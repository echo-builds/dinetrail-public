# 部署指南

仓库包含 `Dockerfile` 和 `render.yaml`，可以部署到 Render 或其他支持 Docker 的平台。

## Render

使用仓库中的 Blueprint 创建服务。`render.yaml` 默认配置包括：

- Frankfurt 区域的免费 Docker Web Service
- `/healthz` 健康检查
- 每个来源 IP 每天 10 次、每次用餐每天 20 次、全站每天 100 次模型请求

创建服务时，在 Render 后台填写 `MODEL_BASE_URL`、`MODEL_API_KEY` 和 `MODEL_NAME`。这些配置不会写入仓库。所选模型需要支持图片理解和结构化输出，具体选项见[模型配置](MODELS.md)。

访客可以直接上传自己的菜单图片，模型密钥只保存在服务端，不会发送到浏览器或写入仓库。

Render 免费 Web Service 空闲后会休眠，首次打开可能需要等待约一分钟；它也不支持持久化磁盘，因此服务重启后服务端会话和原图可能丢失。同一浏览器会保留本地用餐记录，并在服务恢复后建立新会话。该方案适合作品体验，不等同于正式生产服务。平台限制见 [Render Free 文档](https://render.com/docs/free)。

## 通用容器平台

至少配置以下环境变量：

```text
MODEL_API_TYPE=openai_compatible
MODEL_BASE_URL=https://YOUR_PROVIDER.example/v1
MODEL_API_KEY=...
MODEL_NAME=YOUR_VISION_MODEL
HOST=0.0.0.0
PORT=4173
SESSION_DATA_DIR=/data
```

也可以改用 Gemini 原生接口。模型与可选 OCR 的完整配置见[模型配置](MODELS.md)。

将 `/data` 挂载到持久化磁盘，否则服务重启后点餐会话和原图会丢失。

平台健康检查路径为 `/healthz`。只有在 SQLite 可读写且模型密钥已配置时，接口才返回 200。

当前版本没有用户账号，会话 URL 是匿名访问凭证。仓库默认的免费体验配置限制为每个来源 IP 每天 10 次、每次用餐每天 20 次、全站每天 100 次模型请求，并限制会话写入、活跃会话数和服务端图片总量。限额保存在进程内，免费实例重启后会重新计算；模型平台侧仍应关闭自动充值或设置硬额度。这些是作品体验阶段的成本保护，不替代正式账号体系和监控告警。

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
