# 前端对接文档

## 概述

本文档为前端开发者提供与股票分析系统后端 API 对接的详细指南。系统使用 Server-Sent Events (SSE) 技术实现实时流式推送，前端通过 EventSource API 接收分析过程和结果。

## 技术要求

- 浏览器支持 EventSource API（现代浏览器均支持）
- 支持 ES6+ JavaScript
- 推荐使用 TypeScript 以获得类型安全

## 快速开始

### 基础示例

```javascript
// 创建 SSE 连接
const eventSource = new EventSource('http://localhost:8000/api/v1/analysis/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    query: '分析贵州茅台最近的走势',
    session_id: 'my-session-123'
  })
});

// 监听所有事件
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到事件:', data);
};

// 监听错误
eventSource.onerror = (error) => {
  console.error('SSE 错误:', error);
  eventSource.close();
};
```

**注意**: 标准的 EventSource API 不支持 POST 请求和自定义请求体。需要使用以下方法之一：

### 方法 1: 使用 fetch API 手动处理 SSE

```javascript
async function streamAnalysis(query, sessionId) {
  const response = await fetch('http://localhost:8000/api/v1/analysis/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query: query,
      session_id: sessionId
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');

    let eventType = '';
    let eventData = '';

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventType = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        eventData = line.substring(5).trim();
      } else if (line === '' && eventType && eventData) {
        // 完整事件接收完毕
        handleEvent(eventType, JSON.parse(eventData));
        eventType = '';
        eventData = '';
      }
    }
  }
}

function handleEvent(eventType, data) {
  console.log(`事件类型: ${eventType}`, data);
  // 处理不同类型的事件
}
```

### 方法 2: 使用第三方库 (推荐)

使用 `eventsource` 或 `fetch-event-source` 库：

```bash
npm install @microsoft/fetch-event-source
```

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
    console.log('收到事件:', event.event, data);
  },
  onerror(err) {
    console.error('SSE 错误:', err);
    throw err; // 停止重连
  }
});
```

## 完整的 React 示例

### TypeScript 类型定义

```typescript
// types.ts

export type EventType =
  | 'workflow_start'
  | 'stage_start'
  | 'stage_progress'
  | 'tool_call'
  | 'tool_result'
  | 'analysis_chunk'
  | 'stage_complete'
  | 'final_answer'
  | 'error'
  | 'workflow_complete'
  | 'execution_plan';

export type StageType =
  | 'analyze_question'
  | 'collect_data'
  | 'analyze_data'
  | 'generate_answer';

export interface WorkflowStartData {
  session_id: string;
  query: string;
  timestamp: string;
}

export interface StageStartData {
  stage: StageType;
  title: string;
  description?: string;
  timestamp: string;
}

export interface StageProgressData {
  stage: StageType;
  progress: {
    current: number;
    total: number;
    message: string;
  };
  timestamp: string;
}

export interface ToolCallData {
  tool_name: string;
  tool_id: string;
  args: Record<string, any>;
  timestamp: string;
}

export interface ToolResultData {
  tool_name: string;
  tool_id: string;
  status: 'success' | 'error';
  summary: string;
  data_id?: string;
  error?: string;
  timestamp: string;
}

export interface AnalysisChunkData {
  stage: StageType;
  content: string;
  is_final: boolean;
  timestamp: string;
}

export interface StageCompleteData {
  stage: StageType;
  summary: string;
  duration_ms: number;
  timestamp: string;
}

export interface FinalAnswerData {
  content: string;
  metadata: {
    total_duration_ms: number;
    tools_used: string[];
    data_sources: string[];
  };
  timestamp: string;
}

export interface ErrorData {
  error_code: string;
  error_message: string;
  error_detail?: string;
  error_type?: string;
  stage?: StageType;
  recoverable: boolean;
  timestamp: string;
}

export interface WorkflowCompleteData {
  session_id: string;
  status: 'success' | 'error' | 'timeout' | 'cancelled';
  timestamp: string;
}

