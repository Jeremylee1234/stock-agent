"""超时控制工具

提供工具调用和工作流执行的超时控制机制。
"""
import asyncio
import functools
from typing import Any, Callable, Optional, TypeVar, Union
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class TimeoutError(Exception):
    """超时异常"""
    def __init__(self, message: str, timeout: float, operation: str = "operation"):
        self.timeout = timeout
        self.operation = operation
        super().__init__(message)


async def async_timeout(
    coro,
    timeout: float,
    operation_name: str = "operation"
) -> Any:
    """异步操作超时控制
    
    Args:
        coro: 协程对象
        timeout: 超时时间（秒）
        operation_name: 操作名称（用于日志）
    
    Returns:
        协程执行结果
    
    Raises:
        TimeoutError: 超时异常
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        error_msg = f"{operation_name} timed out after {timeout} seconds"
        logger.warning(error_msg)
        raise TimeoutError(error_msg, timeout, operation_name)


def timeout_decorator(
    timeout: float,
    operation_name: Optional[str] = None
):
    """超时装饰器（用于异步函数）
    
    Args:
        timeout: 超时时间（秒）
        operation_name: 操作名称（可选，默认使用函数名）
    
    Example:
        @timeout_decorator(timeout=30, operation_name="fetch_data")
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            return await async_timeout(
                func(*args, **kwargs),
                timeout=timeout,
                operation_name=op_name
            )
        return wrapper
    return decorator


class TimeoutContext:
    """超时上下文管理器
    
    Example:
        async with TimeoutContext(timeout=30, operation_name="data_collection"):
            result = await some_async_operation()
    """
    
    def __init__(self, timeout: float, operation_name: str = "operation"):
        self.timeout = timeout
        self.operation_name = operation_name
        self.start_time = None
        self.task = None
    
    async def __aenter__(self):
        self.start_time = datetime.now()
        logger.debug(f"Starting {self.operation_name} with timeout {self.timeout}s")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is asyncio.TimeoutError:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            error_msg = f"{self.operation_name} timed out after {elapsed:.2f} seconds (limit: {self.timeout}s)"
            logger.warning(error_msg)
            raise TimeoutError(error_msg, self.timeout, self.operation_name)
        
        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            logger.debug(f"{self.operation_name} completed in {elapsed:.2f}s")
        
        return False


async def run_with_timeout(
    func: Callable,
    *args,
    timeout: float,
    operation_name: str = "operation",
    **kwargs
) -> Any:
    """运行函数并应用超时控制
    
    Args:
        func: 要执行的函数（可以是同步或异步）
        *args: 位置参数
        timeout: 超时时间（秒）
        operation_name: 操作名称
        **kwargs: 关键字参数
    
    Returns:
        函数执行结果
    
    Raises:
        TimeoutError: 超时异常
    """
    if asyncio.iscoroutinefunction(func):
        # 异步函数
        return await async_timeout(
            func(*args, **kwargs),
            timeout=timeout,
            operation_name=operation_name
        )
    else:
        # 同步函数，在executor中运行
        loop = asyncio.get_event_loop()
        return await async_timeout(
            loop.run_in_executor(None, functools.partial(func, *args, **kwargs)),
            timeout=timeout,
            operation_name=operation_name
        )


class ToolTimeoutManager:
    """工具调用超时管理器"""
    
    def __init__(self, default_timeout: float = 60.0):
        """
        Args:
            default_timeout: 默认超时时间（秒）
        """
        self.default_timeout = default_timeout
        self.tool_timeouts = {}  # 每个工具的自定义超时
        self.timeout_stats = {
            "total_calls": 0,
            "timeout_count": 0,
            "timeouts_by_tool": {}
        }
    
    def set_tool_timeout(self, tool_name: str, timeout: float):
        """设置特定工具的超时时间
        
        Args:
            tool_name: 工具名称
            timeout: 超时时间（秒）
        """
        self.tool_timeouts[tool_name] = timeout
        logger.info(f"Set timeout for tool {tool_name}: {timeout}s")
    
    def get_tool_timeout(self, tool_name: str) -> float:
        """获取工具的超时时间
        
        Args:
            tool_name: 工具名称
        
        Returns:
            超时时间（秒）
        """
        return self.tool_timeouts.get(tool_name, self.default_timeout)
    
    async def call_tool_with_timeout(
        self,
        tool_func: Callable,
        tool_name: str,
        *args,
        **kwargs
    ) -> Any:
        """调用工具并应用超时控制
        
        Args:
            tool_func: 工具函数
            tool_name: 工具名称
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            工具执行结果
        
        Raises:
            TimeoutError: 超时异常
        """
        timeout = self.get_tool_timeout(tool_name)
        self.timeout_stats["total_calls"] += 1
        
        try:
            result = await run_with_timeout(
                tool_func,
                *args,
                timeout=timeout,
                operation_name=f"tool_{tool_name}",
                **kwargs
            )
            return result
        except TimeoutError as e:
            # 记录超时统计
            self.timeout_stats["timeout_count"] += 1
            if tool_name not in self.timeout_stats["timeouts_by_tool"]:
                self.timeout_stats["timeouts_by_tool"][tool_name] = 0
            self.timeout_stats["timeouts_by_tool"][tool_name] += 1
            
            logger.error(f"Tool {tool_name} timed out after {timeout}s")
            raise
    
    def get_timeout_stats(self) -> dict:
        """获取超时统计信息
        
        Returns:
            超时统计字典
        """
        stats = self.timeout_stats.copy()
        if stats["total_calls"] > 0:
            stats["timeout_rate"] = stats["timeout_count"] / stats["total_calls"]
        else:
            stats["timeout_rate"] = 0.0
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self.timeout_stats = {
            "total_calls": 0,
            "timeout_count": 0,
            "timeouts_by_tool": {}
        }


# 全局工具超时管理器实例
_global_tool_timeout_manager: Optional[ToolTimeoutManager] = None


def get_tool_timeout_manager() -> ToolTimeoutManager:
    """获取全局工具超时管理器
    
    Returns:
        工具超时管理器实例
    """
    global _global_tool_timeout_manager
    if _global_tool_timeout_manager is None:
        # 从配置读取默认超时
        try:
            from config.settings import settings
            default_timeout = settings.llm.timeout
        except:
            default_timeout = 60.0
        
        _global_tool_timeout_manager = ToolTimeoutManager(default_timeout=default_timeout)
    
    return _global_tool_timeout_manager


def set_tool_timeout_manager(manager: ToolTimeoutManager):
    """设置全局工具超时管理器
    
    Args:
        manager: 工具超时管理器实例
    """
    global _global_tool_timeout_manager
    _global_tool_timeout_manager = manager
