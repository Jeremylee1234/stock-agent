# 部署文档

## 概述

本文档提供股票分析系统的部署指南，包括环境配置、Docker 部署、监控和日志配置等内容。

## 系统要求

### 硬件要求

**最低配置**:
- CPU: 2 核
- 内存: 4 GB
- 磁盘: 20 GB

**推荐配置**:
- CPU: 4 核或更多
- 内存: 8 GB 或更多
- 磁盘: 50 GB 或更多（用于日志和缓存）

### 软件要求

- **操作系统**: Linux (Ubuntu 20.04+, CentOS 7+) 或 macOS
- **Python**: 3.9 或更高版本
- **Docker**: 20.10+ (可选，用于容器化部署)
- **Docker Compose**: 1.29+ (可选)

## 环境配置

### 1. 环境变量配置

系统使用环境变量进行配置。创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必需的环境变量：

```bash
# ============================================
# 必需配置
# ============================================

# 运行环境 (development, testing, production)
ENVIRONMENT=production

# DeepSeek API Key（必需）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here

# ============================================
# 数据源配置
# ============================================

# Tushare Pro Token（推荐配置）
TUSHARE_TOKEN=your-tushare-token-here

# Wind/iFind API（可选）
WIND_API_KEY=your-wind-api-key
WIND_USERNAME=your-wind-username
WIND_PASSWORD=your-wind-password

# ============================================
# 可选配置
# ============================================

# OpenAI API Key（可选）
OPENAI_API_KEY=sk-your-openai-api-key

# 搜索 API（可选）
SERPAPI_API_KEY=your-serpapi-key
BING_SEARCH_API_KEY=your-bing-search-key
BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com/v7.0/search

# MCP Server（可选）
MCP_SERVER_URL=http://localhost:3000

# 数据库（可选）
DATABASE_URL=postgresql://user:password@localhost:5432/stock_analysis

# ============================================
# LLM 配置
# ============================================

LLM__DEFAULT_MODEL=deepseek-chat
LLM__TEMPERATURE=0.7
LLM__MAX_TOKENS=4000
LLM__TIMEOUT=60

# ============================================
# 数据源配置
# ============================================

DATA_SOURCE__TUSHARE_TIMEOUT=30
DATA_SOURCE__TUSHARE_RETRY_COUNT=3
DATA_SOURCE__DATA_SOURCE_PRIORITY=["tushare", "akshare", "ifind"]

# ============================================
# 缓存配置
# ============================================

CACHE__ENABLE_CACHE=true
CACHE__CACHE_DIR=data_cache
CACHE__CACHE_TTL=3600
CACHE__MAX_CACHE_SIZE_MB=1000

# ============================================
# 日志配置
# ============================================

LOG__LOG_LEVEL=INFO
LOG__LOG_DIR=logs
LOG__LOG_TO_CONSOLE=true
LOG__LOG_TO_FILE=true
LOG__LOG_ROTATION=1 day
LOG__LOG_RETENTION=30 days
LOG__LOG_MAX_SIZE=100 MB

# ============================================
# 性能配置
# ============================================

PERFORMANCE__MAX_CONCURRENT_REQUESTS=10
PERFORMANCE__REQUEST_TIMEOUT=300
PERFORMANCE__DATA_COMPRESSION_THRESHOLD=20000
PERFORMANCE__MAX_MESSAGE_HISTORY=30
PERFORMANCE__ENABLE_DATA_COMPRESSION=true

# ============================================
# API 配置
# ============================================

API__HOST=0.0.0.0
API__PORT=8000
API__CORS_ORIGINS=["*"]
API__ENABLE_DOCS=true
```

### 2. 配置说明

#### 必需配置

| 变量 | 说明 | 示例 |
|------|------|------|
| ENVIRONMENT | 运行环境 | production |
| DEEPSEEK_API_KEY | DeepSeek API 密钥 | sk-xxx |

#### 数据源配置

