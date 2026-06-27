# 配置管理模块

本模块使用 Pydantic 进行配置验证，支持从环境变量和 `.env` 文件加载配置。

## 特性

- ✅ 使用 Pydantic 进行类型验证和数据校验
- ✅ 支持环境变量和 `.env` 文件
- ✅ 嵌套配置结构，组织清晰
- ✅ 单例模式，全局配置实例
- ✅ 向后兼容旧的配置方式
- ✅ 支持多环境配置（development、testing、production）

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 到 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，至少需要配置：

```bash
DEEPSEEK_API_KEY=sk-your-api-key-here
DATA_SOURCE__TUSHARE_TOKEN=your-tushare-token-here
```

### 2. 使用配置

```python
from config.settings import get_settings

# 获取配置实例
settings = get_settings()

# 访问配置
print(settings.deepseek_api_key)
print(settings.llm.default_model)
print(settings.data_source.tushare_token)

# 使用便捷方法
if settings.has_tushare():
    token = settings.get_tushare_token()
    print(f"Tushare token: {token}")

# 检查环境
if settings.is_development():
    print("Running in development mode")
```

### 3. 向后兼容

旧代码仍然可以使用：

```python
from config.settings import DEEPSEEK_API_KEY, TUSHARE_TOKEN, DEFAULT_MODEL

print(DEEPSEEK_API_KEY)
print(TUSHARE_TOKEN)
print(DEFAULT_MODEL)
```

## 配置结构

### 主配置 (Settings)

| 字段 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| environment | str | 否 | development | 运行环境 |
| deepseek_api_key | str | 是 | - | DeepSeek API Key |
| openai_api_key | str | 否 | None | OpenAI API Key |
| serpapi_api_key | str | 否 | None | SerpAPI Key |
| bing_search_api_key | str | 否 | None | Bing Search API Key |
| mcp_server_url | str | 否 | None | MCP服务器URL |
| database_url | str | 否 | None | 数据库连接URL |

### LLM配置 (LLMConfig)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_model | str | deepseek-chat | 默认模型 |
| temperature | float | 0.7 | 温度参数 (0.0-2.0) |
| max_tokens | int | None | 最大token数 |
| timeout | int | 60 | API超时时间（秒） |

### 数据源配置 (DataSourceConfig)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| tushare_token | str | None | Tushare Pro Token |
| tushare_timeout | int | 30 | Tushare超时时间 |
| tushare_retry_count | int | 3 | Tushare重试次数 |
| wind_api_key | str | None | Wind/iFind API Key |
| wind_username | str | None | Wind用户名 |
| wind_password | str | None | Wind密码 |
| data_source_priority | list | [tushare, akshare, ifind] | 数据源优先级 |

### 缓存配置 (CacheConfig)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| enable_cache | bool | True | 是否启用缓存 |
| cache_dir | Path | data_cache | 缓存目录 |
| cache_ttl | int | 3600 | 缓存过期时间（秒） |
| max_cache_size_mb | int | 1000 | 最大缓存大小（MB） |

### 日志配置 (LogConfig)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| log_level | str | INFO | 日志级别 |
| log_dir | Path | logs | 日志目录 |
| log_to_console | bool | True | 输出到控制台 |
| log_to_file | bool | True | 输出到文件 |
| log_rotation | str | 1 day | 日志轮转周期 |
| log_retention | str | 30 days | 日志保留时间 |
| log_max_size | str | 100 MB | 单文件最大大小 |

### 性能配置 (PerformanceConfig)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_concurrent_requests | int | 10 | 最大并发请求数 |
| request_timeout | int | 300 | 请求超时时间（秒） |
| data_compression_threshold | int | 20000 | 数据压缩阈值（token） |
| max_message_history | int | 30 | 最大消息历史数 |
| enable_data_compression | bool | True | 启用数据压缩 |

### API配置 (APIConfig)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| host | str | 0.0.0.0 | 监听地址 |
| port | int | 8000 | 监听端口 |
| cors_origins | list | ["*"] | CORS源 |
| enable_docs | bool | True | 启用API文档 |

## 环境变量命名规则

使用双下划线 `__` 分隔嵌套配置：

```bash
# 主配置
DEEPSEEK_API_KEY=sk-xxx

# LLM配置
LLM__DEFAULT_MODEL=deepseek-chat
LLM__TEMPERATURE=0.7

# 数据源配置
DATA_SOURCE__TUSHARE_TOKEN=xxx
DATA_SOURCE__TUSHARE_TIMEOUT=30

# 缓存配置
CACHE__ENABLE_CACHE=true
CACHE__CACHE_TTL=3600
```

## 配置验证

配置会在加载时自动验证：

```python
from config.settings import get_settings
from pydantic import ValidationError

try:
    settings = get_settings()
except ValidationError as e:
    print("配置验证失败:")
    print(e.json())
```

验证规则：

- `deepseek_api_key`: 必需，必须以 `sk-` 开头
- `temperature`: 必须在 0.0 到 2.0 之间
- `port`: 必须在 1 到 65535 之间
- `data_source_priority`: 只能包含 tushare、akshare、ifind

## 多环境配置

通过 `ENVIRONMENT` 环境变量切换环境：

```bash
# 开发环境
ENVIRONMENT=development

# 测试环境
ENVIRONMENT=testing

# 生产环境
ENVIRONMENT=production
```

在代码中检查环境：

```python
settings = get_settings()

if settings.is_development():
    # 开发环境特定逻辑
    pass

if settings.is_production():
    # 生产环境特定逻辑
    pass
```

## 重新加载配置

如果需要重新加载配置（例如配置文件更新后）：

```python
from config.settings import reload_settings

settings = reload_settings()
```

## 最佳实践

1. **不要在代码中硬编码敏感信息**：所有API密钥和密码都应通过环境变量配置

2. **使用类型提示**：配置已经包含完整的类型注解，IDE会提供自动补全

3. **验证配置**：在应用启动时验证配置，及早发现问题

4. **使用便捷方法**：使用 `has_tushare()`、`is_development()` 等方法而不是直接检查字段

5. **环境隔离**：不同环境使用不同的 `.env` 文件

## 故障排查

### 问题：配置加载失败

```
ValidationError: 1 validation error for Settings
deepseek_api_key
  Field required
```

**解决方案**：确保 `.env` 文件存在且包含 `DEEPSEEK_API_KEY`

### 问题：Tushare token 未加载

**解决方案**：使用嵌套格式 `DATA_SOURCE__TUSHARE_TOKEN` 而不是 `TUSHARE_TOKEN`

### 问题：配置更新不生效

**解决方案**：调用 `reload_settings()` 重新加载配置

## 示例

### 完整示例

```python
from config.settings import get_settings

def main():
    # 加载配置
    settings = get_settings()
    
    # 检查必需配置
    if not settings.deepseek_api_key:
        raise ValueError("DeepSeek API key is required")
    
    # 检查可选配置
    if settings.has_tushare():
        print(f"Tushare configured with token: {settings.get_tushare_token()[:10]}...")
    else:
        print("Tushare not configured, some features may be unavailable")
    
    # 使用配置
    print(f"Running in {settings.environment} mode")
    print(f"Using model: {settings.llm.default_model}")
    print(f"Cache enabled: {settings.cache.enable_cache}")
    print(f"Log level: {settings.log.log_level}")
    
    # 环境特定逻辑
    if settings.is_development():
        print("Development mode: verbose logging enabled")
    elif settings.is_production():
        print("Production mode: optimized for performance")

if __name__ == "__main__":
    main()
```