export interface ExecutionPlanData {
  question_type: string;
  stock_codes: string[];
  workflow_stages: Array<{
    stage: string;
    objective: string;
    required_tools: string[];
  }>;
  key_points: string[];
  risk_points: string[];
  timestamp: string;
}

export interface SSEEvent {
  type: EventType;
  data: any;
  id?: string;
}
```

### React Hook 实现

```typescript
// useStockAnalysis.ts

import { useState, useCallback, useRef } from 'react';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { SSEEvent, EventType } from './types';

interface UseStockAnalysisOptions {
  onEvent?: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onComplete?: () => void;
}

export function useStockAnalysis(options: UseStockAnalysisOptions = {}) {
  const [isStreaming, setIsStreaming] = useState(false);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const startAnalysis = useCallback(async (query: string, sessionId?: string) => {
    // 重置状态
    setIsStreaming(true);
    setEvents([]);
    setError(null);

    // 创建 AbortController 用于取消请求
    abortControllerRef.current = new AbortController();

    try {
      await fetchEventSource('http://localhost:8000/api/v1/analysis/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          session_id: sessionId || `session-${Date.now()}`,
          options: {
            enable_trace: false,
            max_history: 30
          }
        }),
        signal: abortControllerRef.current.signal,
        
        onmessage(msg) {
          if (msg.event && msg.data) {
            const event: SSEEvent = {
              type: msg.event as EventType,
              data: JSON.parse(msg.data),
              id: msg.id
            };

            // 更新事件列表
            setEvents(prev => [...prev, event]);

            // 调用回调
            options.onEvent?.(event);

            // 检查是否完成
            if (event.type === 'workflow_complete') {
              setIsStreaming(false);
              options.onComplete?.();
            }
          }
        },

        onerror(err) {
          console.error('SSE 错误:', err);
          setError(err as Error);
          setIsStreaming(false);
          options.onError?.(err as Error);
          throw err; // 停止重连
        },

        openWhenHidden: true, // 页面隐藏时保持连接
      });
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        setError(err);
        setIsStreaming(false);
        options.onError?.(err);
      }
    }
  }, [options]);

  const stopAnalysis = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  return {
    isStreaming,
    events,
    error,
    startAnalysis,
    stopAnalysis
  };
}
```

### React 组件示例

```typescript
// StockAnalysisComponent.tsx

import React, { useState } from 'react';
import { useStockAnalysis } from './useStockAnalysis';
import type { SSEEvent } from './types';

