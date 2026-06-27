# 股票分析系统

基于 LangGraph 的智能股票分析系统，提供实时流式分析、技术指标计算、历史模式搜索等功能。

## 特性

- ✨ **实时流式输出**：通过 SSE 实时推送分析过程和结果
- 📊 **技术指标计算**：支持 MACD、KDJ、RSI、BOLL、均线等常用指标
- 🔍 **历史模式搜索**：基于价格形态、技术指标、筹码分布搜索相似走势
- 🎯 **多数据源集成**：整合 Tushare、Akshare、iFind 等数据源
- 🚀 **高性能**：支持并发请求、数据压缩、智能缓存
- 📝 **完整日志**：分级日志、审计追踪、错误处理
- 🔒 **数据真实性**：确保所有分析基于真实数据，不编造信息

## 系统架构

系统采用四节点工作流架构：

```
用户查询 → 分析问题 → 收集数据 → 分析数据 → 生成答案
```

### 核心组件

1. **API 层** (`api/`)
   - SSE 流式接口
   - REST API 端点
   - 事件类型定义
   - 数据模型

2. **工作流层** (`agents/`)
   - 问题分析节点
   - 数据收集节点
   - 数据分析节点
   - 答案生成节点

3. **工具层** (`tools/`)
   - 股票数据工具
   - 技术指标计算
   - 历史模式搜索
   - 数据源适配器

4. **基础设施** (`utils/`, `config/`)
   - 配置管理
   - 日志系统
   - 错误处理
   - 数据压缩
   - 并发控制

## 项目结构

```
stock-analysis-system/
├── api/                          # API 接口层
│   ├── __init__.py
│   ├── main.py                   # FastAPI 应用入口
│   ├── sse_routes.py             # SSE 流式接口
│   ├── event_types.py            # 事件类型定义
│   ├── models.py                 # API 数据模型
│   └── error_handlers.py         # 错误处理
├── agents/                       # 工作流层
│   ├── __init__.py
│   ├── stock_agent_main.py       # 主工作流（四节点）
│   ├── business_agent.py         # 业务智能体
│   ├── customer_agent.py         # 客户智能体
│   ├── analysis_agent.py         # 分析智能体
│   ├── stock_selection_agent.py  # 选股智能体
│   ├── state.py                  # 状态定义
│   ├── router.py                 # 路由器
│   └── graph.py                  # LangGraph 图
├── tools/                        # 工具层
│   ├── __init__.py
│   ├── stock_analysis_tool.py    # 股票分析工具
│   ├── technical_indicators.py   # 技术指标计算
│   ├── pattern_search.py         # 历史模式搜索
│   ├── tushare_pattern_search.py # Tushare 模式搜索
│   ├── enhanced_tools.py         # 增强工具
│   ├── search_tools.py           # 搜索工具
│   ├── financial_data_tools.py   # 金融数据工具
│   ├── mcp_tools.py              # MCP 工具
│   ├── database_tools.py         # 数据库工具
│   ├── tool_registry.py          # 工具注册管理
│   └── data_sources/             # 数据源适配器
│       ├── __init__.py
│       ├── base_adapter.py       # 基类
│       ├── tushare_adapter.py    # Tushare 适配器
│       ├── akshare_adapter.py    # Akshare 适配器
│       └── ifind_adapter.py      # iFind 适配器
├── utils/                        # 工具类
│   ├── __init__.py
│   ├── logger.py                 # 日志系统
│   ├── error_handler.py          # 错误处理
│   ├── data_validator.py         # 数据验证
│   ├── data_compression.py       # 数据压缩
│   ├── trace_utils.py            # 追踪工具
│   ├── timeout.py                # 超时控制
│   └── concurrency.py            # 并发控制
├── config/                       # 配置
│   ├── __init__.py
│   └── settings.py               # 配置管理（Pydantic）
├── tests/                        # 测试
│   ├── unit/                     # 单元测试
│   ├── integration/              # 集成测试
│   └── e2e/                      # 端到端测试
├── docs/                         # 文档
│   ├── API.md                    # API 文档
│   ├── FRONTEND_INTEGRATION.md   # 前端对接文档
│   ├── DEPLOYMENT.md             # 部署文档
│   └── PROJECT_STRUCTURE.md      # 项目结构说明
├── logs/                         # 日志目录
├── data_cache/                   # 缓存目录
├── .env                          # 环境变量（不提交）
├── .env.example                  # 环境变量模板
├── requirements.txt              # Python 依赖
├── Dockerfile                    # Docker 镜像
├── docker-compose.yml            # Docker Compose 配置
├── main.py                       # 应用入口
└── README.md                     # 说明文档
```

