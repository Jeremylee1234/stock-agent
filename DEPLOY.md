# 部署指南

将项目推送到 GitHub 后，在 Linux 服务器上用 Docker 一键部署股票分析 Agent API。

## 前置条件

**本机（推送代码）**
- Git
- GitHub 账号

**服务器**
- Linux（Ubuntu 22.04+ / CentOS 8+ 等）
- Docker 20.10+ 与 Docker Compose v2
- 出站网络（访问 DeepSeek、iFinD、Tushare 等 API）
- 开放端口（默认 8000）

---

## 第一步：推送到 GitHub

### 1. 在 GitHub 创建仓库

登录 [github.com/new](https://github.com/new)，创建空仓库（不要勾选 README），例如：

```
仓库名: stock-agent
可见性: Private（推荐，含业务逻辑）
```

### 2. 本机推送代码

在项目根目录执行：

```bash
cd "/Users/sh-data-03/Desktop/ai agent"

git init
git add .
git commit -m "Initial commit: stock analysis agent with Docker deployment"

# 替换为你的 GitHub 用户名和仓库名
git remote add origin https://github.com/YOUR_USERNAME/stock-agent.git
git branch -M main
git push -u origin main
```

> **注意**：`.env` 已在 `.gitignore` 中，不会被推送。密钥只在服务器本地配置。

---

## 第二步：服务器安装 Docker

### Ubuntu / Debian

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 重新登录 SSH 使 docker 组生效
docker --version
docker compose version
```

### 国内服务器可选镜像加速

编辑 `/etc/docker/daemon.json`：

```json
{
  "registry-mirrors": ["https://docker.1ms.run"]
}
```

```bash
sudo systemctl restart docker
```

---

## 第三步：克隆并部署

```bash
git clone https://github.com/YOUR_USERNAME/stock-agent.git
cd stock-agent

cp .env.example .env
nano .env   # 填入 DEEPSEEK_API_KEY、TUSHARE_TOKEN、IFIND_REFRESH_TOKEN

bash scripts/deploy.sh
```

部署成功后访问：

| 地址 | 说明 |
|------|------|
| `http://服务器IP:8000/health` | 健康检查 |
| `http://服务器IP:8000/api/docs` | Swagger 文档 |
| `http://服务器IP:8000/demo` | Web 演示页 |

---

## 常用运维命令

```bash
docker compose logs -f          # 查看日志
docker compose restart          # 重启
git pull && bash scripts/deploy.sh   # 更新后重新部署
docker compose down             # 停止
```

---

## Nginx 反向代理（生产环境推荐）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/v1/analysis/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
        proxy_set_header Connection '';
        chunked_transfer_encoding off;
    }
}
```

HTTPS：`sudo certbot --nginx -d your-domain.com`

---

## 环境变量说明

| 变量 | 必需 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek LLM API 密钥 |
| `DATA_SOURCE__TUSHARE_TOKEN` | 否 | Tushare 数据源 |
| `IFIND_REFRESH_TOKEN` | 否 | iFinD 数据源（会过期） |
| `API__PORT` | 否 | 对外端口，默认 8000 |

完整配置见 `.env.example`。
