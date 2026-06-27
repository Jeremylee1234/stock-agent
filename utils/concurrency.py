"""并发控制工具

提供请求并发控制和队列管理机制。
"""
import asyncio
from typing import Optional, Callable, Any
from datetime import datetime
from collections import deque

from utils.logger import get_logger

logger = get_logger(__name__)


class ConcurrencyLimiter:
    """并发限制器
    
    使用信号量控制最大并发数，并提供请求队列管理。
    """
    
    def __init__(self, max_concurrent: int = 10):
        """
        Args:
            max_concurrent: 最大并发请求数
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_requests = 0
        self.total_requests = 0
        self.completed_requests = 0
        self.failed_requests = 0
        self.queue_size = 0
        self.max_queue_size_reached = 0
        self.request_history = deque(maxlen=1000)  # 保留最近1000个请求的历史
        
        logger.info(f"ConcurrencyLimiter initialized with max_concurrent={max_concurrent}")
    
    async def __aenter__(self):
        """进入上下文管理器"""
        await self.semaphore.acquire()
        self.active_requests += 1
        self.total_requests += 1
        self.queue_size = self.max_concurrent - self.semaphore._value
        
        if self.queue_size > self.max_queue_size_reached:
            self.max_queue_size_reached = self.queue_size
        
        logger.debug(
            f"Request acquired semaphore. "
            f"Active: {self.active_requests}, "
            f"Queue: {self.queue_size}"
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器"""
        self.active_requests -= 1
        
        if exc_type is None:
            self.completed_requests += 1
        else:
            self.failed_requests += 1
        
        self.semaphore.release()
        
        logger.debug(
            f"Request released semaphore. "
            f"Active: {self.active_requests}, "
            f"Completed: {self.completed_requests}, "
            f"Failed: {self.failed_requests}"
        )
        
        return False
    
    async def execute(
        self,
        func: Callable,
        *args,
        request_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """执行函数并应用并发控制
        
        Args:
            func: 要执行的异步函数
            *args: 位置参数
            request_id: 请求ID（用于日志）
            **kwargs: 关键字参数
        
        Returns:
            函数执行结果
        """
        request_id = request_id or f"req_{self.total_requests + 1}"
        start_time = datetime.now()
        
        # 记录请求开始
        logger.info(
            f"Request {request_id} queued. "
            f"Active: {self.active_requests}/{self.max_concurrent}"
        )
        
        async with self:
            # 记录请求开始执行
            logger.info(f"Request {request_id} started execution")
            
            try:
                result = await func(*args, **kwargs)
                
                # 记录成功
                elapsed = (datetime.now() - start_time).total_seconds()
                self.request_history.append({
                    "request_id": request_id,
                    "status": "success",
                    "duration": elapsed,
                    "timestamp": start_time.isoformat()
                })
                
                logger.info(
                    f"Request {request_id} completed successfully in {elapsed:.2f}s"
                )
                
                return result
                
            except Exception as e:
                # 记录失败
                elapsed = (datetime.now() - start_time).total_seconds()
                self.request_history.append({
                    "request_id": request_id,
                    "status": "failed",
                    "error": str(e),
                    "duration": elapsed,
                    "timestamp": start_time.isoformat()
                })
                
                logger.error(
                    f"Request {request_id} failed after {elapsed:.2f}s: {e}"
                )
                
                raise
    
    def get_stats(self) -> dict:
        """获取并发统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "max_concurrent": self.max_concurrent,
            "active_requests": self.active_requests,
            "total_requests": self.total_requests,
            "completed_requests": self.completed_requests,
            "failed_requests": self.failed_requests,
            "current_queue_size": self.queue_size,
            "max_queue_size_reached": self.max_queue_size_reached,
            "success_rate": (
                self.completed_requests / self.total_requests 
                if self.total_requests > 0 else 0.0
            ),
            "failure_rate": (
                self.failed_requests / self.total_requests 
                if self.total_requests > 0 else 0.0
            )
        }
    
    def get_recent_requests(self, count: int = 10) -> list:
        """获取最近的请求历史
        
        Args:
            count: 返回的请求数量
        
        Returns:
            请求历史列表
        """
        return list(self.request_history)[-count:]
    
    def reset_stats(self):
        """重置统计信息（保留配置）"""
        self.total_requests = 0
        self.completed_requests = 0
        self.failed_requests = 0
        self.max_queue_size_reached = 0
        self.request_history.clear()
        logger.info("Concurrency statistics reset")


class RequestQueue:
    """请求队列
    
    提供FIFO请求队列，支持优先级和超时。
    """
    
    def __init__(self, max_size: Optional[int] = None):
        """
        Args:
            max_size: 队列最大大小（None表示无限制）
        """
        self.max_size = max_size
        self.queue = asyncio.Queue(maxsize=max_size or 0)
        self.processing = 0
        self.total_enqueued = 0
        self.total_processed = 0
        self.total_rejected = 0
    
    async def enqueue(
        self,
        request_id: str,
        func: Callable,
        *args,
        priority: int = 0,
        **kwargs
    ) -> bool:
        """将请求加入队列
        
        Args:
            request_id: 请求ID
            func: 要执行的函数
            *args: 位置参数
            priority: 优先级（数字越小优先级越高）
            **kwargs: 关键字参数
        
        Returns:
            是否成功加入队列
        """
        if self.max_size and self.queue.qsize() >= self.max_size:
            self.total_rejected += 1
            logger.warning(
                f"Request {request_id} rejected: queue full "
                f"({self.queue.qsize()}/{self.max_size})"
            )
            return False
        
        try:
            await self.queue.put({
                "request_id": request_id,
                "func": func,
                "args": args,
                "kwargs": kwargs,
                "priority": priority,
                "enqueued_at": datetime.now().isoformat()
            })
            
            self.total_enqueued += 1
            logger.info(
                f"Request {request_id} enqueued. "
                f"Queue size: {self.queue.qsize()}"
            )
            return True
            
        except asyncio.QueueFull:
            self.total_rejected += 1
            logger.warning(f"Request {request_id} rejected: queue full")
            return False
    
    async def dequeue(self) -> Optional[dict]:
        """从队列中取出请求
        
        Returns:
            请求字典，如果队列为空则返回None
        """
        try:
            request = await self.queue.get()
            self.processing += 1
            logger.debug(
                f"Request {request['request_id']} dequeued. "
                f"Processing: {self.processing}, "
                f"Queue size: {self.queue.qsize()}"
            )
            return request
        except asyncio.QueueEmpty:
            return None
    
    def mark_processed(self, request_id: str):
        """标记请求已处理
        
        Args:
            request_id: 请求ID
        """
        self.processing -= 1
        self.total_processed += 1
        self.queue.task_done()
        logger.debug(
            f"Request {request_id} processed. "
            f"Processing: {self.processing}"
        )
    
    def get_stats(self) -> dict:
        """获取队列统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "max_size": self.max_size,
            "current_size": self.queue.qsize(),
            "processing": self.processing,
            "total_enqueued": self.total_enqueued,
            "total_processed": self.total_processed,
            "total_rejected": self.total_rejected,
            "rejection_rate": (
                self.total_rejected / (self.total_enqueued + self.total_rejected)
                if (self.total_enqueued + self.total_rejected) > 0 else 0.0
            )
        }


# 全局并发限制器实例
_global_concurrency_limiter: Optional[ConcurrencyLimiter] = None


def get_concurrency_limiter() -> ConcurrencyLimiter:
    """获取全局并发限制器
    
    Returns:
        并发限制器实例
    """
    global _global_concurrency_limiter
    if _global_concurrency_limiter is None:
        # 从配置读取最大并发数
        try:
            from config.settings import settings
            max_concurrent = settings.performance.max_concurrent_requests
        except:
            max_concurrent = 10
        
        _global_concurrency_limiter = ConcurrencyLimiter(max_concurrent=max_concurrent)
    
    return _global_concurrency_limiter


def set_concurrency_limiter(limiter: ConcurrencyLimiter):
    """设置全局并发限制器
    
    Args:
        limiter: 并发限制器实例
    """
    global _global_concurrency_limiter
    _global_concurrency_limiter = limiter