## Docker 部署（推荐）

GitHub + 服务器一键部署，详见 [DEPLOY.md](./DEPLOY.md)。

```bash
# 服务器上
git clone https://github.com/YOUR_USERNAME/stock-agent.git
cd stock-agent
cp .env.example .env && nano .env
bash scripts/deploy.sh
```

## 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone <repository-url>
cd stock-analysis-system

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必需的 API 密钥：

```bash
# 必需配置
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
ENVIRONMENT=development

# 推荐配置（用于历史模式搜索）
TUSHARE_TOKEN=your-tushare-token-here

# 可选配置
WIND_API_KEY=your-wind-api-key
SERPAPI_API_KEY=your-serpapi-key
BING_SEARCH_API_KEY=your-bing-search-key
```

### 3. 启动服务

```bash
# 开发模式（带自动重载）
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs

# 测试 SSE 连接
curl http://localhost:8000/api/v1/analysis/stream/test
```

## 使用示例

### 1. 通过 API 进行分析

```bash
curl -X POST http://localhost:8000/api/v1/analysis/stream \
  -H "Content-Type: application/json" \
  -d '{
    "query": "分析贵州茅台最近的走势",
    "session_id": "test-session-123"
  }'
```

### 2. 在 Python 中使用

```python
from agents.stock_agent_main import StockAnalysisGraph

# 创建工作流实例
graph = StockAnalysisGraph(
    trace=False,
    enable_data_compression=True
)

# 同步调用
result = graph.invoke(
    query="分析贵州茅台最近的走势",
    config={"configurable": {"thread_id": "session_1"}}
)

# 获取最终答案
final_answer = result.get("results", {}).get("final_answer", "")
print(final_answer)

# 流式调用
async for event in graph.astream_with_events(
    query="查找连续三天涨停的股票",
    config={"configurable": {"thread_id": "session_2"}}
):
    event_type = event.get("event_type")
    event_data = event.get("data")
    print(f"[{event_type}] {event_data}")
```

### 3. 前端对接示例

使用 `@microsoft/fetch-event-source` 库：

```javascript
import { fetchEventSource } from '@microsoft/fetch-event-source';

await fetchEventSource('http://localhost:8000/api/v1/analysis/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    query: '分析贵州茅台最近的走势',
    session_id: 'my-session-123'
  }),
  onmessage(event) {
    const data = JSON.parse(event.data);
    console.log(`[${event.event}]`, data);
    
    // 处理不同类型的事件
    switch (event.event) {
      case 'stage_start':
        console.log('阶段开始:', data.title);
        break;
      case 'tool_call':
        console.log('调用工具:', data.tool_name);
        break;
      case 'final_answer':
        console.log('最终答案:', data.content);
        break;
    }
  },
  onerror(err) {
    console.error('SSE 错误:', err);
  }
});
```

详细的前端对接示例请参考 [前端对接文档](docs/FRONTEND_INTEGRATION.md)。

## 核心功能

### 1. 技术指标计算

系统支持以下技术指标：

- **MACD**：DIF、DEA、MACD 柱，金叉/死叉信号
- **KDJ**：K 值、D 值、J 值，超买/超卖信号
- **RSI**：相对强弱指标，超买/超卖判断
- **BOLL**：布林带上轨、中轨、下轨
- **均线**：5/10/20/30/60/120/250 日均线
- **成交量指标**：OBV、量比

使用示例：

```python
from tools.technical_indicators import TechnicalIndicators
import pandas as pd

# 准备价格数据
prices = pd.Series([100, 102, 101, 103, 105, 104, 106])

# 计算 MACD
macd_result = TechnicalIndicators.calculate_macd(prices)
print(f"DIF: {macd_result['dif']}")
print(f"DEA: {macd_result['dea']}")
print(f"信号: {macd_result['signal']}")

# 计算 RSI
rsi_result = TechnicalIndicators.calculate_rsi(prices, period=14)
print(f"RSI: {rsi_result['rsi']}")
print(f"信号: {rsi_result['signal']}")
```

