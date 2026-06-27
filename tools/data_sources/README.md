# 数据源适配器

本模块提供统一的数据源接口，支持多个数据源（Tushare、Akshare、iFind）。

## 架构设计

### 基类：DataSourceAdapter

所有数据源适配器都继承自 `DataSourceAdapter` 抽象基类，该基类定义了统一的接口：

- `get_stock_basic(stock_code)`: 获取股票基本信息
- `get_daily_data(stock_code, start_date, end_date)`: 获取日线数据
- `get_financial_data(stock_code)`: 获取财务数据
- `handle_error(error, operation)`: 统一错误处理
- `validate_stock_code(stock_code)`: 验证股票代码
- `validate_date_format(date_str)`: 验证日期格式
- `format_stock_code(stock_code)`: 格式化股票代码

## 支持的数据源

### 1. TushareAdapter

**特点**：
- 数据质量高，覆盖全面
- 需要 Tushare Pro Token
- 支持重试机制和错误处理

**配置**：
```python
# 环境变量
DATA_SOURCE__TUSHARE_TOKEN=your_token_here
DATA_SOURCE__TUSHARE_RETRY_COUNT=3
DATA_SOURCE__TUSHARE_TIMEOUT=30
```

**使用示例**：
```python
from tools.data_sources import TushareAdapter

# 初始化（自动从配置读取token）
adapter = TushareAdapter()

# 或手动指定token
adapter = TushareAdapter(token="your_token")

# 获取股票基本信息
basic_info = adapter.get_stock_basic("600519")
print(basic_info)

# 获取日线数据
daily_data = adapter.get_daily_data("600519", "20240101", "20240131")
print(daily_data)

# 获取财务数据
financial_data = adapter.get_financial_data("600519")
print(financial_data)

# 获取股票列表
stock_list = adapter.get_stock_list(market="主板")
print(stock_list)
```

**股票代码格式**：
- 输入：`600519` 或 `600519.SH`
- 输出：`600519.SH`（自动添加交易所后缀）

### 2. AkshareAdapter

**特点**：
- 免费开源，无需API密钥
- 数据来源广泛
- 支持资金流向、筹码分布、新闻研报等

**使用示例**：
```python
from tools.data_sources import AkshareAdapter

# 初始化（无需配置）
adapter = AkshareAdapter()

# 获取股票基本信息
basic_info = adapter.get_stock_basic("600519")
print(basic_info)

# 获取日线数据
daily_data = adapter.get_daily_data("600519", "20240101", "20240131")
print(daily_data)

# 获取财务数据
financial_data = adapter.get_financial_data("600519")
print(financial_data)

# 获取资金流向（最近30天）
fund_flow = adapter.get_fund_flow("600519", days=30)
print(fund_flow)

# 获取筹码分布
chip_dist = adapter.get_chip_distribution("600519", days=30)
print(chip_dist)

# 获取十大流通股东
top_holders = adapter.get_top_10_holders("600519")
print(top_holders)

# 获取新闻
news = adapter.get_news("600519", limit=10)
print(news)

# 获取研报
reports = adapter.get_research_reports("600519", limit=5)
print(reports)
```

**股票代码格式**：
- 输入：`600519` 或 `600519.SH`
- 输出：`600519`（移除交易所后缀）

### 3. IFindAdapter

**特点**：
- 同花顺官方数据源
- 支持HTTP API和本地DLL两种模式
- 数据实时性好，支持智能选股

**配置**：
```python
# 环境变量（HTTP模式）
DATA_SOURCE__WIND_API_KEY=your_api_key
DATA_SOURCE__WIND_USERNAME=your_username
DATA_SOURCE__WIND_PASSWORD=your_password
```

**使用示例**：
```python
from tools.data_sources import IFindAdapter

# 初始化（HTTP模式，推荐）
adapter = IFindAdapter(use_http=True)

# 或手动指定配置
adapter = IFindAdapter(
    api_key="your_key",
    use_http=True
)

# 初始化（DLL模式）
adapter = IFindAdapter(
    username="your_username",
    password="your_password",
    use_http=False
)

# 获取股票基本信息
basic_info = adapter.get_stock_basic("600519")
print(basic_info)

# 获取日线数据
daily_data = adapter.get_daily_data("600519", "20240101", "20240131")
print(daily_data)

# 获取财务数据
financial_data = adapter.get_financial_data("600519")
print(financial_data)

# 智能选股（仅HTTP模式）
stocks = adapter.smart_stock_selection("光伏板块最近走势")
print(stocks)
```

