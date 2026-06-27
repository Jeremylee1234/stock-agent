# 项目结构说明

## 目录结构

```
stock-analysis-system/
├── api/                          # API接口层
│   └── __init__.py
├── agents/                       # 智能体层
│   ├── __init__.py
│   ├── analysis_agent.py        # 金融分析智能体
│   ├── business_agent.py        # 公司业务智能体
│   ├── customer_agent.py        # 客户信息智能体
│   ├── graph.py                 # LangGraph主图
│   ├── router.py                # 智能体路由器
│   ├── state.py                 # 状态定义
│   └── stock_agent_main.py      # 股票分析主工作流
├── config/                       # 配置管理
│   ├── __init__.py
│   └── settings.py              # 配置文件（原config.py）
├── tools/                        # 工具层
│   ├── __init__.py
│   ├── background_tools.py      # 背景工具
│   ├── database_tools.py        # 数据库工具
│   ├── financial_data_tools.py  # 金融数据工具
│   ├── mcp_tools.py             # MCP工具
│   ├── search_tools.py          # 搜索工具
│   ├── stock_analysis_tool.py   # 股票分析工具（MCP服务器）
│   └── tushare_pattern_search.py # Tushare模式搜索
├── utils/                        # 工具类
│   ├── __init__.py
│   ├── data_compression.py      # 数据压缩工具
│   └── trace_utils.py           # 追踪工具
├── tests/                        # 测试
│   ├── __init__.py
│   ├── unit/                    # 单元测试
│   │   └── __init__.py
│   ├── integration/             # 集成测试
│   │   └── __init__.py
│   └── e2e/                     # 端到端测试
│       └── __init__.py
├── docs/                         # 文档
│   └── PROJECT_STRUCTURE.md     # 项目结构说明（本文件）
├── data_cache/                   # 数据缓存目录
├── tokenizer/                    # 分词器
├── main.py                       # 应用入口
├── requirements.txt              # 依赖包
├── .env                          # 环境变量
└── README.md                     # 项目说明

```

## 模块说明

### 1. API接口层 (api/)
负责提供HTTP接口，包括SSE流式接口和REST接口。

**主要文件：**
- 待实现：`sse_routes.py` - SSE流式接口
- 待实现：`rest_routes.py` - REST接口
- 待实现：`models.py` - API数据模型

### 2. 智能体层 (agents/)
包含所有智能体的实现和工作流定义。

**主要文件：**
- `stock_agent_main.py` - 股票分析主工作流（四节点：分析问题→收集数据→分析数据→生成答案）
- `graph.py` - 多智能体LangGraph状态机
- `router.py` - 智能体路由器
- `state.py` - 状态定义
- `analysis_agent.py` - 金融分析智能体
- `business_agent.py` - 公司业务智能体
- `customer_agent.py` - 客户信息智能体
- `stock_selection_agent.py` - 选股智能体

### 3. 配置管理 (config/)
集中管理所有配置项。

**主要文件：**
- `settings.py` - 配置文件（包含API密钥、模型配置等）

### 4. 工具层 (tools/)
提供各种数据获取和处理工具。

**主要文件：**
- `stock_analysis_tool.py` - 股票分析工具（MCP服务器，包含同花顺iFind、akshare接口）
- `tushare_pattern_search.py` - Tushare历史模式搜索
- `financial_data_tools.py` - 金融数据工具
- `database_tools.py` - 数据库工具
- `mcp_tools.py` - MCP工具
- `search_tools.py` - 搜索工具
- `background_tools.py` - 背景工具

### 5. 工具类 (utils/)
提供通用工具函数。

**主要文件：**
- `data_compression.py` - 数据压缩工具（处理超长数据）
- `trace_utils.py` - 追踪工具（用于调试和日志）

### 6. 测试 (tests/)
包含所有测试代码。

**目录结构：**
- `unit/` - 单元测试
- `integration/` - 集成测试
- `e2e/` - 端到端测试

### 7. 文档 (docs/)
项目文档。

**主要文件：**
- `PROJECT_STRUCTURE.md` - 项目结构说明（本文件）
- 待实现：`API.md` - API文档
- 待实现：`FRONTEND_INTEGRATION.md` - 前端对接文档
- 待实现：`DEPLOYMENT.md` - 部署文档

## 导入路径变更

### 旧导入路径 → 新导入路径

```python
# 配置
from config import DEEPSEEK_API_KEY
→ from config.settings import DEEPSEEK_API_KEY

# 状态
from state import AgentState
→ from agents.state import AgentState

# 路由器
from router import Router
→ from agents.router import Router

# 图
from graph import MultiAgentGraph
→ from agents.graph import MultiAgentGraph

# 数据压缩
from data_compression import DataCompressor
→ from utils.data_compression import DataCompressor

# 追踪工具
from trace_utils import CallbackTracer
→ from utils.trace_utils import CallbackTracer

# 股票分析工具
from stock_analysis_tool import get_stock_history_price
→ from tools.stock_analysis_tool import get_stock_history_price

# Tushare模式搜索
from tushare_pattern_search import search_similar_pattern
→ from tools.tushare_pattern_search import search_similar_pattern
```

## 主要入口文件

### main.py
多智能体系统的主入口文件，支持示例模式和交互模式。

**使用方法：**
```bash
# 运行示例
python main.py

# 交互模式
python main.py --interactive
```

### agents/stock_agent_main.py
股票分析工作流的主文件，实现了四节点工作流：
1. 分析问题
2. 收集数据
3. 分析数据
4. 生成答案

## 下一步工作

根据设计文档，接下来需要实现：

1. **配置管理优化** (Task 2)
   - 实现 `config/settings.py` 的pydantic验证
   - 支持环境变量和配置文件

2. **日志系统** (Task 3)
   - 实现 `utils/logger.py`
   - 集成到现有代码

3. **错误处理框架** (Task 4)
   - 实现 `utils/error_handler.py`
   - 实现 `utils/data_validator.py`

4. **数据源适配器** (Task 5)
   - 创建 `tools/data_sources/` 目录
   - 实现各数据源适配器

5. **技术指标计算** (Task 6)
   - 实现 `tools/technical_indicators.py`

6. **历史模式搜索引擎** (Task 7)
   - 实现 `tools/pattern_search.py`

7. **SSE接口** (Task 10)
   - 实现 `api/main.py`
   - 实现 `api/sse_routes.py`

## 注意事项

1. 所有新代码应遵循新的目录结构
2. 导入路径已全部更新，确保使用新的导入路径
3. 测试代码应放在对应的测试目录中
4. 文档应及时更新到 `docs/` 目录