### 2. 历史模式搜索

搜索历史上相似的技术形态和走势：

```python
from tools.pattern_search import PatternSearchEngine

# 创建搜索引擎
engine = PatternSearchEngine(tushare_token="your-token")

# 搜索价格形态
result = engine.search_price_pattern(
    pattern_desc="连续三天涨停",
    start_date="20200101",
    end_date="20231231",
    max_results=20
)

# 查看匹配结果
for match in result['matches']:
    print(f"{match['stock_name']} ({match['stock_code']})")
    print(f"匹配日期: {match['match_date']}")
    print(f"后续5日涨跌幅: {match['future_performance']['5d_return']:.2%}")

# 查看统计摘要
stats = result['statistics']
print(f"平均5日收益率: {stats['avg_5d_return']:.2%}")
print(f"上涨概率: {stats['win_rate_5d']:.2%}")
```

### 3. 多数据源集成

系统整合了多个数据源，自动选择最优数据源：

```python
from tools.data_sources import get_adapter

# 获取 Tushare 适配器
tushare = get_adapter('tushare')
daily_data = tushare.get_daily_data('600519.SH', '20240101', '20240131')

# 获取 Akshare 适配器
akshare = get_adapter('akshare')
stock_info = akshare.get_stock_basic('600519')

# 获取 iFind 适配器
ifind = get_adapter('ifind')
financial_data = ifind.get_financial_data('600519.SH')
```

### 4. 实时流式输出

系统通过 SSE 推送 11 种事件类型：

1. `workflow_start` - 工作流开始
2. `stage_start` - 阶段开始
3. `stage_progress` - 阶段进度
4. `tool_call` - 工具调用
5. `tool_result` - 工具结果
6. `analysis_chunk` - 分析内容增量
7. `stage_complete` - 阶段完成
8. `final_answer` - 最终答案
9. `error` - 错误
10. `workflow_complete` - 工作流完成
11. `execution_plan` - 执行计划

详细的事件格式请参考 [API 文档](docs/API.md)。

## 配置说明

系统使用 Pydantic 进行配置管理，支持环境变量和配置文件。

### 主要配置项

```python
# LLM 配置
LLM__DEFAULT_MODEL=deepseek-chat
LLM__TEMPERATURE=0.7
LLM__MAX_TOKENS=4000
LLM__TIMEOUT=60

# 性能配置
PERFORMANCE__MAX_CONCURRENT_REQUESTS=10
PERFORMANCE__REQUEST_TIMEOUT=300
PERFORMANCE__DATA_COMPRESSION_THRESHOLD=20000
PERFORMANCE__MAX_MESSAGE_HISTORY=30

# 日志配置
LOG__LOG_LEVEL=INFO
LOG__LOG_DIR=logs
LOG__LOG_TO_CONSOLE=true
LOG__LOG_TO_FILE=true

# API 配置
API__HOST=0.0.0.0
API__PORT=8000
API__CORS_ORIGINS=["*"]
```

完整的配置说明请参考 `config/settings.py`。

## 部署

### Docker 部署

```bash
# 构建镜像
docker build -t stock-analysis-system:latest .

# 运行容器
docker run -d \
  --name stock-analysis \
  -p 8000:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data_cache:/app/data_cache \
  --env-file .env \
  stock-analysis-system:latest
```

### Docker Compose 部署

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f stock-analysis

# 停止服务
docker-compose down
```

详细的部署指南请参考 [部署文档](docs/DEPLOYMENT.md)。

## 前后端对接

### SSE 事件处理

前端通过 EventSource 或 fetch API 接收 SSE 事件：

```javascript
// 使用 fetch-event-source 库
import { fetchEventSource } from '@microsoft/fetch-event-source';

await fetchEventSource('http://localhost:8000/api/v1/analysis/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: '分析贵州茅台' }),
  
  onmessage(event) {
    const data = JSON.parse(event.data);
    
    switch (event.event) {
      case 'workflow_start':
        console.log('分析开始');
        break;
      case 'stage_start':
        console.log('当前阶段:', data.title);
        break;
      case 'tool_call':
        console.log('调用工具:', data.tool_name);
        break;
      case 'final_answer':
        console.log('最终答案:', data.content);
        break;
    }
  }
});
```

### React Hook 示例

```typescript
import { useStockAnalysis } from './hooks/useStockAnalysis';

