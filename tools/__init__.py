"""
工具模块（tools/__init__.py）

这段代码的作用是对工具包目录下的各个工具类进行导入和统一管理，便于其他模块直接通过 from tools import ... 方式访问这些工具类。

具体解释如下：
1. 从当前包（tools）的四个子模块导入了四个工具类，分别是：
   - SearchTools：搜索相关的工具类，例如调用SerpAPI、Bing等搜索引擎。
   - FinancialDataTools：金融数据处理相关工具类（例如获取行情、指标、量化数据等）。
   - MCPTools：公司自研的MCP系统相关工具类（如获取策略、产品、中台信息等）。
   - DatabaseTools：数据库操作相关工具类，如查询客户账户信息等。

2. 通过 `__all__` 变量，指定从该包导入（import *）时可用的对象列表。这也是对外统一的工具接口。
   - 这样写法有助于 IDE 自动补全和明确可用工具类，防止内部引用的其它类被意外暴露。
   - 例如，`from tools import *` 时，只会导入 `__all__` 里声明的四个主工具类。

总结：本文件是 tools 工具包的总入口，负责统一出口四个核心工具类，方便其他模块调用和统一管理。
"""
from .search_tools import SearchTools
from .financial_data_tools import FinancialDataTools
from .mcp_tools import MCPTools
from .database_tools import DatabaseTools

__all__ = [
    "SearchTools",
    "FinancialDataTools",
    "MCPTools",
    "DatabaseTools"
]

