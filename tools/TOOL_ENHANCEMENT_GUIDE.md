# 工具增强使用指南

本文档说明如何使用增强的工具系统，包括工具注册、统一错误处理、数据验证和数据来源标识。

## 概述

工具增强系统提供以下功能：

1. **工具注册管理器** (`tool_registry.py`): 统一管理所有工具
2. **增强的工具包装器** (`enhanced_tools.py`): 为工具添加错误处理、验证和数据来源标识
3. **统一错误处理** (`utils/error_handler.py`): ToolExecutor类
4. **数据验证** (`utils/data_validator.py`): DataValidator类

## 快速开始

### 1. 注册工具

所有工具在 `stock_analysis_tool.py` 中已自动注册。如果需要注册新工具：

```python
from tools.tool_registry import register_tool

# 注册工具
register_tool(
    name="my_tool",
    func=my_tool_function,
    description="工具描述",
    category="data_source",  # 或 "indicator", "pattern_search", "general"
    data_source="ifind",     # 或 "akshare", "tushare"
    requires_auth=True,
    parameters={
        "param1": {"type": "str", "description": "参数1描述"}
    },
    tags=["tag1", "tag2"]
)
```

### 2. 使用增强的工具执行

#### 方式1：通过工具注册中心执行

```python
from tools.tool_registry import get_global_registry

registry = get_global_registry()

# 异步执行
result = await registry.execute(
    "get_stock_history_price",
    stock_code="600519.SH",
    start_date="20240101",
    end_date="20240131",
    validate_result=True,      # 自动验证结果
    add_data_source=True       # 自动添加数据来源标识
)

# 同步执行
result = registry.execute_sync(
    "get_stock_history_price",
    stock_code="600519.SH",
    start_date="20240101",
    end_date="20240131"
)
```

#### 方式2：通过增强包装器执行

```python
from tools.enhanced_tools import execute_tool

result = await execute_tool(
    "get_stock_history_price",
    stock_code="600519.SH",
    start_date="20240101",
    end_date="20240131",
    validate_result=True,
    add_data_source=True
)
```

### 3. 结果格式

所有工具执行结果都遵循统一格式：

#### 成功结果

```python
{
    "success": True,
    "data": {
        # 工具返回的实际数据
        "data_source": "ifind",  # 自动添加的数据来源
        ...
    },
    "tool_name": "get_stock_history_price",
    "timestamp": "2024-01-01T00:00:00",
    "duration_ms": 1234,
    "validation": {
        "is_valid": True,
        "message": "验证通过"
    }
}
```

#### 失败结果

```python
{
    "success": False,
    "error_code": "TOOL_TIMEOUT",
    "error_message": "工具调用超时",
    "error_detail": "详细错误信息",
    "error_type": "TimeoutError",
    "tool_name": "get_stock_history_price",
    "recoverable": True,
    "retry_suggested": True,
    "timestamp": "2024-01-01T00:00:00"
}
```

## 工具分类

### data_source
数据源工具，用于获取股票数据：
- `get_stock_history_price`: 历史价格数据（iFind）
- `get_stock_daily_indicators`: 基本面数据（akshare）
- `get_stock_chip_indicators`: 筹码分布数据（akshare）
- `get_stock_news_indicators`: 新闻研报数据（akshare）

### indicator
技术指标计算工具：
- `calculate_technical_indicators`: 计算MACD、KDJ、RSI、BOLL、均线等

### pattern_search
历史模式搜索工具：
- `search_similar_pattern`: 搜索历史相似走势

## 错误处理

### 错误代码

系统定义了以下标准错误代码：

- `TOOL_TIMEOUT`: 工具调用超时
- `TOOL_CONNECTION_ERROR`: 连接失败
- `TOOL_AUTH_ERROR`: 认证失败
- `TOOL_ERROR`: 通用工具错误
- `DATA_VALIDATION_ERROR`: 数据验证失败
- `DATA_FORMAT_ERROR`: 数据格式错误
- `INSUFFICIENT_DATA`: 数据不足

### 重试机制

ToolExecutor 自动处理可恢复的错误并重试：

```python
# 默认最多重试3次
executor = ToolExecutor(max_retries=3, retry_delay=1.0)

result = await executor.execute_tool(
    my_tool_function,
    *args,
    enable_retry=True,  # 启用重试
    **kwargs
)
```

## 数据验证

### 自动验证

工具执行时会自动验证结果：

