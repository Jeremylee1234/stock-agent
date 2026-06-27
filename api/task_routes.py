"""
任务队列接口 —— 解决 iOS 后台断开 SSE 连接的问题

原理：
  客户端发起任务 → 服务端后台异步执行 agent → 客户端随时轮询结果
  即使 app 进后台断开连接，任务在服务端继续跑，回到前台再拉结果即可

接口：
  POST /api/v1/task          创建任务，立即返回 task_id
  GET  /api/v1/task/{id}     查询任务状态和结果
  DELETE /api/v1/task/{id}   取消/删除任务
"""
import asyncio
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agents.stock_agent_main import StockAnalysisGraph
from agents.backtest_agent import BacktestAgent

# 回测相关关键词（快速判断，无需 LLM）
_BACKTEST_KEYWORDS = [
    "回测", "历史回测", "策略测试", "进场条件", "连板策略", "胜率", "收益评估",
    "历史验证", "策略验证", "回踩买入", "断板", "连板回踩", "买入策略", "止损",
    "持仓天数", "胜率统计", "策略回测", "量化回测",
]

def _is_backtest_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _BACKTEST_KEYWORDS)


def _make_graph(query: str):
    """根据 query 选择合适的 agent"""
    if _is_backtest_query(query):
        return BacktestAgent()
    return StockAnalysisGraph()

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 内存任务存储（生产环境换 Redis）──────────────────────────────────────────
# 结构：{ task_id: TaskRecord }
_tasks: Dict[str, Dict[str, Any]] = {}

# 任务超时自动清理（1小时）
TASK_TTL_SECONDS = 3600


# ── 数据模型 ──────────────────────────────────────────────────────────────────

class CreateTaskRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class TaskStatus:
    PENDING  = "pending"   # 等待执行（预留，当前直接 running）
    RUNNING  = "running"   # 执行中
    DONE     = "done"      # 完成
    ERROR    = "error"     # 出错
    CANCELLED= "cancelled" # 已取消


# ── 后台执行函数 ──────────────────────────────────────────────────────────────

async def _run_task(task_id: str, query: str, session_id: str):
    """在后台异步执行 agent，把结果写入 _tasks[task_id]"""
    task = _tasks[task_id]
    graph = _make_graph(query)

    try:
        async for event in graph.astream_with_events(
            query,
            config={"configurable": {"thread_id": session_id}}
        ):
            # 任务被取消则停止
            if task["status"] == TaskStatus.CANCELLED:
                logger.info(f"Task {task_id} cancelled, stopping agent")
                return

            etype = event.get("event_type", "")
            data  = event.get("data", {})

            # 把所有事件追加到 events 列表，客户端可以按需取用
            task["events"].append({"event_type": etype, "data": data})

            # 同时维护几个常用字段，方便客户端快速读取
            if etype == "analysis_chunk":
                task["chunks"].append(data.get("content", ""))

            elif etype == "stage_complete":
                task["stage_summaries"].append({
                    "stage": data.get("stage"),
                    "summary": data.get("summary", ""),
                    "duration_ms": data.get("duration_ms", 0),
                })

            elif etype == "final_answer":
                task["final_answer"] = data.get("content", "")
                task["metadata"]     = data.get("metadata", {})

            elif etype == "workflow_complete":
                task["status"] = TaskStatus.DONE
                task["finished_at"] = datetime.now().isoformat()
                logger.info(f"Task {task_id} done")
                return

            elif etype == "error":
                task["status"] = TaskStatus.ERROR
                task["error"]  = data.get("error_message", "未知错误")
                task["finished_at"] = datetime.now().isoformat()
                logger.error(f"Task {task_id} error: {task['error']}")
                return

        # 流结束但没收到 workflow_complete（兜底）
        if task["status"] == TaskStatus.RUNNING:
            task["status"] = TaskStatus.DONE
            task["finished_at"] = datetime.now().isoformat()

    except asyncio.CancelledError:
        task["status"] = TaskStatus.CANCELLED
        task["finished_at"] = datetime.now().isoformat()
    except Exception as e:
        task["status"] = TaskStatus.ERROR
        task["error"]  = str(e)
        task["finished_at"] = datetime.now().isoformat()
        logger.exception(f"Task {task_id} unexpected error")


