# API 文档

## 概述

本文档描述股票分析系统的 REST API 和 SSE（Server-Sent Events）接口。系统提供实时流式分析能力，通过 SSE 推送分析过程和结果。

## 基础信息

- **基础URL**: `http://localhost:8000/api/v1`
- **协议**: HTTP/HTTPS
- **内容类型**: `application/json` (REST), `text/event-stream` (SSE)
- **字符编码**: UTF-8

## 认证

当前版本暂不需要认证。未来版本可能会添加 API Key 或 OAuth2 认证。

## API 端点

### 1. SSE 流式分析接口

实时流式推送股票分析过程和结果。

**端点**: `POST /api/v1/analysis/stream`

**请求格式**:

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

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户查询问题 |
| session_id | string | 否 | 会话ID，不提供则自动生成 |
| options | object | 否 | 可选配置 |
| options.enable_trace | boolean | 否 | 是否启用追踪（默认false） |
| options.max_history | integer | 否 | 最大历史消息数（默认30） |

**响应格式**: SSE 流

**响应头**:

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
Access-Control-Allow-Origin: *
```

**SSE 事件格式**:

```
id: <event_id>
event: <event_type>
data: <json_data>

```

**请求示例**:

```bash
curl -X POST http://localhost:8000/api/v1/analysis/stream \
  -H "Content-Type: application/json" \
  -d '{
    "query": "分析贵州茅台最近的走势",
    "session_id": "test-session-123"
  }'
```

**响应示例**:

```
id: test-session-123_1
event: workflow_start
data: {"session_id":"test-session-123","query":"分析贵州茅台最近的走势","timestamp":"2024-01-01T00:00:00Z"}

id: test-session-123_2
event: stage_start
data: {"stage":"analyze_question","title":"解析用户问题","description":"识别问题类型和所需数据","timestamp":"2024-01-01T00:00:01Z"}

id: test-session-123_3
event: tool_call
data: {"tool_name":"tool_get_stock_history_price","tool_id":"call_123","args":{"stock_code":"600519","start_date":"20240101","end_date":"20240131"},"timestamp":"2024-01-01T00:00:02Z"}

...
```

**错误响应**:

- **400 Bad Request**: 请求参数错误
```json
{
  "detail": "请求数据格式错误: query字段不能为空"
}
```

- **503 Service Unavailable**: 服务器繁忙
```json
{
  "detail": "服务器繁忙，当前并发请求数已达上限（10），请稍后重试"
}
```

- **500 Internal Server Error**: 服务器内部错误
```json
{
  "detail": "服务器内部错误: <error_message>"
}
```

---

### 2. SSE 测试接口

测试 SSE 连接是否正常工作。

**端点**: `GET /api/v1/analysis/stream/test`

**请求参数**: 无

**响应格式**: SSE 流

**响应示例**:

```
id: 1
event: test
data: {"message":"Test event 1","timestamp":"2024-01-01T00:00:00Z"}

id: 2
event: test
data: {"message":"Test event 2","timestamp":"2024-01-01T00:00:01Z"}

...