- **股票价格数据**: 检查必需字段、价格合理性、高开低收关系
- **技术指标**: 检查指标值范围、必需字段
- **日期格式**: 验证日期字符串格式

### 手动验证

```python
from utils.data_validator import DataValidator

validator = DataValidator()

# 验证股票价格数据
is_valid, message = validator.validate_stock_price_data(data)

# 验证技术指标结果
is_valid, message = validator.validate_technical_indicator_result(
    result, 
    indicator_type="RSI"
)

# 检测数据异常
anomalies = validator.detect_anomalies(df)
```

## 数据缓存

系统提供简单的内存缓存机制：

```python
from tools.stock_analysis_tool import _global_cache

# 获取缓存
cached_data = _global_cache.get("cache_key")

# 设置缓存
_global_cache.set("cache_key", data)

# 清空缓存
_global_cache.clear()

# 获取统计信息
stats = _global_cache.get_stats()
```

缓存默认过期时间为1小时（3600秒）。

## 查询工具

### 列出所有工具

```python
from tools.tool_registry import get_global_registry

registry = get_global_registry()

# 列出所有工具
all_tools = registry.list_tools()

# 按分类过滤
data_source_tools = registry.list_tools(category="data_source")

# 按数据源过滤
ifind_tools = registry.list_tools(data_source="ifind")

# 按标签过滤
price_tools = registry.list_tools(tags=["price"])
```

### 搜索工具

```python
# 搜索工具
results = registry.search_tools("price")

# 获取工具信息
tool_info = registry.get_tool_info("get_stock_history_price")

# 获取统计信息
stats = registry.get_statistics()
```

## 最佳实践

### 1. 始终使用注册中心执行工具

```python
# 推荐
result = await registry.execute("tool_name", ...)

# 不推荐
result = await tool_function(...)
```

### 2. 检查执行结果

```python
result = await registry.execute("tool_name", ...)

if result.get("success"):
    data = result.get("data")
    # 处理数据
else:
    error_code = result.get("error_code")
    error_message = result.get("error_message")
    # 处理错误
```

### 3. 利用数据来源标识

```python
result = await registry.execute("tool_name", ..., add_data_source=True)

if result.get("success"):
    data = result.get("data")
    data_source = data.get("data_source")  # "ifind", "akshare", "tushare"
    # 根据数据来源进行不同处理
```

### 4. 启用数据验证

```python
result = await registry.execute("tool_name", ..., validate_result=True)

if result.get("success"):
    validation = result.get("validation", {})
    if validation.get("is_valid"):
        # 数据有效，继续处理
        pass
    else:
        # 数据验证失败，记录警告
        logger.warning(f"Validation failed: {validation.get('message')}")
```

## 迁移现有代码

### 步骤1：确保工具已注册

检查 `stock_analysis_tool.py` 中的 `register_all_tools()` 函数，确保你的工具已注册。

### 步骤2：更新工具调用

将直接调用工具函数改为通过注册中心调用：

```python
# 旧代码
result = await get_stock_history_price("600519.SH", "20240101", "20240131")

# 新代码
from tools.tool_registry import get_global_registry
registry = get_global_registry()
result = await registry.execute(
    "get_stock_history_price",
    stock_code="600519.SH",
    start_date="20240101",
    end_date="20240131"
)
```

### 步骤3：更新错误处理

```python
# 旧代码
try:
    result = await get_stock_history_price(...)
    if 'error' in result:
        # 处理错误
except Exception as e:
    # 处理异常

# 新代码
result = await registry.execute("get_stock_history_price", ...)
if not result.get("success"):
    error_code = result.get("error_code")
    error_message = result.get("error_message")
    # 统一的错误处理
```

## 故障排查

### 工具未找到

```python
result = await registry.execute("my_tool", ...)
# 返回: {"success": False, "error_code": "TOOL_NOT_FOUND", ...}
```

解决方法：确保工具已注册。

### 数据验证失败

```python
result = await registry.execute("tool_name", ..., validate_result=True)
# validation.is_valid = False
```

解决方法：检查工具返回的数据格式和内容。

### 工具执行超时

```python
# 返回: {"success": False, "error_code": "TOOL_TIMEOUT", ...}
```

解决方法：检查网络连接，或增加超时时间。

## 参考

- `tools/tool_registry.py`: 工具注册管理器实现
- `tools/enhanced_tools.py`: 增强工具包装器实现
- `utils/error_handler.py`: 统一错误处理实现
- `utils/data_validator.py`: 数据验证实现
- `tools/stock_analysis_tool.py`: 工具注册示例
