# 部署指南

仓库包含 `Dockerfile` 和 `render.yaml`，可以部署到 Render 或其他支持 Docker 的平台。

## Render

使用仓库中的 Blueprint 创建服务。`render.yaml` 默认配置包括：

- Frankfurt 区域的 Docker Web Service
- `/healthz` 健康检查
- 挂载到 `/data` 的 1 GB 持久化磁盘

在 Render 后台配置不会写入仓库的 `DASHSCOPE_API_KEY`。

Render 的免费 Web Service 不支持持久化磁盘，且空闲后会休眠，只适合临时验证。需要保存点餐会话和原图时，应使用支持持久化磁盘的实例。平台限制见 [Render Free 文档](https://render.com/docs/free) 与 [Persistent Disks 文档](https://render.com/docs/disks)。

## 通用容器平台

至少配置以下环境变量：

```text
DASHSCOPE_API_KEY=...
HOST=0.0.0.0
PORT=4173
SESSION_DATA_DIR=/data
```

将 `/data` 挂载到持久化磁盘，否则服务重启后点餐会话和原图会丢失。

平台健康检查路径为 `/healthz`。只有在 SQLite 可读写且模型密钥已配置时，接口才返回 200。

当前版本没有用户账号，会话 URL 是匿名访问凭证。匿名接口默认限制为每个来源 IP 每小时 60 次模型请求、全站每小时 300 次模型请求，并限制会话写入、活跃会话数和服务端图片总量。这些是 MVP 阶段的成本保护，不替代正式账号体系和监控告警。

## 部署验证

部署完成后运行：

```bash
python3 scripts/smoke_public.py https://YOUR-SERVICE.onrender.com
```

脚本会验证 HTTPS、模型配置、会话创建与恢复、会话删除以及原图保存与恢复。

如需同时验证一次真实模型识别：

```bash
python3 scripts/smoke_public.py \
  https://YOUR-SERVICE.onrender.com \
  --menu-image /path/to/menu.jpg
```

冒烟脚本只删除自己创建的测试会话，不会改动用户会话。
