"""
统一错误处理模块

提供标准化的错误处理机制，包括：
- ToolExecutor: 统一工具调用和错误处理
- 标准错误格式和错误代码
- 错误分类和恢复策略
"""

import logging
import traceback
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Union
from functools import wraps
import asyncio

# 导入常见异常类型
try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


# 错误代码定义
class ErrorCode:
    """标准错误代码"""
    # 工具调用错误
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_CONNECTION_ERROR = "TOOL_CONNECTION_ERROR"
    TOOL_AUTH_ERROR = "TOOL_AUTH_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    
    # 数据验证错误
    DATA_VALIDATION_ERROR = "DATA_VALIDATION_ERROR"
    DATA_FORMAT_ERROR = "DATA_FORMAT_ERROR"
    DATA_MISSING_ERROR = "DATA_MISSING_ERROR"
    
    # 工作流执行错误
    WORKFLOW_ERROR = "WORKFLOW_ERROR"
    WORKFLOW_TIMEOUT = "WORKFLOW_TIMEOUT"
    LLM_CALL_ERROR = "LLM_CALL_ERROR"
    
    # 配置错误
    CONFIG_ERROR = "CONFIG_ERROR"
    CONFIG_MISSING_ERROR = "CONFIG_MISSING_ERROR"
    
    # 系统错误
    SYSTEM_ERROR = "SYSTEM_ERROR"
    MEMORY_ERROR = "MEMORY_ERROR"
    FILE_SYSTEM_ERROR = "FILE_SYSTEM_ERROR"


