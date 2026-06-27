"""
统一日志工具模块

提供分级日志记录功能，支持文件和控制台输出，实现日志轮转机制。
满足需求 9.4, 9.7, 9.8
"""

import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional
from datetime import datetime
import json


class StockAnalysisLogger:
    """股票分析系统统一日志器"""
    
    _instances = {}
    
    def __init__(
        self,
        name: str = "stock_analysis",
        log_dir: str = "./logs",
        log_level: str = "INFO",
        console_output: bool = True,
        file_output: bool = True,
        max_bytes: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        rotation_type: str = "size"  # "size" or "time"
    ):
        """
        初始化日志器
        
        Args:
            name: 日志器名称
            log_dir: 日志文件目录
            log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            console_output: 是否输出到控制台
            file_output: 是否输出到文件
            max_bytes: 单个日志文件最大字节数（用于size rotation）
            backup_count: 保留的备份文件数量
            rotation_type: 轮转类型 ("size" 按大小, "time" 按时间)
        """
        self.name = name
        self.log_dir = log_dir
        self.logger = logging.getLogger(name)
        
        # 设置日志级别
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 创建日志目录
            if file_output:
                os.makedirs(log_dir, exist_ok=True)
            
            # 定义日志格式
            formatter = logging.Formatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            
            # 控制台处理器
            if console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(level)
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
            
            # 文件处理器
            if file_output:
                log_file = os.path.join(log_dir, f"{name}.log")
                
                if rotation_type == "size":
                    # 按大小轮转
                    file_handler = RotatingFileHandler(
                        log_file,
                        maxBytes=max_bytes,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )
                elif rotation_type == "time":
                    # 按时间轮转（每天）
                    file_handler = TimedRotatingFileHandler(
                        log_file,
                        when='midnight',
                        interval=1,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )
                else:
                    # 默认使用按大小轮转
                    file_handler = RotatingFileHandler(
                        log_file,
                        maxBytes=max_bytes,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )
                
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
    
    @classmethod
    def get_logger(
        cls,
        name: str = "stock_analysis",
        **kwargs
    ) -> 'StockAnalysisLogger':
        """
        获取日志器实例（单例模式）
        
        Args:
            name: 日志器名称
            **kwargs: 其他初始化参数
        
        Returns:
            StockAnalysisLogger实例
        """
        if name not in cls._instances:
            cls._instances[name] = cls(name=name, **kwargs)
        return cls._instances[name]
    
    def debug(self, message: str, **kwargs):
        """记录DEBUG级别日志"""
        self.logger.debug(message, extra=kwargs)
    
    def info(self, message: str, **kwargs):
        """记录INFO级别日志"""
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录WARNING级别日志"""
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs):
        """记录ERROR级别日志
        
        Args:
            message: 日志消息
            exc_info: 是否包含异常堆栈信息
            **kwargs: 额外的上下文信息
        """
        self.logger.error(message, exc_info=exc_info, extra=kwargs)
    
    def critical(self, message: str, exc_info: bool = False, **kwargs):
        """记录CRITICAL级别日志"""
        self.logger.critical(message, exc_info=exc_info, extra=kwargs)
    
    def log_tool_call(
        self,
        tool_name: str,
        args: dict,
        status: str = "started",
        duration_ms: Optional[int] = None,
        result_summary: Optional[str] = None,
        error: Optional[str] = None
    ):
        """
        记录工具调用的详细信息
        满足需求 9.2, 9.5, 9.6
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            status: 调用状态 (started, success, error)
            duration_ms: 耗时（毫秒）
            result_summary: 结果摘要
            error: 错误信息
        """
        log_data = {
            "event_type": "tool_call",
            "tool_name": tool_name,
            "args": self._sanitize_args(args),
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        
        if result_summary:
            log_data["result_summary"] = result_summary
        
        if error:
            log_data["error"] = error
        
        log_message = f"Tool call: {tool_name} - {status}"
        if duration_ms:
            log_message += f" ({duration_ms}ms)"
        
        if status == "error":
            self.error(log_message, extra={"tool_call_data": json.dumps(log_data, ensure_ascii=False)})
        else:
            self.info(log_message, extra={"tool_call_data": json.dumps(log_data, ensure_ascii=False)})
    
    def log_workflow_stage(
        self,
        stage: str,
        status: str = "started",
        duration_ms: Optional[int] = None,
        summary: Optional[str] = None
    ):
        """
        记录工作流阶段信息
        满足需求 9.5
        
        Args:
            stage: 阶段名称
            status: 阶段状态 (started, completed, error)
            duration_ms: 耗时（毫秒）
            summary: 阶段摘要
        """
        log_data = {
            "event_type": "workflow_stage",
            "stage": stage,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        if duration_ms is not None:
            log_data["duration_ms"] = duration_ms
        
        if summary:
            log_data["summary"] = summary
        
        log_message = f"Workflow stage: {stage} - {status}"
        if duration_ms:
            log_message += f" ({duration_ms}ms)"
        
        self.info(log_message, extra={"workflow_data": json.dumps(log_data, ensure_ascii=False)})
    
    def log_user_query(
        self,
        query: str,
        session_id: str,
        status: str = "started"
    ):
        """
        记录用户查询
        满足需求 9.5
        
        Args:
            query: 用户查询内容
            session_id: 会话ID
            status: 查询状态 (started, completed, error)
        """
        log_data = {
            "event_type": "user_query",
            "query": query[:200],  # 限制长度
            "session_id": session_id,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        log_message = f"User query {status}: {query[:100]}"
        self.info(log_message, extra={"query_data": json.dumps(log_data, ensure_ascii=False)})
    
    def _sanitize_args(self, args: dict) -> dict:
        """
        清理敏感参数信息
        
        Args:
            args: 原始参数字典
        
        Returns:
            清理后的参数字典
        """
        sanitized = {}
        sensitive_keys = ['token', 'password', 'api_key', 'secret', 'auth']
        
        for key, value in args.items():
            # 检查是否是敏感键
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            else:
                # 限制值的长度
                if isinstance(value, str) and len(value) > 200:
                    sanitized[key] = value[:200] + "...(truncated)"
                else:
                    sanitized[key] = value
        
        return sanitized


# 全局默认日志器实例
_default_logger: Optional[StockAnalysisLogger] = None


def get_logger(name: str = "stock_analysis", **kwargs) -> StockAnalysisLogger:
    """
    获取日志器实例的便捷函数
    
    Args:
        name: 日志器名称
        **kwargs: 其他初始化参数
    
    Returns:
        StockAnalysisLogger实例
    """
    return StockAnalysisLogger.get_logger(name=name, **kwargs)


def setup_default_logger(**kwargs) -> StockAnalysisLogger:
    """
    设置全局默认日志器
    
    Args:
        **kwargs: 日志器初始化参数
    
    Returns:
        配置好的日志器实例
    """
    global _default_logger
    _default_logger = get_logger(**kwargs)
    return _default_logger


def get_default_logger() -> StockAnalysisLogger:
    """
    获取全局默认日志器
    
    Returns:
        默认日志器实例
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_default_logger()
    return _default_logger
