"""数据源适配器模块 - iFinD 优先，Tushare 降级"""

from .base_adapter import DataSourceAdapter
from .tushare_adapter import TushareAdapter
from .ifind_adapter import IFindAdapter, get_ifind_adapter

__all__ = [
    'DataSourceAdapter',
    'TushareAdapter',
    'IFindAdapter',
    'get_ifind_adapter',
]