export function StockAnalysisComponent() {
  const [query, setQuery] = useState('');
  const [currentStage, setCurrentStage] = useState('');
  const [analysisContent, setAnalysisContent] = useState('');
  const [finalAnswer, setFinalAnswer] = useState('');
  const [toolCalls, setToolCalls] = useState<any[]>([]);

  const { isStreaming, events, error, startAnalysis, stopAnalysis } = useStockAnalysis({
    onEvent: (event: SSEEvent) => {
      console.log('收到事件:', event);

      switch (event.type) {
        case 'stage_start':
          setCurrentStage(event.data.title);
          break;

        case 'tool_call':
          setToolCalls(prev => [...prev, event.data]);
          break;

        case 'analysis_chunk':
          setAnalysisContent(prev => prev + event.data.content);
          break;

        case 'final_answer':
          setFinalAnswer(event.data.content);
          break;

        case 'error':
          console.error('分析错误:', event.data);
          break;
      }
    },
    onError: (err) => {
      console.error('流式处理错误:', err);
    },
    onComplete: () => {
      console.log('分析完成');
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      startAnalysis(query);
    }
  };

  return (
    <div className="stock-analysis">
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入您的问题，例如：分析贵州茅台最近的走势"
          disabled={isStreaming}
        />
        <button type="submit" disabled={isStreaming || !query.trim()}>
          {isStreaming ? '分析中...' : '开始分析'}
        </button>
        {isStreaming && (
          <button type="button" onClick={stopAnalysis}>
            停止
          </button>
        )}
      </form>

      {error && (
        <div className="error">
          错误: {error.message}
        </div>
      )}

      {isStreaming && currentStage && (
        <div className="current-stage">
          当前阶段: {currentStage}
        </div>
      )}

      {toolCalls.length > 0 && (
        <div className="tool-calls">
          <h3>工具调用</h3>
          <ul>
            {toolCalls.map((call, index) => (
              <li key={index}>
                {call.tool_name} - {JSON.stringify(call.args)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysisContent && (
        <div className="analysis-content">
          <h3>分析过程</h3>
          <pre>{analysisContent}</pre>
        </div>
      )}

      {finalAnswer && (
        <div className="final-answer">
          <h3>最终答案</h3>
          <div>{finalAnswer}</div>
        </div>
      )}

      <div className="events-log">
        <h3>事件日志 ({events.length})</h3>
        <ul>
          {events.map((event, index) => (
            <li key={index}>
              [{event.type}] {JSON.stringify(event.data)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
```

## Vue 3 示例

### Composition API

```typescript
// useStockAnalysis.ts (Vue)

import { ref, onUnmounted } from 'vue';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import type { SSEEvent } from './types';

export function useStockAnalysis() {
  const isStreaming = ref(false);
  const events = ref<SSEEvent[]>([]);
  const error = ref<Error | null>(null);
  const currentStage = ref('');
  const analysisContent = ref('');
  const finalAnswer = ref('');

  let abortController: AbortController | null = null;

  const startAnalysis = async (query: string, sessionId?: string) => {
    // 重置状态
    isStreaming.value = true;
    events.value = [];
    error.value = null;
    currentStage.value = '';
    analysisContent.value = '';
    finalAnswer.value = '';

    abortController = new AbortController();

    try {
      await fetchEventSource('http://localhost:8000/api/v1/analysis/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query,
          session_id: sessionId || `session-${Date.now()}`,
        }),
        signal: abortController.signal,

        onmessage(msg) {
          if (msg.event && msg.data) {
            const event: SSEEvent = {
              type: msg.event as any,
              data: JSON.parse(msg.data),
              id: msg.id
            };

            events.value.push(event);

            // 处理不同类型的事件
            switch (event.type) {
              case 'stage_start':
                currentStage.value = event.data.title;
                break;
              case 'analysis_chunk':
                analysisContent.value += event.data.content;
                break;
              case 'final_answer':
                finalAnswer.value = event.data.content;
                break;
              case 'workflow_complete':
                isStreaming.value = false;
                break;
            }
          }
        },

        onerror(err) {
          console.error('SSE 错误:', err);
          error.value = err as Error;
          isStreaming.value = false;
          throw err;
        }
      });
    } catch (err) {
      if (err instanceof Error && err.name !== 'AbortError') {
        error.value = err;
        isStreaming.value = false;
      }
    }
  };

  const stopAnalysis = () => {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    isStreaming.value = false;
  };

  // 组件卸载时清理
  onUnmounted(() => {
    stopAnalysis();
  });

  return {
    isStreaming,
    events,
    error,
    currentStage,
    analysisContent,
    finalAnswer,
    startAnalysis,
    stopAnalysis
  };
}
```

### Vue 组件

```vue
<template>
  <div class="stock-analysis">
    <form @submit.prevent="handleSubmit">
      <input
        v-model="query"
        type="text"
        placeholder="输入您的问题"
        :disabled="isStreaming"
      />
      <button type="submit" :disabled="isStreaming || !query.trim()">
        {{ isStreaming ? '分析中...' : '开始分析' }}
      </button>
      <button v-if="isStreaming" type="button" @click="stopAnalysis">
        停止
      </button>
    </form>

    <div v-if="error" class="error">
      错误: {{ error.message }}
    </div>

    <div v-if="isStreaming && currentStage" class="current-stage">
      当前阶段: {{ currentStage }}
    </div>

    <div v-if="analysisContent" class="analysis-content">
      <h3>分析过程</h3>
      <pre>{{ analysisContent }}</pre>
    </div>

    <div v-if="finalAnswer" class="final-answer">
      <h3>最终答案</h3>
      <div>{{ finalAnswer }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useStockAnalysis } from './useStockAnalysis';

const query = ref('');

const {
  isStreaming,
  error,
  currentStage,
  analysisContent,
  finalAnswer,
  startAnalysis,
  stopAnalysis
} = useStockAnalysis();

const handleSubmit = () => {
  if (query.value.trim()) {
    startAnalysis(query.value);
  }
};
</script>
```

## 错误处理最佳实践

### 1. 网络错误处理

```typescript
async function startAnalysisWithRetry(query: string, maxRetries = 3) {
  let retries = 0;

  while (retries < maxRetries) {
    try {
      await startAnalysis(query);
      break; // 成功，退出循环
    } catch (error) {
      retries++;
      console.error(`尝试 ${retries}/${maxRetries} 失败:`, error);

      if (retries >= maxRetries) {
        throw new Error('达到最大重试次数');
      }

      // 指数退避
      const delay = Math.min(1000 * Math.pow(2, retries), 10000);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

### 2. 超时处理

```typescript
async function startAnalysisWithTimeout(query: string, timeoutMs = 300000) {
  const timeoutPromise = new Promise((_, reject) => {
    setTimeout(() => reject(new Error('请求超时')), timeoutMs);
  });

  const analysisPromise = startAnalysis(query);

  try {
    await Promise.race([analysisPromise, timeoutPromise]);
  } catch (error) {
    stopAnalysis(); // 确保清理资源
    throw error;
  }
}
```

### 3. 错误事件处理

```typescript
function handleErrorEvent(errorData: ErrorData) {
  console.error('收到错误事件:', errorData);

  // 根据错误代码采取不同的处理策略
  switch (errorData.error_code) {
    case 'TOOL_TIMEOUT':
    case 'TOOL_CONNECTION_ERROR':
      if (errorData.recoverable) {
        // 可恢复的错误，可以重试
        console.log('错误可恢复，建议重试');
      }
      break;

    case 'WORKFLOW_TIMEOUT':
      // 工作流超时，不可恢复
      console.error('工作流超时，请简化查询或稍后重试');
      break;

    case 'DATA_VALIDATION_ERROR':
      // 数据验证错误，可能是输入问题
      console.error('数据验证失败，请检查输入');
      break;

    default:
      console.error('未知错误:', errorData.error_message);
  }

  // 显示用户友好的错误消息
  showUserError(errorData);
}

function showUserError(errorData: ErrorData) {
  const userMessages: Record<string, string> = {
    'TOOL_TIMEOUT': '数据获取超时，请稍后重试',
    'TOOL_CONNECTION_ERROR': '网络连接失败，请检查网络',
    'WORKFLOW_TIMEOUT': '分析超时，请简化您的问题',
    'DATA_VALIDATION_ERROR': '数据格式错误，请重新输入',
    'LLM_CALL_ERROR': '分析服务暂时不可用，请稍后重试'
  };

  const message = userMessages[errorData.error_code] || '发生未知错误';
  alert(message); // 或使用更友好的 UI 组件
}
```

### 4. 连接断开处理

```typescript
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function handleConnectionError(error: Error) {
  console.error('连接错误:', error);

  if (reconnectAttempts < maxReconnectAttempts) {
    reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);

    console.log(`${delay}ms 后尝试重连 (${reconnectAttempts}/${maxReconnectAttempts})`);

    setTimeout(() => {
      // 重新建立连接
      startAnalysis(lastQuery);
    }, delay);
  } else {
    console.error('达到最大重连次数，放弃重连');
    showUserError({
      error_code: 'CONNECTION_FAILED',
      error_message: '无法连接到服务器',
      recoverable: false,
      timestamp: new Date().toISOString()
    } as ErrorData);
  }
}

// 连接成功时重置重连计数
function handleConnectionSuccess() {
  reconnectAttempts = 0;
}
```

## 性能优化建议

### 1. 事件节流

对于高频事件（如 analysis_chunk），使用节流避免过度渲染：

```typescript
import { throttle } from 'lodash';

const throttledUpdateContent = throttle((content: string) => {
  setAnalysisContent(content);
}, 100); // 每 100ms 最多更新一次

// 在事件处理中使用
case 'analysis_chunk':
  throttledUpdateContent(prev => prev + event.data.content);
  break;
```

### 2. 虚拟滚动

对于大量事件日志，使用虚拟滚动：

```typescript
import { FixedSizeList } from 'react-window';

function EventLogList({ events }: { events: SSEEvent[] }) {
  const Row = ({ index, style }: any) => (
    <div style={style}>
      [{events[index].type}] {JSON.stringify(events[index].data)}
    </div>
  );

  return (
    <FixedSizeList
      height={400}
      itemCount={events.length}
      itemSize={35}
      width="100%"
    >
      {Row}
    </FixedSizeList>
  );
}
```

### 3. 内存管理

限制保存的事件数量：

```typescript
const MAX_EVENTS = 1000;

function addEvent(event: SSEEvent) {
  setEvents(prev => {
    const newEvents = [...prev, event];
    // 只保留最新的 MAX_EVENTS 个事件
    return newEvents.slice(-MAX_EVENTS);
  });
}
```

## 调试技巧

### 1. 启用详细日志

```typescript
const DEBUG = true;

function logEvent(event: SSEEvent) {
  if (DEBUG) {
    console.group(`[${event.type}] ${new Date().toISOString()}`);
    console.log('Event ID:', event.id);
    console.log('Data:', event.data);
    console.groupEnd();
  }
}
```

### 2. 事件时间线可视化

```typescript
interface EventTimeline {
  type: string;
  timestamp: Date;
  duration?: number;
}

const timeline: EventTimeline[] = [];

function trackEvent(event: SSEEvent) {
  timeline.push({
    type: event.type,
    timestamp: new Date(event.data.timestamp),
  });

  // 计算阶段耗时
  if (event.type === 'stage_complete') {
    const startEvent = timeline.find(
      e => e.type === 'stage_start' && !e.duration
    );
    if (startEvent) {
      startEvent.duration = event.data.duration_ms;
    }
  }
}

// 可视化时间线
function visualizeTimeline() {
  console.table(timeline);
}
```

### 3. 使用浏览器开发者工具

在 Chrome DevTools 中：
1. 打开 Network 标签
2. 筛选 EventStream 类型
3. 查看实时事件流
4. 检查连接状态和错误

## 常见问题

### Q1: EventSource 不支持 POST 请求怎么办？

A: 使用 `fetch` API 手动处理 SSE 流，或使用 `@microsoft/fetch-event-source` 库。

### Q2: 如何处理长时间运行的分析？

A: 实现超时机制和进度显示，让用户了解当前状态。建议设置 5-10 分钟的超时。

### Q3: 页面刷新后如何恢复会话？

A: 使用持久化的 session_id（如存储在 localStorage），但注意服务端可能不保存历史状态。

### Q4: 如何测试 SSE 连接？

A: 使用测试端点 `GET /api/v1/analysis/stream/test` 验证连接是否正常。

### Q5: 移动端浏览器支持如何？

A: 现代移动浏览器均支持 EventSource，但注意处理后台运行和网络切换的情况。

## 安全建议

1. **输入验证**: 在发送前验证用户输入
2. **XSS 防护**: 渲染用户内容时进行转义
3. **HTTPS**: 生产环境使用 HTTPS
4. **认证**: 添加 API 认证机制
5. **速率限制**: 客户端实现请求节流

## 示例项目

完整的示例项目可在以下位置找到：
- React 示例: `/examples/react-frontend`
- Vue 示例: `/examples/vue-frontend`
- 原生 JavaScript 示例: `/examples/vanilla-js`

## 联系与支持

如有问题或建议，请联系开发团队或提交 Issue。