| 变量 | 说明 | 是否必需 |
|------|------|----------|
| TUSHARE_TOKEN | Tushare Pro Token | 推荐 |
| WIND_API_KEY | Wind/iFind API Key | 可选 |
| WIND_USERNAME | Wind/iFind 用户名 | 可选 |
| WIND_PASSWORD | Wind/iFind 密码 | 可选 |

#### 性能配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| PERFORMANCE__MAX_CONCURRENT_REQUESTS | 最大并发请求数 | 10 |
| PERFORMANCE__REQUEST_TIMEOUT | 请求超时时间（秒） | 300 |
| PERFORMANCE__DATA_COMPRESSION_THRESHOLD | 数据压缩阈值（token） | 20000 |

### 3. 配置验证

验证配置是否正确：

```bash
python -c "from config.settings import settings; print('配置加载成功'); print(f'环境: {settings.environment}'); print(f'API端口: {settings.api.port}')"
```

## 本地部署

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate
# Windows:
# venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 初始化

```bash
# 创建必要的目录
mkdir -p logs data_cache

# 验证配置
python -c "from config.settings import settings; print('配置验证通过')"
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

## Docker 部署

### 1. 构建 Docker 镜像

创建 `Dockerfile`:

```dockerfile
# 多阶段构建
FROM python:3.11-slim as builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --user -r requirements.txt

# 最终镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 从 builder 复制已安装的依赖
COPY --from=builder /root/.local /root/.local

# 更新 PATH
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p logs data_cache

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# 启动命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

构建镜像：

```bash
docker build -t stock-analysis-system:latest .
```

### 2. 运行容器

```bash
docker run -d \
  --name stock-analysis \
  -p 8000:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data_cache:/app/data_cache \
  --env-file .env \
  stock-analysis-system:latest
```

### 3. 查看日志

```bash
# 查看容器日志
docker logs -f stock-analysis

# 查看应用日志
tail -f logs/stock_analysis.log
```

### 4. 停止和删除容器

```bash
# 停止容器
docker stop stock-analysis

# 删除容器
docker rm stock-analysis
```

## Docker Compose 部署

### 1. 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  stock-analysis:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: stock-analysis
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
      - ./data_cache:/app/data_cache
    env_file:
      - .env
    environment:
      - ENVIRONMENT=production
      - API__HOST=0.0.0.0
      - API__PORT=8000
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    networks:
      - stock-analysis-network

  # 可选：添加 Redis 用于缓存
  redis:
    image: redis:7-alpine
    container_name: stock-analysis-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - stock-analysis-network

  # 可选：添加 PostgreSQL 数据库
  postgres:
    image: postgres:15-alpine
    container_name: stock-analysis-postgres
    environment:
      POSTGRES_DB: stock_analysis
      POSTGRES_USER: stock_user
      POSTGRES_PASSWORD: stock_password
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    networks:
      - stock-analysis-network

networks:
  stock-analysis-network:
    driver: bridge

volumes:
  redis-data:
  postgres-data:
```

### 2. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f stock-analysis
```

### 3. 停止服务