function StockAnalysisComponent() {
  const { isStreaming, events, startAnalysis, stopAnalysis } = useStockAnalysis();
  
  const handleSubmit = (query: string) => {
    startAnalysis(query);
  };
  
  return (
    <div>
      <input onChange={(e) => setQuery(e.target.value)} />
      <button onClick={() => handleSubmit(query)}>
        {isStreaming ? '分析中...' : '开始分析'}
      </button>
      {/* 显示事件和结果 */}
    </div>
  );
}
```

完整的前端对接示例请参考 [前端对接文档](docs/FRONTEND_INTEGRATION.md)。

## 文档

- [API 文档](docs/API.md) - 完整的 API 接口说明
- [前端对接文档](docs/FRONTEND_INTEGRATION.md) - 前端集成指南和示例
- [部署文档](docs/DEPLOYMENT.md) - 部署配置和运维指南
- [项目结构说明](docs/PROJECT_STRUCTURE.md) - 详细的项目结构说明

## 测试

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 运行端到端测试
pytest tests/e2e/

# 查看测试覆盖率
pytest --cov=. --cov-report=html
```

## 性能优化

系统实现了多项性能优化：

1. **并发控制**：限制最大并发请求数，防止资源耗尽
2. **数据压缩**：自动压缩超长工具输出，减少内存占用
3. **智能缓存**：缓存常用数据，减少 API 调用
4. **消息修剪**：自动修剪历史消息，避免上下文溢出
5. **超时控制**：为工具调用和工作流设置超时，防止长时间阻塞
6. **异步处理**：使用异步 I/O 提高并发性能

## 监控与日志

### 日志系统

系统使用 loguru 实现分级日志：

```python
from utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

日志配置：

- 日志级别：DEBUG、INFO、WARNING、ERROR、CRITICAL
- 日志输出：控制台 + 文件
- 日志轮转：每天轮转，保留 30 天
- 日志格式：JSON 格式，便于解析

### 监控端点

```bash
# 健康检查
GET /health

# 服务统计
GET /api/v1/analysis/stats

# 事件类型列表
GET /api/v1/analysis/event-types
```

## 故障排查

### 常见问题

1. **服务无法启动**
   ```bash
   # 检查端口占用
   lsof -i :8000
   
   # 检查配置
   python -c "from config.settings import settings; print(settings)"
   ```

2. **SSE 连接断开**
   - 检查 Nginx 配置（如果使用）
   - 确保 `proxy_buffering off`
   - 增加 `proxy_read_timeout`

3. **内存占用过高**
   - 减少并发数：`PERFORMANCE__MAX_CONCURRENT_REQUESTS=5`
   - 减少消息历史：`PERFORMANCE__MAX_MESSAGE_HISTORY=20`
   - 启用数据压缩：`PERFORMANCE__ENABLE_DATA_COMPRESSION=true`

4. **API 调用超时**
   - 增加超时时间：`PERFORMANCE__REQUEST_TIMEOUT=600`
   - 增加 LLM 超时：`LLM__TIMEOUT=120`

### 日志分析

```bash
# 查看最近的错误
tail -n 100 logs/stock_analysis.log | grep ERROR

# 统计错误类型
cat logs/stock_analysis.log | jq -r 'select(.level == "ERROR") | .message' | sort | uniq -c

# 查看慢请求
cat logs/stock_analysis.log | jq 'select(.duration_ms > 10000)'
```

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 开发流程

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -am 'Add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

### 代码规范

- 遵循 PEP 8 代码风格
- 为所有函数添加 docstring
- 为所有类添加类级别文档
- 使用类型注解提高代码可读性
- 编写单元测试覆盖新功能

## 许可证

内部使用

## 联系方式

如有问题或建议，请联系开发团队或提交 Issue。

---

**注意事项**：

1. **API 密钥安全**：不要将 API 密钥提交到版本控制系统
2. **数据准确性**：所有分析结果仅供参考，不构成投资建议
3. **API 限流**：注意各 API 的调用频率限制
4. **客户隐私**：严格保护客户信息，不泄露敏感数据
5. **生产环境**：生产环境请使用 HTTPS 和适当的安全配置

