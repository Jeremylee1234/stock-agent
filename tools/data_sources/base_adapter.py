"""数据源适配器基类

定义统一的数据源接口，所有数据源适配器必须实现此接口。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import pandas as pd
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)


class DataSourceAdapter(ABC):
    """数据源适配器抽象基类
    
    所有数据源适配器必须继承此类并实现所有抽象方法。
    提供统一的错误处理和数据格式化接口。
    """
    
    def __init__(self, name: str):
        """初始化适配器
        
        Args:
            name: 数据源名称（如：tushare、akshare、ifind）
        """
        self.name = name
        self.logger = get_logger(f"{__name__}.{name}")
    
    @abstractmethod
    def get_stock_basic(self, stock_code: str) -> Dict[str, Any]:
        """获取股票基本信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            包含股票基本信息的字典，格式：
            {
                "stock_code": str,
                "stock_name": str,
                "industry": str,
                "market": str,  # 市场（如：主板、创业板）
                "list_date": str,  # 上市日期
                "data_source": str,  # 数据来源
                ...
            }
            
        Raises:
            Exception: 数据获取失败时抛出异常
        """
        pass
    
    @abstractmethod
    def get_daily_data(
        self,
        stock_code: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """获取日线数据
        
        Args:
            stock_code: 股票代码
            start_date: 开始日期（格式：YYYYMMDD）
            end_date: 结束日期（格式：YYYYMMDD）
            
        Returns:
            包含日线数据的DataFrame，列包括：
            - date: 日期
            - open: 开盘价
            - high: 最高价
            - low: 最低价
            - close: 收盘价
            - volume: 成交量
            - amount: 成交额
            - data_source: 数据来源
            
        Raises:
            Exception: 数据获取失败时抛出异常
        """
        pass
    
    @abstractmethod
    def get_financial_data(self, stock_code: str) -> Dict[str, Any]:
        """获取财务数据
        
        Args:
            stock_code: 股票代码
            
        Returns:
            包含财务数据的字典，格式：
            {
                "stock_code": str,
                "report_date": str,  # 报告期
                "revenue": float,  # 营业收入
                "net_profit": float,  # 净利润
                "total_assets": float,  # 总资产
                "total_liabilities": float,  # 总负债
                "data_source": str,
                ...
            }
            
        Raises:
            Exception: 数据获取失败时抛出异常
        """
        pass
    
    def handle_error(self, error: Exception, operation: str = "") -> Dict[str, Any]:
        """统一错误处理
        
        Args:
            error: 异常对象
            operation: 操作描述（可选）
            
        Returns:
            标准化的错误信息字典
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # 记录错误日志
        self.logger.error(
            f"数据源 {self.name} 错误 - 操作: {operation}, "
            f"类型: {error_type}, 消息: {error_message}",
            exc_info=True
        )
        
        return {
            "error": True,
            "error_type": error_type,
            "error_message": error_message,
            "data_source": self.name,
            "operation": operation,
            "timestamp": datetime.now().isoformat()
        }
    
    def add_data_source_tag(self, data: Any) -> Any:
        """为数据添加数据源标识
        
        Args:
            data: 原始数据（可以是dict或DataFrame）
            
        Returns:
            添加了data_source字段的数据
        """
        if isinstance(data, dict):
            data["data_source"] = self.name
        elif isinstance(data, pd.DataFrame):
            data["data_source"] = self.name
        return data
    
    def validate_stock_code(self, stock_code: str) -> bool:
        """验证股票代码格式
        
        Args:
            stock_code: 股票代码
            
        Returns:
            是否有效
        """
        if not stock_code or not isinstance(stock_code, str):
            return False
        
        # 移除空格
        stock_code = stock_code.strip()
        
        # 基本长度检查（6位数字或带市场后缀）
        if len(stock_code) < 6:
            return False
        
        return True
    
    def validate_date_format(self, date_str: str) -> bool:
        """验证日期格式（YYYYMMDD）
        
        Args:
            date_str: 日期字符串
            
        Returns:
            是否有效
        """
        if not date_str or not isinstance(date_str, str):
            return False
        
        try:
            datetime.strptime(date_str, "%Y%m%d")
            return True
        except ValueError:
            return False
    
    def format_stock_code(self, stock_code: str) -> str:
        """格式化股票代码（子类可以重写以适应不同格式）
        
        Args:
            stock_code: 原始股票代码
            
        Returns:
            格式化后的股票代码
        """
        return stock_code.strip().upper()
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.__class__.__name__}(name={self.name})"
    
    def __repr__(self) -> str:
        """对象表示"""
        return self.__str__()