```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

## 生产环境部署

### 1. 使用 Nginx 反向代理

创建 Nginx 配置文件 `/etc/nginx/sites-available/stock-analysis`:

```nginx
upstream stock_analysis {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 证书配置
    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 日志
    access_log /var/log/nginx/stock-analysis-access.log;
    error_log /var/log/nginx/stock-analysis-error.log;

    # 客户端最大请求体大小
    client_max_body_size 10M;

    # 代理配置
    location / {
        proxy_pass http://stock_analysis;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSE 特殊配置
    location /api/v1/analysis/stream {
        proxy_pass http://stock_analysis;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 必需配置
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }

    # 静态文件（如果有）
    location /static {
        alias /path/to/static/files;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

启用配置：

```bash
# 创建符号链接
sudo ln -s /etc/nginx/sites-available/stock-analysis /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

### 2. 使用 Systemd 管理服务

创建 systemd 服务文件 `/etc/systemd/system/stock-analysis.service`:

```ini
[Unit]
Description=Stock Analysis System
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/path/to/stock-analysis-system
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

# 日志
StandardOutput=append:/var/log/stock-analysis/stdout.log
StandardError=append:/var/log/stock-analysis/stderr.log

# 安全配置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/path/to/stock-analysis-system/logs /path/to/stock-analysis-system/data_cache

[Install]
WantedBy=multi-user.target
```

管理服务：

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start stock-analysis

# 设置开机自启
sudo systemctl enable stock-analysis

# 查看状态
sudo systemctl status stock-analysis

# 查看日志
sudo journalctl -u stock-analysis -f
```

### 3. 使用 Supervisor 管理进程

安装 Supervisor：

```bash
sudo apt-get install supervisor
```

创建配置文件 `/etc/supervisor/conf.d/stock-analysis.conf`:

```ini
[program:stock-analysis]
command=/path/to/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
directory=/path/to/stock-analysis-system
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/stock-analysis/supervisor.log
stdout_logfile_maxbytes=50MB
stdout_logfile_backups=10
environment=PATH="/path/to/venv/bin"
```

管理进程：

```bash
# 重载配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动进程
sudo supervisorctl start stock-analysis

# 查看状态
sudo supervisorctl status stock-analysis

# 重启进程
sudo supervisorctl restart stock-analysis
```

## 监控配置

### 1. 应用监控

系统提供以下监控端点：

```bash
# 健康检查
GET /health

# 服务统计
GET /api/v1/analysis/stats

# 事件类型列表
GET /api/v1/analysis/event-types
```

### 2. 日志监控

使用 ELK Stack 或其他日志聚合工具：

```bash
# 安装 Filebeat
sudo apt-get install filebeat

# 配置 Filebeat 收集日志
# /etc/filebeat/filebeat.yml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /path/to/stock-analysis-system/logs/*.log
  json.keys_under_root: true
  json.add_error_key: true

output.elasticsearch:
  hosts: ["localhost:9200"]
```

### 3. 性能监控

使用 Prometheus + Grafana：

```python
# 在 api/main.py 中添加 Prometheus 指标
from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Response

# 定义指标
request_count = Counter('http_requests_total', 'Total HTTP requests')
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")
```

### 4. 告警配置

配置告警规则（Prometheus AlertManager）：

```yaml
groups:
- name: stock_analysis_alerts
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status="500"}[5m]) > 0.05
    for: 5m
    labels:
      severity: critical
    annotations:
      summary: "High error rate detected"
      description: "Error rate is {{ $value }} requests/sec"

  - alert: HighResponseTime
    expr: http_request_duration_seconds{quantile="0.95"} > 10
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High response time detected"
      description: "95th percentile response time is {{ $value }}s"
```

## 日志配置

### 1. 日志级别

根据环境设置合适的日志级别：

- **开发环境**: DEBUG
- **测试环境**: INFO
- **生产环境**: WARNING 或 ERROR

```bash
# 在 .env 中配置
LOG__LOG_LEVEL=WARNING
```

### 2. 日志轮转

系统使用 loguru 自动进行日志轮转：

```bash
# 配置日志轮转
LOG__LOG_ROTATION=1 day      # 每天轮转
LOG__LOG_RETENTION=30 days   # 保留30天
LOG__LOG_MAX_SIZE=100 MB     # 单文件最大100MB
```

### 3. 日志格式

日志采用 JSON 格式，便于解析和分析：

```json
{
  "timestamp": "2024-01-01T00:00:00.000Z",
  "level": "INFO",
  "logger": "api.sse_routes",
  "message": "Starting SSE stream",
  "session_id": "abc-123",
  "query": "分析贵州茅台"
}
```

### 4. 日志查询

使用 jq 查询 JSON 日志：

```bash
# 查询错误日志
cat logs/stock_analysis.log | jq 'select(.level == "ERROR")'

# 查询特定会话的日志
cat logs/stock_analysis.log | jq 'select(.session_id == "abc-123")'

# 统计错误数量
cat logs/stock_analysis.log | jq 'select(.level == "ERROR")' | wc -l
```

## 备份与恢复

### 1. 数据备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份日志
tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" logs/

# 备份缓存
tar -czf "$BACKUP_DIR/cache_$DATE.tar.gz" data_cache/

# 备份配置
cp .env "$BACKUP_DIR/env_$DATE"

# 删除30天前的备份
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
```

### 2. 定期备份

使用 cron 定期执行备份：

```bash
# 编辑 crontab
crontab -e

# 每天凌晨2点执行备份
0 2 * * * /path/to/backup.sh >> /var/log/stock-analysis-backup.log 2>&1
```

## 安全配置

### 1. API 密钥管理

- 使用环境变量存储密钥
- 不要将 `.env` 文件提交到版本控制
- 定期轮换 API 密钥
- 使用密钥管理服务（如 AWS Secrets Manager）

### 2. 网络安全

```bash
# 配置防火墙（UFW）
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# 限制 API 访问
# 在 .env 中配置
API__CORS_ORIGINS=["https://your-frontend-domain.com"]
```

### 3. HTTPS 配置

使用 Let's Encrypt 获取免费 SSL 证书：

```bash
# 安装 Certbot
sudo apt-get install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo certbot renew --dry-run
```

## 性能优化

### 1. 并发配置

根据服务器资源调整并发数：

```bash
# 计算推荐的 worker 数量
# workers = (2 * CPU核心数) + 1

# 4核CPU的推荐配置
uvicorn api.main:app --workers 9 --host 0.0.0.0 --port 8000
```

### 2. 缓存优化

```bash
# 启用缓存并调整参数
CACHE__ENABLE_CACHE=true
CACHE__CACHE_TTL=3600           # 1小时
CACHE__MAX_CACHE_SIZE_MB=2000   # 2GB
```

### 3. 数据库连接池

如果使用数据库，配置连接池：

```python
# 在 config/settings.py 中添加
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

## 故障排查

### 常见问题

1. **服务无法启动**
   ```bash
   # 检查端口占用
   sudo lsof -i :8000
   
   # 检查配置
   python -c "from config.settings import settings"
   ```

2. **SSE 连接断开**
   ```bash
   # 检查 Nginx 配置
   # 确保 proxy_buffering off
   # 增加 proxy_read_timeout
   ```

3. **内存占用过高**
   ```bash
   # 减少并发数
   PERFORMANCE__MAX_CONCURRENT_REQUESTS=5
   
   # 减少消息历史
   PERFORMANCE__MAX_MESSAGE_HISTORY=20
   ```

4. **API 调用超时**
   ```bash
   # 增加超时时间
   PERFORMANCE__REQUEST_TIMEOUT=600
   LLM__TIMEOUT=120
   ```

### 日志分析

```bash
# 查看最近的错误
tail -n 100 logs/stock_analysis.log | grep ERROR

# 统计错误类型
cat logs/stock_analysis.log | jq -r 'select(.level == "ERROR") | .message' | sort | uniq -c

# 查看慢请求
cat logs/stock_analysis.log | jq 'select(.duration_ms > 10000)'
```

## 升级与维护

### 1. 版本升级

```bash
# 备份当前版本
cp -r /path/to/stock-analysis-system /path/to/stock-analysis-system.backup

# 拉取新代码
git pull origin main

# 更新依赖
pip install -r requirements.txt --upgrade

# 重启服务
sudo systemctl restart stock-analysis
```

### 2. 数据库迁移

```bash
# 如果使用数据库，执行迁移
alembic upgrade head
```

### 3. 健康检查

```bash
#!/bin/bash
# health_check.sh

HEALTH_URL="http://localhost:8000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -eq 200 ]; then
    echo "Service is healthy"
    exit 0
else
    echo "Service is unhealthy (HTTP $RESPONSE)"
    exit 1
fi
```

## 联系与支持

如有部署问题或需要技术支持，请联系开发团队或提交 Issue。