class ToolExecutor:
    """
    工具执行器，统一处理工具调用和错误
    
    提供以下功能：
    - 统一的工具调用接口
    - 自动错误捕获和分类
    - 标准化的错误响应格式
    - 可配置的重试机制
    - 详细的日志记录
    """
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        初始化工具执行器
        
        Args:
            max_retries: 最大重试次数（仅对可恢复错误）
            retry_delay: 重试延迟（秒），使用指数退避
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)
    
    async def execute_tool(
        self,
        tool_func: Callable,
        *args,
        tool_name: Optional[str] = None,
        enable_retry: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行工具并处理错误
        
        Args:
            tool_func: 要执行的工具函数
            *args: 位置参数
            tool_name: 工具名称（用于日志和错误信息）
            enable_retry: 是否启用重试机制
            **kwargs: 关键字参数
        
        Returns:
            标准化的工具执行结果字典：
            {
                "success": bool,
                "data": Any,  # 仅在成功时存在
                "tool_name": str,
                "timestamp": str,
                "error_code": str,  # 仅在失败时存在
                "error_message": str,  # 仅在失败时存在
                "error_detail": str,  # 仅在失败时存在
                "recoverable": bool,  # 仅在失败时存在
                "retry_suggested": bool  # 仅在失败时存在
            }
        """
        if tool_name is None:
            tool_name = getattr(tool_func, '__name__', 'unknown_tool')
        
        retry_count = 0
        last_error = None
        
        while retry_count <= (self.max_retries if enable_retry else 0):
            try:
                # 记录工具调用开始
                self.logger.info(f"Executing tool: {tool_name}, attempt: {retry_count + 1}")
                start_time = datetime.now()
                
                # 执行工具函数
                if asyncio.iscoroutinefunction(tool_func):
                    result = await tool_func(*args, **kwargs)
                else:
                    result = tool_func(*args, **kwargs)
                
                # 计算执行时间
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # 记录成功
                self.logger.info(
                    f"Tool {tool_name} executed successfully, "
                    f"duration: {duration_ms}ms"
                )
                
                return {
                    "success": True,
                    "data": result,
                    "tool_name": tool_name,
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": duration_ms
                }
            
            except Exception as e:
                last_error = e
                error_result = self._classify_and_handle_error(tool_name, e)
                
                # 如果错误可恢复且启用重试，则重试
                if (error_result.get("recoverable", False) and 
                    enable_retry and 
                    retry_count < self.max_retries):
                    retry_count += 1
                    delay = self.retry_delay * (2 ** (retry_count - 1))  # 指数退避
                    self.logger.warning(
                        f"Tool {tool_name} failed (attempt {retry_count}), "
                        f"retrying in {delay}s: {str(e)}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # 不可恢复或达到最大重试次数
                    return error_result
        
        # 不应该到达这里，但以防万一
        return self._handle_generic_error(tool_name, last_error)
    
    def execute_tool_sync(
        self,
        tool_func: Callable,
        *args,
        tool_name: Optional[str] = None,
        enable_retry: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        同步版本的工具执行器
        
        Args:
            tool_func: 要执行的工具函数（必须是同步函数）
            *args: 位置参数
            tool_name: 工具名称
            enable_retry: 是否启用重试机制
            **kwargs: 关键字参数
        
        Returns:
            标准化的工具执行结果字典
        """
        if tool_name is None:
            tool_name = getattr(tool_func, '__name__', 'unknown_tool')
        
        retry_count = 0
        last_error = None
        
        while retry_count <= (self.max_retries if enable_retry else 0):
            try:
                # 记录工具调用开始
                self.logger.info(f"Executing tool: {tool_name}, attempt: {retry_count + 1}")
                start_time = datetime.now()
                
                # 执行工具函数
                result = tool_func(*args, **kwargs)
                
                # 计算执行时间
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # 记录成功
                self.logger.info(
                    f"Tool {tool_name} executed successfully, "
                    f"duration: {duration_ms}ms"
                )
                
                return {
                    "success": True,
                    "data": result,
                    "tool_name": tool_name,
                    "timestamp": datetime.now().isoformat(),
                    "duration_ms": duration_ms
                }
            
            except Exception as e:
                last_error = e
                error_result = self._classify_and_handle_error(tool_name, e)
                
                # 如果错误可恢复且启用重试，则重试
                if (error_result.get("recoverable", False) and 
                    enable_retry and 
                    retry_count < self.max_retries):
                    retry_count += 1
                    delay = self.retry_delay * (2 ** (retry_count - 1))  # 指数退避
                    self.logger.warning(
                        f"Tool {tool_name} failed (attempt {retry_count}), "
                        f"retrying in {delay}s: {str(e)}"
                    )
                    import time
                    time.sleep(delay)
                    continue
                else:
                    # 不可恢复或达到最大重试次数
                    return error_result
        
        # 不应该到达这里，但以防万一
        return self._handle_generic_error(tool_name, last_error)
    
    def _classify_and_handle_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """
        分类并处理错误
        
        Args:
            tool_name: 工具名称
            error: 异常对象
        
        Returns:
            标准化的错误响应字典
        """
        error_type = type(error).__name__
        
        # 超时错误
        if requests and isinstance(error, requests.Timeout):
            return self._handle_timeout_error(tool_name, error)
        
        # 连接错误
        if requests and isinstance(error, requests.ConnectionError):
            return self._handle_connection_error(tool_name, error)
        
        # 认证错误
        if requests and isinstance(error, requests.HTTPError):
            if hasattr(error, 'response') and error.response.status_code in [401, 403]:
                return self._handle_auth_error(tool_name, error)
        
        # 值错误（通常是数据验证问题）
        if isinstance(error, ValueError):
            return self._handle_validation_error(tool_name, error)
        
        # 键错误（数据格式问题）
        if isinstance(error, KeyError):
            return self._handle_data_format_error(tool_name, error)
        
        # 内存错误
        if isinstance(error, MemoryError):
            return self._handle_memory_error(tool_name, error)
        
        # 通用错误
        return self._handle_generic_error(tool_name, error)
    
    def _handle_timeout_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理超时错误"""
        self.logger.error(
            f"Tool {tool_name} timeout: {error}",
            exc_info=True
        )
        return {
            "success": False,
            "error_code": ErrorCode.TOOL_TIMEOUT,
            "error_message": f"工具 {tool_name} 调用超时",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "tool_name": tool_name,
            "recoverable": True,
            "retry_suggested": True,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_connection_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理连接错误"""
        self.logger.error(
            f"Tool {tool_name} connection error: {error}",
            exc_info=True
        )
        return {
            "success": False,
            "error_code": ErrorCode.TOOL_CONNECTION_ERROR,
            "error_message": f"工具 {tool_name} 连接失败",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "tool_name": tool_name,
            "recoverable": True,
            "retry_suggested": True,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_auth_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理认证错误"""
        self.logger.error(
            f"Tool {tool_name} authentication error: {error}",
            exc_info=True
        )
        return {
            "success": False,
            "error_code": ErrorCode.TOOL_AUTH_ERROR,
            "error_message": f"工具 {tool_name} 认证失败",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "tool_name": tool_name,
            "recoverable": False,
            "retry_suggested": False,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_validation_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理数据验证错误"""
        self.logger.warning(
            f"Tool {tool_name} validation error: {error}"
        )
        return {
            "success": False,
            "error_code": ErrorCode.DATA_VALIDATION_ERROR,
            "error_message": f"工具 {tool_name} 返回数据验证失败",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "tool_name": tool_name,
            "recoverable": False,
            "retry_suggested": False,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_data_format_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理数据格式错误"""
        self.logger.warning(
            f"Tool {tool_name} data format error: {error}"
        )
        return {
            "success": False,
            "error_code": ErrorCode.DATA_FORMAT_ERROR,
            "error_message": f"工具 {tool_name} 返回数据格式错误",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "tool_name": tool_name,
            "recoverable": False,
            "retry_suggested": False,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_memory_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理内存错误"""
        self.logger.critical(
            f"Tool {tool_name} memory error: {error}",
            exc_info=True
        )
        return {
            "success": False,
            "error_code": ErrorCode.MEMORY_ERROR,
            "error_message": f"工具 {tool_name} 内存不足",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "tool_name": tool_name,
            "recoverable": False,
            "retry_suggested": False,
            "timestamp": datetime.now().isoformat()
        }
    
    def _handle_generic_error(
        self,
        tool_name: str,
        error: Exception
    ) -> Dict[str, Any]:
        """处理通用错误"""
        self.logger.error(
            f"Tool {tool_name} unexpected error: {error}",
            exc_info=True
        )
        
        # 获取堆栈跟踪
        stack_trace = traceback.format_exc()
        
        return {
            "success": False,
            "error_code": ErrorCode.TOOL_ERROR,
            "error_message": f"工具 {tool_name} 执行失败",
            "error_detail": str(error),
            "error_type": type(error).__name__,
            "stack_trace": stack_trace,
            "tool_name": tool_name,
            "recoverable": False,
            "retry_suggested": False,
            "timestamp": datetime.now().isoformat()
        }


def handle_tool_errors(tool_name: Optional[str] = None):
    """
    装饰器：为工具函数添加统一的错误处理
    
    使用示例：
        @handle_tool_errors(tool_name="get_stock_price")
        def get_stock_price(stock_code: str):
            # 工具逻辑
            pass
    
    Args:
        tool_name: 工具名称（可选，默认使用函数名）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            executor = ToolExecutor()
            return await executor.execute_tool(
                func,
                *args,
                tool_name=tool_name or func.__name__,
                **kwargs
            )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            executor = ToolExecutor()
            return executor.execute_tool_sync(
                func,
                *args,
                tool_name=tool_name or func.__name__,
                **kwargs
            )
        
        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 导出的公共接口
__all__ = [
    'ErrorCode',
    'ToolExecutor',
    'handle_tool_errors'
]
