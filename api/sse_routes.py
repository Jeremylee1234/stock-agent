"""SSE路由实现

提供Server-Sent Events接口用于实时流式推送分析结果。
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json
import logging
import uuid
import asyncio
from datetime import datetime

from api.models import AnalysisRequest
from api.event_types import (
    validate_event_type,
    validate_event_data,
    SUPPORTED_EVENT_TYPES,
    get_event_type_description
)
from agents.stock_agent_main import StockAnalysisGraph
from agents.backtest_agent import BacktestAgent
from utils.logger import get_logger
from utils.concurrency import get_concurrency_limiter

# 配置日志
logger = get_logger(__name__)

# 创建路由
router = APIRouter()

# 获取全局并发限制器
concurrency_limiter = get_concurrency_limiter()


def format_sse_event(event_type: str, data: dict, event_id: str = None) -> str:
    """格式化SSE事件
    
    Args:
        event_type: 事件类型
        data: 事件数据
        event_id: 事件ID（可选）
    
    Returns:
        格式化的SSE事件字符串
    """
    lines = []
    
    # 添加事件ID
    if event_id:
        lines.append(f"id: {event_id}")
    
    # 添加事件类型
    lines.append(f"event: {event_type}")
    
    # 添加数据（JSON格式）
    data_json = json.dumps(data, ensure_ascii=False)
    lines.append(f"data: {data_json}")
    
    # SSE格式要求：两个换行符结束一个事件
    lines.append("")
    lines.append("")
    
    return "\n".join(lines)


async def event_generator(
    query: str,
    session_id: str,
    options = None
) -> AsyncGenerator[str, None]:
    """SSE事件生成器
    
    Args:
        query: 用户查询问题
        session_id: 会话ID
        options: 可选配置
    
    Yields:
        SSE格式的事件字符串
    """
    if options is None:
        from api.models import AnalysisOptions
        options = AnalysisOptions()
    
    # options 是 AnalysisOptions Pydantic 对象，用属性访问
    enable_trace = options.enable_trace if hasattr(options, 'enable_trace') else False
    max_history = options.max_history if hasattr(options, 'max_history') else 30
    
    # 获取超时配置
    try:
        from config.settings import settings
        workflow_timeout = settings.performance.request_timeout
    except:
        workflow_timeout = 300  # 默认5分钟
    
    logger.info(f"Starting SSE stream for session {session_id}, query: {query}, timeout: {workflow_timeout}s")
    
    graph = None
    workflow_completed = False
    
    try:
    #     # 创建工作流实例
    # _BACKTEST_KEYWORDS = [
    #     "回测", "历史回测", "策略测试", "进场条件", "连板策略", "胜率", "收益评估",
    #     "历史验证", "策略验证", "回踩买入", "断板", "连板回踩", "买入策略",
    #     "量化回测", "策略回测",
    # ]

    # if any(kw in query for kw in _BACKTEST_KEYWORDS):
    #     graph = BacktestAgent()
    # else:
        graph = StockAnalysisGraph(
            trace=enable_trace,
            print_live_trace=False,
            enable_data_compression=True
        )
        
        # 配置
        config = {
            "configurable": {
                "thread_id": session_id
            }
        }
        
        # 使用超时控制流式执行工作流
        from utils.timeout import async_timeout, TimeoutError as CustomTimeoutError
        
        try:
            # 流式执行工作流并推送事件
            event_count = 0
            
            # 包装工作流执行以应用超时
            async def execute_workflow():
                async for event in graph.astream_with_events(query, config):
                    yield event
            
            # 应用超时控制
            workflow_generator = execute_workflow()
            start_time = asyncio.get_event_loop().time()
            
            async for event in workflow_generator:
                # 检查是否超时
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > workflow_timeout:
                    raise CustomTimeoutError(
                        f"Workflow execution exceeded timeout of {workflow_timeout}s",
                        workflow_timeout,
                        "workflow_execution"
                    )
                
                event_count += 1
                event_type = event.get("event_type", "unknown")
                event_data = event.get("data", {})
                
                # 检查是否为完成事件
                if event_type == "workflow_complete":
                    workflow_completed = True
                
                # 验证事件类型
                if not validate_event_type(event_type):
                    logger.warning(f"Unknown event type: {event_type}, skipping validation")
                else:
                    # 验证事件数据格式（仅记录警告，不中断流）
                    is_valid, error_msg = validate_event_data(event_type, event_data)
                    if not is_valid:
                        logger.warning(f"Event data validation failed for {event_type}: {error_msg}")
                
                # 生成事件ID
                event_id = f"{session_id}_{event_count}"
                
                # 格式化并推送SSE事件
                sse_event = format_sse_event(event_type, event_data, event_id)
                yield sse_event
                
                logger.debug(f"Sent SSE event: {event_type} (id: {event_id})")
            
            logger.info(f"SSE stream completed for session {session_id}, total events: {event_count}")
        
        except CustomTimeoutError as e:
            logger.error(f"Workflow timeout for session {session_id}: {e}")
            
            # 发送超时错误事件
            timeout_event = {
                "error_code": "WORKFLOW_TIMEOUT",
                "error_message": f"工作流执行超时（超过{workflow_timeout}秒）",
                "error_detail": str(e),
                "timeout_seconds": workflow_timeout,
                "recoverable": False,
                "timestamp": datetime.now().isoformat()
            }
            
            sse_event = format_sse_event("error", timeout_event)
            yield sse_event
            
            # 发送完成事件（超时状态）
            if not workflow_completed:
                complete_event = {
                    "session_id": session_id,
                    "status": "timeout",
                    "timestamp": datetime.now().isoformat()
                }
                
                sse_event = format_sse_event("workflow_complete", complete_event)
                yield sse_event
        
    except asyncio.CancelledError:
        # 客户端断开连接
        logger.info(f"SSE stream cancelled for session {session_id} (client disconnected)")
        
        # 如果工作流未完成，发送取消事件
        if not workflow_completed:
            cancel_event = {
                "session_id": session_id,
                "status": "cancelled",
                "reason": "client_disconnected",
                "timestamp": datetime.now().isoformat()
            }
            sse_event = format_sse_event("workflow_complete", cancel_event)
            yield sse_event
        
        raise  # 重新抛出以正确关闭连接
        
    except Exception as e:
        logger.error(f"Error in SSE stream for session {session_id}: {e}", exc_info=True)
        
        # 发送错误事件
        error_event = {
            "error_code": "STREAM_ERROR",
            "error_message": "流式处理失败",
            "error_detail": str(e),
            "error_type": type(e).__name__,
            "recoverable": False,
            "timestamp": datetime.now().isoformat()
        }
        
        sse_event = format_sse_event("error", error_event)
        yield sse_event
        
        # 发送完成事件（错误状态）
        if not workflow_completed:
            complete_event = {
                "session_id": session_id,
                "status": "error",
                "timestamp": datetime.now().isoformat()
            }
            
            sse_event = format_sse_event("workflow_complete", complete_event)
            yield sse_event
    
    finally:
        # 清理资源
        logger.debug(f"Cleaning up resources for session {session_id}")
        if graph:
            # 这里可以添加工作流清理逻辑
            pass


@router.post("/analysis/stream")
async def stream_analysis(request: Request):
    """SSE流式分析接口
    
    接收用户查询，通过SSE实时推送分析过程和结果。
    
    Args:
        request: FastAPI请求对象
    
    Returns:
        StreamingResponse: SSE流式响应
    
    Raises:
        HTTPException: 请求参数错误或处理失败
    """
    try:
        # 解析请求体
        body = await request.json()
        
        # 验证请求数据
        try:
            analysis_request = AnalysisRequest(**body)
        except Exception as e:
            logger.error(f"Invalid request data: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"请求数据格式错误: {str(e)}"
            )
        
        # 提取参数
        query = analysis_request.query
        session_id = analysis_request.session_id or str(uuid.uuid4())
        options = analysis_request.options or {}
        
        # 验证查询不为空
        if not query or not query.strip():
            raise HTTPException(
                status_code=400,
                detail="查询问题不能为空"
            )
        
        # 检查并发限制
        stats = concurrency_limiter.get_stats()
        if stats["active_requests"] >= stats["max_concurrent"]:
            logger.warning(
                f"Request rejected due to concurrency limit. "
                f"Active: {stats['active_requests']}/{stats['max_concurrent']}"
            )
            raise HTTPException(
                status_code=503,
                detail=f"服务器繁忙，当前并发请求数已达上限（{stats['max_concurrent']}），请稍后重试"
            )
        
        logger.info(f"Received analysis request: session_id={session_id}, query={query[:50]}...")
        
        # 使用并发控制包装事件生成器
        async def controlled_event_generator():
            """带并发控制的事件生成器"""
            async with concurrency_limiter:
                async for event in event_generator(query, session_id, options):
                    yield event
        
        # 返回SSE流式响应
        return StreamingResponse(
            controlled_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用nginx缓冲
                "Access-Control-Allow-Origin": "*",  # CORS
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in stream_analysis: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"服务器内部错误: {str(e)}"
        )


@router.get("/analysis/stream/test")
async def test_sse():
    """SSE测试端点
    
    用于测试SSE连接是否正常工作。
    
    Returns:
        StreamingResponse: 测试SSE流
    """
    async def test_generator():
        """测试事件生成器"""
        for i in range(5):
            event_data = {
                "message": f"Test event {i + 1}",
                "timestamp": datetime.now().isoformat()
            }
            yield format_sse_event("test", event_data, str(i + 1))
            
            # 模拟延迟
            import asyncio
            await asyncio.sleep(1)
        
        # 发送完成事件
        complete_data = {
            "message": "Test completed",
            "timestamp": datetime.now().isoformat()
        }
        yield format_sse_event("complete", complete_data)
    
    return StreamingResponse(
        test_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/analysis/event-types")
async def get_event_types():
    """获取支持的事件类型列表
    
    Returns:
        支持的事件类型及其描述
    """
    event_types = []
    for event_type in sorted(SUPPORTED_EVENT_TYPES):
        event_types.append({
            "type": event_type,
            "description": get_event_type_description(event_type)
        })
    
    return {
        "event_types": event_types,
        "total": len(event_types)
    }


@router.get("/analysis/stats")
async def get_analysis_stats():
    """获取分析服务统计信息
    
    Returns:
        统计信息，包括并发控制、请求队列等
    """
    stats = {
        "concurrency": concurrency_limiter.get_stats(),
        "recent_requests": concurrency_limiter.get_recent_requests(count=10),
        "timestamp": datetime.now().isoformat()
    }
    
    return stats
