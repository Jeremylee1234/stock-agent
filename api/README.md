# 股票分析系统 API

基于FastAPI的SSE流式接口，提供实时股票分析服务。

## 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn httpx
```

### 2. 配置环境变量

确保 `.env` 文件中配置了必要的API密钥：

```env
DEEPSEEK_API_KEY=sk-your-api-key
TUSHARE_TOKEN=your-tushare-token  # 可选
```

### 3. 启动服务器

```bash
# 方式1: 直接运行
python api/main.py

# 方式2: 使用uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

服务器将在 `http://localhost:8000` 启动。

### 4. 访问API文档

- Swagger UI: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc

## API端点

### 健康检查

```http
GET /health
GET /api/health
```

返回服务健康状态。

**响应示例:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00",
  "service": "stock-analysis-api",
  "version": "1.0.0"
}
```

### 获取事件类型列表

```http
GET /api/v1/analysis/event-types
```

返回所有支持的SSE事件类型。

**响应示例:**
```json
{
  "event_types": [
    {
      "type": "workflow_start",
      "description": "工作流开始"
    },
    {
      "type": "stage_start",
      "description": "阶段开始"
    }
  ],
  "total": 11
}
```

### SSE流式分析

```http
POST /api/v1/analysis/stream
Content-Type: application/json
Accept: text/event-stream
```

**请求体:**
```json
{
  "query": "分析贵州茅台最近的走势",
  "session_id": "optional-session-id",
  "options": {
    "enable_trace": false,
    "max_history": 30
  }
}
```

**响应:** SSE事件流

### SSE测试端点

```http
GET /api/v1/analysis/stream/test
Accept: text/event-stream
```

返回测试SSE事件流，用于验证连接。

## SSE事件类型

系统支持以下11种事件类型：

### 1. workflow_start - 工作流开始

```json
{
  "session_id": "uuid",
  "query": "用户问题",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 2. stage_start - 阶段开始

```json
{
  "stage": "analyze_question",
  "title": "解析用户问题",
  "description": "识别问题类型和所需数据",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 3. stage_progress - 阶段进度

```json
{
  "stage": "collect_data",
  "progress": {
    "current": 2,
    "total": 5,
    "message": "正在调用工具: tool_get_stock_history_price"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 4. tool_call - 工具调用

```json
{
  "tool_name": "tool_get_stock_history_price",
  "tool_id": "call_123",
  "args": {
    "stock_code": "600519",
    "start_date": "20240101",
    "end_date": "20240131"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 5. tool_result - 工具结果

```json
{
  "tool_name": "tool_get_stock_history_price",
  "tool_id": "call_123",
  "status": "success",
  "summary": "获取到30天历史数据",
  "data_id": "compressed_data_123",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 6. analysis_chunk - 分析内容增量

```json
{
  "stage": "analyze_data",
  "content": "根据收集到的数据，贵州茅台在过去30天...",
  "is_final": false,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 7. stage_complete - 阶段完成

```json
{
  "stage": "collect_data",
  "summary": "数据收集完成，共调用5个工具",
  "duration_ms": 2500,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 8. final_answer - 最终答案

```json
{
  "content": "完整的分析结论...",
  "metadata": {
    "total_duration_ms": 8000,
    "tools_used": ["tool1", "tool2"],
    "data_sources": ["ifind", "akshare"]
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 9. error - 错误事件

```json
{
  "error_code": "TOOL_CALL_FAILED",
  "error_message": "工具调用失败",
  "error_detail": "连接超时",
  "stage": "collect_data",
  "recoverable": true,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 10. workflow_complete - 工作流完成

```json
{
  "session_id": "uuid",
  "status": "success",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### 11. execution_plan - 执行计划

```json
{
  "question_type": "技术分析",
  "stock_codes": ["600519"],
  "workflow_stages": [...],
  "key_points": [...],
  "risk_points": [...],
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## 工作流阶段

系统包含4个主要工作流阶段：

1. **analyze_question** - 分析问题
2. **collect_data** - 收集数据
3. **analyze_data** - 分析数据
4. **generate_answer** - 生成答案

## 前端集成示例

### JavaScript (EventSource)

```javascript
const eventSource = new EventSource('http://localhost:8000/api/v1/analysis/stream');

eventSource.addEventListener('workflow_start', (event) => {
  const data = JSON.parse(event.data);
  console.log('工作流开始:', data);
});

eventSource.addEventListener('stage_start', (event) => {
  const data = JSON.parse(event.data);
  console.log('阶段开始:', data.stage);
});

eventSource.addEventListener('final_answer', (event) => {
  const data = JSON.parse(event.data);
  console.log('最终答案:', data.content);
});

eventSource.addEventListener('error', (event) => {
  const data = JSON.parse(event.data);
  console.error('错误:', data.error_message);
});

eventSource.addEventListener('workflow_complete', (event) => {
  const data = JSON.parse(event.data);
  console.log('工作流完成:', data.status);
  eventSource.close();
});
```

### Python (httpx)

```python
import httpx
import json

async def stream_analysis(query: str):
    async with httpx.AsyncClient(timeout=300.0) as client:
        request_data = {
            "query": query,
            "options": {"enable_trace": False}
        }
        
        async with client.stream(
            "POST",
            "http://localhost:8000/api/v1/analysis/stream",
            json=request_data,
            headers={"Accept": "text/event-stream"}
        ) as response:
            event_type = None
            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_str = line.split(":", 1)[1].strip()
                    data = json.loads(data_str)
                    print(f"[{event_type}] {data}")
                    
                    if event_type == "workflow_complete":
                        break
```

## 测试工具

### 1. Python测试脚本

```bash
python test_sse_api.py
```

### 2. HTML测试客户端

在浏览器中打开 `test_sse_client.html`

### 3. curl测试

```bash
# 健康检查
curl http://localhost:8000/health

# 事件类型列表
curl http://localhost:8000/api/v1/analysis/event-types

# SSE测试端点
curl -N http://localhost:8000/api/v1/analysis/stream/test

# SSE流式分析
curl -N -X POST http://localhost:8000/api/v1/analysis/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query": "分析贵州茅台最近的走势"}'
```

## 错误处理

API使用标准的HTTP状态码和错误响应格式：

```json
{
  "error": true,
  "error_code": "VALIDATION_ERROR",
  "error_message": "请求数据验证失败",
  "error_detail": "query: field required",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

常见错误代码：

- `VALIDATION_ERROR` - 请求数据验证失败 (400)
- `WORKFLOW_ERROR` - 工作流执行错误 (500)
- `TOOL_EXECUTION_ERROR` - 工具执行错误 (500)
- `STREAM_ERROR` - 流式处理错误 (500)
- `CONFIGURATION_ERROR` - 配置错误 (500)

## 配置

API配置通过 `config/settings.py` 管理，支持环境变量覆盖：

```env
# API配置
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=["*"]

# 性能配置
MAX_CONCURRENT_REQUESTS=10
REQUEST_TIMEOUT=300
```

## 性能优化

- 支持异步处理，可处理多个并发请求
- 自动数据压缩，减少传输数据量
- 消息历史修剪，避免上下文溢出
- 连接超时管理，防止资源泄漏

## 安全建议

1. 在生产环境中配置具体的CORS源，不要使用 `["*"]`
2. 使用HTTPS加密传输
3. 实施API密钥认证
4. 配置请求速率限制
5. 启用日志审计

## 故障排查

### 连接失败

检查服务器是否启动：
```bash
curl http://localhost:8000/health
```

### SSE事件未收到

1. 确认请求头包含 `Accept: text/event-stream`
2. 检查防火墙和代理设置
3. 查看服务器日志

### 工作流执行失败

1. 检查 `.env` 文件中的API密钥配置
2. 查看日志文件 `logs/` 目录
3. 验证数据源连接

## 许可证

MIT License
