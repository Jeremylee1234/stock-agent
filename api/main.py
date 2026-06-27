"""FastAPI应用主入口

本模块是股票分析系统的 FastAPI 应用入口，负责：
1. 创建和配置 FastAPI 应用实例
2. 配置 CORS 中间件
3. 注册错误处理器
4. 注册路由（SSE 流式接口等）
5. 提供健康检查端点

主要端点：
- GET /: 根路径，返回服务信息
- GET /health: 健康检查
- GET /api/health: API 健康检查（带前缀）
- POST /api/v1/analysis/stream: SSE 流式分析接口
- GET /api/v1/analysis/stream/test: SSE 测试接口
- GET /api/v1/analysis/event-types: 获取事件类型列表
- GET /api/v1/analysis/stats: 获取服务统计信息

使用示例：
    # 启动服务
    uvicorn api.main:app --host 0.0.0.0 --port 8000
    
    # 或直接运行
    python api/main.py

环境变量：
    API__HOST: API 服务监听地址（默认: 0.0.0.0）
    API__PORT: API 服务端口（默认: 8000）
    API__CORS_ORIGINS: 允许的 CORS 源（默认: ["*"]）
    API__ENABLE_DOCS: 是否启用 API 文档（默认: true）
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import logging
import os
from typing import Dict, Any

from config.settings import settings, API_HOST, API_PORT, CORS_ORIGINS, DEBUG
from api.error_handlers import register_error_handlers

# 配置日志
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="股票分析系统API",
    description="基于LangGraph的多智能体股票分析系统，提供实时流式分析、技术指标计算、历史模式搜索等功能",
    version="1.0.0",
    docs_url="/api/docs" if settings.api.enable_docs else None,
    redoc_url="/api/redoc" if settings.api.enable_docs else None,
    contact={
        "name": "开发团队",
        "email": "support@example.com"
    },
    license_info={
        "name": "内部使用"
    }
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册错误处理器
register_error_handlers(app)


@app.get("/", response_class=JSONResponse, tags=["root"])
async def root() -> JSONResponse:
    """根路径端点"""
    return JSONResponse(
        content={
            "service": "股票分析系统API",
            "version": "1.0.0",
            "status": "running"
        },
        media_type="application/json; charset=utf-8"
    )


@app.get("/health", response_class=JSONResponse, tags=["health"])
async def health_check() -> JSONResponse:
    """健康检查端点
    
    用于监控系统检查服务是否健康运行。返回 200 状态码表示服务正常。
    
    Returns:
        JSONResponse: 包含健康状态、时间戳、服务名称和版本的 JSON 响应
        
    Response Schema:
        {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00.000000",
            "service": "stock-analysis-api",
            "version": "1.0.0"
        }
        
    Example:
        >>> curl http://localhost:8000/health
        {"status":"healthy","timestamp":"2024-01-01T00:00:00.000000",...}
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "stock-analysis-api",
            "version": "1.0.0"
        }
    )


@app.get("/api/health", response_class=JSONResponse, tags=["health"])
async def api_health_check() -> JSONResponse:
    """API健康检查端点（带/api前缀）
    
    与 /health 端点功能相同，但带有 /api 前缀，用于统一的 API 路径规范。
    
    Returns:
        JSONResponse: 健康状态信息
        
    See Also:
        health_check: 主健康检查端点
    """
    return await health_check()


# 导入路由
from api.sse_routes import router as sse_router
from api.task_routes import router as task_router, register_task_cleanup

# 注册路由
app.include_router(sse_router, prefix="/api/v1", tags=["analysis"])
app.include_router(task_router, prefix="/api/v1", tags=["task"])

# 注册后台清理任务
register_task_cleanup(app)

# 托管前端静态文件
_web_demo_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web_demo")
if os.path.isdir(_web_demo_dir):
    app.mount("/demo", StaticFiles(directory=_web_demo_dir, html=True), name="web_demo")


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting FastAPI application on {API_HOST}:{API_PORT}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug mode: {DEBUG}")
    logger.info(f"API docs: {'enabled' if settings.api.enable_docs else 'disabled'}")
    
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
        access_log=True
    )