def _new_task_record(task_id: str, query: str, session_id: str) -> Dict:
    return {
        "task_id":       task_id,
        "session_id":    session_id,
        "query":         query,
        "status":        TaskStatus.RUNNING,
        "events":        [],          # 所有 SSE 事件（完整）
        "chunks":        [],          # analysis_chunk 内容列表
        "stage_summaries": [],        # 每个阶段的摘要
        "final_answer":  None,        # 最终答案
        "metadata":      {},          # 耗时、工具列表等
        "error":         None,
        "created_at":    datetime.now().isoformat(),
        "finished_at":   None,
        "expires_at":    (datetime.now() + timedelta(seconds=TASK_TTL_SECONDS)).isoformat(),
    }


# ── 接口 ──────────────────────────────────────────────────────────────────────

@router.post("/task", tags=["task"])
async def create_task(body: CreateTaskRequest):
    """
    创建分析任务（适合 iOS / 移动端）

    立即返回 task_id，后台异步执行 agent。
    客户端可以随时断开，任务继续在服务端跑。

    返回：
        { "task_id": "xxx", "status": "running" }
    """
    task_id    = str(uuid.uuid4())
    session_id = body.session_id or task_id

    record = _new_task_record(task_id, body.query, session_id)
    _tasks[task_id] = record

    # 后台启动，不等待
    asyncio.create_task(_run_task(task_id, body.query, session_id))

    logger.info(f"Task created: {task_id}, query: {body.query[:50]}")
    return {
        "task_id":    task_id,
        "session_id": session_id,
        "status":     TaskStatus.RUNNING,
        "created_at": record["created_at"],
    }


@router.get("/task/{task_id}", tags=["task"])
async def get_task(task_id: str, since_event: int = 0):
    """
    查询任务状态和结果

    参数：
        task_id:     创建任务时返回的 ID
        since_event: 从第几个事件开始返回（用于增量拉取，默认 0 = 全部）

    返回：
        {
          "task_id": "xxx",
          "status": "running" | "done" | "error" | "cancelled",
          "progress": {
            "stage_summaries": [...],   // 已完成的阶段摘要
            "answer_so_far": "...",     // 已生成的答案片段（流式拼接）
          },
          "result": {                   // status=done 时才有
            "final_answer": "...",
            "metadata": { "total_duration_ms": 12000, "tools_used": [...] }
          },
          "error": null,
          "events_from": 0,             // 本次返回的事件起始索引
          "events_total": 42,           // 目前总事件数
          "new_events": [...]           // since_event 之后的新事件
        }
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在或已过期")

    all_events  = task["events"]
    new_events  = all_events[since_event:]
    answer_so_far = "".join(task["chunks"])

    resp: Dict[str, Any] = {
        "task_id":    task_id,
        "status":     task["status"],
        "created_at": task["created_at"],
        "finished_at":task["finished_at"],
        "progress": {
            "stage_summaries": task["stage_summaries"],
            "answer_so_far":   answer_so_far,
        },
        "events_from":  since_event,
        "events_total": len(all_events),
        "new_events":   new_events,
        "error": task["error"],
    }

    if task["status"] == TaskStatus.DONE:
        resp["result"] = {
            "final_answer": task["final_answer"],
            "metadata":     task["metadata"],
        }

    return resp


@router.delete("/task/{task_id}", tags=["task"])
async def cancel_task(task_id: str):
    """
    取消任务

    将任务标记为 cancelled，后台协程检测到后会停止执行。
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    if task["status"] == TaskStatus.RUNNING:
        task["status"] = TaskStatus.CANCELLED
        task["finished_at"] = datetime.now().isoformat()

    return {"task_id": task_id, "status": task["status"]}


# ── 定时清理过期任务 ──────────────────────────────────────────────────────────

async def _cleanup_expired_tasks():
    """每 10 分钟清理一次过期任务，防止内存泄漏"""
    while True:
        await asyncio.sleep(600)
        now = datetime.now()
        expired = [
            tid for tid, t in list(_tasks.items())
            if datetime.fromisoformat(t["expires_at"]) < now
        ]
        for tid in expired:
            del _tasks[tid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired tasks")


# 注册启动事件
from fastapi import FastAPI

def register_task_cleanup(app: FastAPI):
    @app.on_event("startup")
    async def start_cleanup():
        asyncio.create_task(_cleanup_expired_tasks())