id: 6
event: complete
data: {"message":"Test completed","timestamp":"2024-01-01T00:00:05Z"}
```

---

### 3. 获取事件类型列表

获取系统支持的所有 SSE 事件类型及其描述。

**端点**: `GET /api/v1/analysis/event-types`

**请求参数**: 无

**响应格式**: JSON

**响应示例**:

```json
{
  "event_types": [
    {
      "type": "analysis_chunk",
      "description": "分析内容增量"
    },
    {
      "type": "error",
      "description": "错误"
    },
    {
      "type": "execution_plan",
      "description": "执行计划"
    },
    {
      "type": "final_answer",
      "description": "最终答案"
    },
    {
      "type": "stage_complete",
      "description": "阶段完成"
    },
    {
      "type": "stage_progress",
      "description": "阶段进度"
    },
    {
      "type": "stage_start",
      "description": "阶段开始"
    },
    {
      "type": "tool_call",
      "description": "工具调用"
    },
    {
      "type": "tool_result",
      "description": "工具结果"
    },
    {
      "type": "workflow_complete",
      "description": "工作流完成"
    },
    {
      "type": "workflow_start",
      "description": "工作流开始"
    }
  ],
  "total": 11
}
```

---

### 4. 获取服务统计信息

获取分析服务的统计信息，包括并发控制、请求队列等。

**端点**: `GET /api/v1/analysis/stats`

**请求参数**: 无

**响应格式**: JSON

**响应示例**:

```json
{
  "concurrency": {
    "max_concurrent": 10,
    "active_requests": 3,
    "total_requests": 156,
    "rejected_requests": 5
  },
  "recent_requests": [
    {
      "session_id": "abc-123",
      "start_time": "2024-01-01T10:00:00Z",
      "duration_ms": 5230,
      "status": "completed"
    }
  ],
  "timestamp": "2024-01-01T10:30:00Z"
}
```

---

## SSE 事件类型详解

系统支持以下 11 种 SSE 事件类型：

### 1. workflow_start - 工作流开始

工作流开始执行时推送。

**数据结构**:

```json
{
  "session_id": "uuid",
  "query": "用户问题",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | string | 会话ID |
| query | string | 用户查询问题 |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 2. stage_start - 阶段开始

工作流进入新阶段时推送。

**数据结构**:

```json
{
  "stage": "analyze_question",
  "title": "解析用户问题",
  "description": "识别问题类型和所需数据",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| stage | string | 阶段名称（analyze_question, collect_data, analyze_data, generate_answer） |
| title | string | 阶段标题 |
| description | string | 阶段描述（可选） |
| timestamp | string | ISO 8601 格式时间戳 |

**阶段类型**:

- `analyze_question`: 解析用户问题
- `collect_data`: 收集数据
- `analyze_data`: 分析数据
- `generate_answer`: 生成答案

---

### 3. stage_progress - 阶段进度

阶段执行过程中推送进度更新。

**数据结构**:

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

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| stage | string | 阶段名称 |
| progress | object | 进度信息 |
| progress.current | integer | 当前进度 |
| progress.total | integer | 总进度 |
| progress.message | string | 进度消息 |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 4. tool_call - 工具调用

系统调用工具函数时推送。

**数据结构**:

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

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| tool_name | string | 工具名称 |
| tool_id | string | 工具调用ID（用于匹配tool_result） |
| args | object | 工具参数 |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 5. tool_result - 工具结果

工具函数返回结果时推送。

**数据结构**:

```json
{
  "tool_name": "tool_get_stock_history_price",
  "tool_id": "call_123",
  "status": "success",
  "summary": "获取到30天历史数据，包含价格和均线",
  "data_id": "compressed_data_123",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| tool_name | string | 工具名称 |
| tool_id | string | 工具调用ID（与tool_call匹配） |
| status | string | 执行状态（success 或 error） |
| summary | string | 结果摘要 |
| data_id | string | 数据ID（如果数据被压缩，可选） |
| error | string | 错误信息（如果失败，可选） |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 6. analysis_chunk - 分析内容增量

系统生成分析内容时推送增量更新。

**数据结构**:

```json
{
  "stage": "analyze_data",
  "content": "根据收集到的数据，贵州茅台在过去30天...",
  "is_final": false,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| stage | string | 阶段名称 |
| content | string | 分析内容 |
| is_final | boolean | 是否为最终内容 |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 7. stage_complete - 阶段完成

阶段执行完成时推送。

**数据结构**:

```json
{
  "stage": "collect_data",
  "summary": "数据收集完成，共调用5个工具",
  "duration_ms": 2500,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| stage | string | 阶段名称 |
| summary | string | 阶段摘要 |
| duration_ms | integer | 阶段耗时（毫秒） |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 8. final_answer - 最终答案

工作流生成最终答案时推送。

**数据结构**:

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

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 答案内容 |
| metadata | object | 元数据 |
| metadata.total_duration_ms | integer | 总耗时（毫秒） |
| metadata.tools_used | array | 使用的工具列表 |
| metadata.data_sources | array | 数据来源列表 |
| timestamp | string | ISO 8601 格式时间戳 |

---

### 9. error - 错误

发生错误时推送。

**数据结构**:

```json
{
  "error_code": "TOOL_CALL_FAILED",
  "error_message": "工具调用失败",
  "error_detail": "连接超时",
  "error_type": "TimeoutError",
  "stage": "collect_data",
  "recoverable": true,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| error_code | string | 错误代码 |
| error_message | string | 错误消息 |
| error_detail | string | 错误详情（可选） |
| error_type | string | 错误类型（可选） |
| stage | string | 发生错误的阶段（可选） |
| recoverable | boolean | 是否可恢复 |
| timestamp | string | ISO 8601 格式时间戳 |

**常见错误代码**:

- `TOOL_CALL_FAILED`: 工具调用失败
- `TOOL_TIMEOUT`: 工具调用超时
- `TOOL_CONNECTION_ERROR`: 工具连接错误
- `DATA_VALIDATION_ERROR`: 数据验证错误
- `WORKFLOW_ERROR`: 工作流执行错误
- `WORKFLOW_TIMEOUT`: 工作流超时
- `LLM_CALL_ERROR`: 大模型调用失败
- `STREAM_ERROR`: 流式处理失败

---

### 10. workflow_complete - 工作流完成

工作流执行完成时推送（无论成功或失败）。

**数据结构**:

```json
{
  "session_id": "uuid",
  "status": "success",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| session_id | string | 会话ID |
| status | string | 完成状态（success, error, timeout, cancelled） |
| timestamp | string | ISO 8601 格式时间戳 |

**状态类型**:

- `success`: 成功完成
- `error`: 发生错误
- `timeout`: 执行超时
- `cancelled`: 客户端取消

---

### 11. execution_plan - 执行计划

系统生成执行计划时推送。

**数据结构**:

```json
{
  "question_type": "技术分析",
  "stock_codes": ["600519"],
  "workflow_stages": [
    {
      "stage": "collect_data",
      "objective": "获取股票历史数据",
      "required_tools": ["tool_get_stock_history_price"]
    }
  ],
  "key_points": ["分析MACD指标", "分析KDJ指标"],
  "risk_points": ["数据可能不完整"],
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| question_type | string | 问题类型 |
| stock_codes | array | 涉及的股票代码列表 |
| workflow_stages | array | 工作流阶段列表 |
| key_points | array | 关键点列表 |
| risk_points | array | 风险点列表 |
| timestamp | string | ISO 8601 格式时间戳 |

---

## 事件序列示例

一个完整的分析请求通常会产生以下事件序列：

```
1. workflow_start          # 工作流开始
2. stage_start             # 阶段1开始：解析问题
3. execution_plan          # 生成执行计划
4. stage_complete          # 阶段1完成
5. stage_start             # 阶段2开始：收集数据
6. tool_call               # 调用工具1
7. tool_result             # 工具1结果
8. tool_call               # 调用工具2
9. tool_result             # 工具2结果
10. stage_complete         # 阶段2完成
11. stage_start            # 阶段3开始：分析数据
12. analysis_chunk         # 分析内容增量1
13. analysis_chunk         # 分析内容增量2
14. stage_complete         # 阶段3完成
15. stage_start            # 阶段4开始：生成答案
16. final_answer           # 最终答案
17. stage_complete         # 阶段4完成
18. workflow_complete      # 工作流完成
```

---

## 错误处理

### 客户端错误处理建议

1. **连接错误**: 实现重连机制，建议使用指数退避策略
2. **超时错误**: 设置合理的超时时间（建议 5-10 分钟）
3. **数据解析错误**: 验证 JSON 格式，处理解析异常
4. **错误事件**: 根据 `recoverable` 字段决定是否重试

### 服务端错误响应

服务端错误会通过以下方式通知：

1. **HTTP 错误状态码**: 400, 500, 503 等
2. **SSE error 事件**: 包含详细错误信息
3. **workflow_complete 事件**: status 字段为 "error"

---

## 性能与限制

### 并发限制

- 默认最大并发连接数: 10
- 超过限制返回 503 错误
- 可通过配置文件调整

### 超时设置

- 默认工作流超时: 300 秒（5 分钟）
- 超时后发送 error 事件和 workflow_complete 事件
- 可通过配置文件调整

### 数据压缩

- 工具输出超过阈值时自动压缩
- 压缩后返回 `data_id` 而非完整数据
- 完整数据存储在服务端，可通过 data_id 查询

---

## CORS 配置

系统默认允许所有来源的跨域请求：

```
Access-Control-Allow-Origin: *
```

生产环境建议配置具体的允许来源。

---

## 版本历史

- **v1.0.0** (2024-01): 初始版本
  - 实现 SSE 流式分析接口
  - 支持 11 种事件类型
  - 实现并发控制和超时机制

---

## 联系与支持

如有问题或建议，请联系开发团队或提交 Issue。
