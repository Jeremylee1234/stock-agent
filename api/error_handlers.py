"""API错误处理器

提供统一的错误处理和错误响应格式。
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
from datetime import datetime
from typing import Union

from utils.logger import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """API错误基类"""
    
    def __init__(
        self,
        error_code: str,
        error_message: str,
        error_detail: str = None,
        status_code: int = 500
    ):
        self.error_code = error_code
        self.error_message = error_message
        self.error_detail = error_detail
        self.status_code = status_code
        super().__init__(error_message)


class WorkflowError(APIError):
    """工作流执行错误"""
    
    def __init__(self, message: str, detail: str = None):
        super().__init__(
            error_code="WORKFLOW_ERROR",
            error_message=message,
            error_detail=detail,
            status_code=500
        )


class ToolExecutionError(APIError):
    """工具执行错误"""
    
    def __init__(self, tool_name: str, message: str, detail: str = None):
        super().__init__(
            error_code="TOOL_EXECUTION_ERROR",
            error_message=f"工具 {tool_name} 执行失败: {message}",
            error_detail=detail,
            status_code=500
        )


class DataValidationError(APIError):
    """数据验证错误"""
    
    def __init__(self, message: str, detail: str = None):
        super().__init__(
            error_code="DATA_VALIDATION_ERROR",
            error_message=message,
            error_detail=detail,
            status_code=400
        )


class ConfigurationError(APIError):
    """配置错误"""
    
    def __init__(self, message: str, detail: str = None):
        super().__init__(
            error_code="CONFIGURATION_ERROR",
            error_message=message,
            error_detail=detail,
            status_code=500
        )


def create_error_response(
    error_code: str,
    error_message: str,
    error_detail: str = None,
    status_code: int = 500,
    request_id: str = None
) -> JSONResponse:
    """创建标准错误响应
    
    Args:
        error_code: 错误代码
        error_message: 错误消息
        error_detail: 错误详情
        status_code: HTTP状态码
        request_id: 请求ID
    
    Returns:
        JSON错误响应
    """
    content = {
        "error": True,
        "error_code": error_code,
        "error_message": error_message,
        "timestamp": datetime.now().isoformat()
    }
    
    if error_detail:
        content["error_detail"] = error_detail
    
    if request_id:
        content["request_id"] = request_id
    
    return JSONResponse(
        status_code=status_code,
        content=content
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """API错误处理器
    
    Args:
        request: 请求对象
        exc: API错误
    
    Returns:
        错误响应
    """
    logger.error(
        f"API Error: {exc.error_code} - {exc.error_message}",
        extra={
            "error_code": exc.error_code,
            "error_detail": exc.error_detail,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return create_error_response(
        error_code=exc.error_code,
        error_message=exc.error_message,
        error_detail=exc.error_detail,
        status_code=exc.status_code
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """HTTP异常处理器
    
    Args:
        request: 请求对象
        exc: HTTP异常
    
    Returns:
        错误响应
    """
    logger.warning(
        f"HTTP Exception: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return create_error_response(
        error_code=f"HTTP_{exc.status_code}",
        error_message=str(exc.detail),
        status_code=exc.status_code
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """请求验证异常处理器
    
    Args:
        request: 请求对象
        exc: 验证异常
    
    Returns:
        错误响应
    """
    errors = exc.errors()
    logger.warning(
        f"Validation Error: {errors}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": errors
        }
    )
    
    # 格式化验证错误
    error_messages = []
    for error in errors:
        loc = " -> ".join(str(x) for x in error["loc"])
        msg = error["msg"]
        error_messages.append(f"{loc}: {msg}")
    
    return create_error_response(
        error_code="VALIDATION_ERROR",
        error_message="请求数据验证失败",
        error_detail="; ".join(error_messages),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """通用异常处理器
    
    Args:
        request: 请求对象
        exc: 异常
    
    Returns:
        错误响应
    """
    logger.error(
        f"Unhandled Exception: {type(exc).__name__} - {str(exc)}",
        exc_info=True,
        extra={
            "path": request.url.path,
            "method": request.method
        }
    )
    
    return create_error_response(
        error_code="INTERNAL_SERVER_ERROR",
        error_message="服务器内部错误",
        error_detail=str(exc) if logging.getLogger().level <= logging.DEBUG else None,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def register_error_handlers(app):
    """注册错误处理器到FastAPI应用
    
    Args:
        app: FastAPI应用实例
    """
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("Error handlers registered")