**股票代码格式**：
- 输入：`600519` 或 `600519.SH`
- 输出：`600519.SH`（自动添加交易所后缀）

## 统一的错误处理

所有适配器都使用统一的错误处理机制：

```python
# 错误返回格式（字典）
{
    "error": True,
    "error_type": "ValueError",
    "error_message": "无效的股票代码",
    "data_source": "tushare",
    "operation": "get_stock_basic(invalid_code)",
    "timestamp": "2024-01-01T00:00:00"
}

# 错误返回格式（DataFrame）
df = adapter.get_daily_data("invalid", "20240101", "20240131")
if df.empty and hasattr(df, 'attrs') and 'error' in df.attrs:
    error_info = df.attrs['error']
    print(f"Error: {error_info['error_message']}")
```

## 数据源标识

所有返回的数据都包含 `data_source` 字段，标识数据来源：

```python
# 字典格式
{
    "stock_code": "600519.SH",
    "stock_name": "贵州茅台",
    "data_source": "tushare",  # 数据来源标识
    ...
}

# DataFrame格式
df = adapter.get_daily_data("600519", "20240101", "20240131")
print(df['data_source'].iloc[0])  # 输出: tushare
```

## 最佳实践

### 1. 数据源选择策略

根据需求选择合适的数据源：

```python
from tools.data_sources import TushareAdapter, AkshareAdapter, IFindAdapter
from config.settings import get_settings

settings = get_settings()

# 优先级策略
if settings.has_tushare():
    adapter = TushareAdapter()
elif settings.has_ifind():
    adapter = IFindAdapter()
else:
    adapter = AkshareAdapter()  # 免费备选
```

### 2. 错误处理

```python
def get_stock_data_with_fallback(stock_code, start_date, end_date):
    """使用多个数据源的容错机制"""
    adapters = [
        TushareAdapter(),
        AkshareAdapter(),
        IFindAdapter()
    ]
    
    for adapter in adapters:
        try:
            df = adapter.get_daily_data(stock_code, start_date, end_date)
            if not df.empty:
                return df
        except Exception as e:
            print(f"{adapter.name} failed: {e}")
            continue
    
    return pd.DataFrame()  # 所有数据源都失败
```

### 3. 缓存机制

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_stock_basic(stock_code):
    """缓存股票基本信息"""
    adapter = TushareAdapter()
    return adapter.get_stock_basic(stock_code)
```

## 扩展新数据源

要添加新的数据源适配器：

1. 继承 `DataSourceAdapter` 基类
2. 实现所有抽象方法
3. 重写 `format_stock_code` 方法（如果格式不同）
4. 在 `__init__.py` 中导出

```python
from .base_adapter import DataSourceAdapter

class MyAdapter(DataSourceAdapter):
    def __init__(self):
        super().__init__(name="my_source")
    
    def get_stock_basic(self, stock_code):
        # 实现逻辑
        pass
    
    def get_daily_data(self, stock_code, start_date, end_date):
        # 实现逻辑
        pass
    
    def get_financial_data(self, stock_code):
        # 实现逻辑
        pass
```

## 测试

运行测试以验证适配器功能：

```bash
# 测试导入
python3 -c "from tools.data_sources import TushareAdapter, AkshareAdapter, IFindAdapter; print('OK')"

# 测试Akshare适配器
python3 -c "
from tools.data_sources import AkshareAdapter
adapter = AkshareAdapter()
print(adapter.format_stock_code('600519'))
"

# 测试Tushare适配器（需要配置token）
python3 -c "
from tools.data_sources import TushareAdapter
adapter = TushareAdapter()
info = adapter.get_stock_basic('600519')
print(info)
"
```

## 注意事项

1. **API限制**：
   - Tushare Pro有调用频率限制
   - iFind需要有效的API密钥或账号
   - Akshare免费但可能不稳定

2. **数据格式**：
   - 日期统一使用 `YYYYMMDD` 格式
   - 股票代码会自动格式化为各数据源要求的格式
   - 返回的DataFrame列名已统一

3. **错误处理**：
   - 所有方法都有完善的错误处理
   - 错误信息包含详细的上下文
   - 建议使用try-except捕获异常

4. **性能优化**：
   - 建议使用缓存减少API调用
   - 批量查询时注意API限制
   - 合理设置超时时间
