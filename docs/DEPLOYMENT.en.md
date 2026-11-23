# Deployment Guide

This repository includes a `Dockerfile` and `render.yaml`, and can be deployed to Render or any other platform that supports Docker containers.

## Render

Create a service from the repository using Render Blueprint. The default `render.yaml` configuration includes:

- A Docker web service in the Frankfurt region
- A `/healthz` health check
- A 1 GB persistent disk mounted at `/data`

When creating the service, provide `MODEL_BASE_URL`, `MODEL_API_KEY`, and `MODEL_NAME` in the Render dashboard. These values are not committed to the repository. The selected model must accept images and produce structured output; see [Model Configuration](MODELS.en.md).

Render's free web services do not support persistent disks and go to sleep when idle, so they are suitable only for temporary testing. To preserve dining sessions and uploaded menu images, use an instance with persistent storage. See Render's documentation for [free services](https://render.com/docs/free) and [persistent disks](https://render.com/docs/disks).

## Other Container Platforms

Set at least the following environment variables:

```text
MODEL_API_TYPE=openai_compatible
MODEL_BASE_URL=https://YOUR_PROVIDER.example/v1
MODEL_API_KEY=...
MODEL_NAME=YOUR_VISION_MODEL
HOST=0.0.0.0
PORT=4173
SESSION_DATA_DIR=/data
```

You may use the native Gemini adapter instead. See [Model Configuration](MODELS.en.md) for provider options and optional OCR setup.

Mount persistent storage at `/data`. Otherwise, dining sessions and uploaded menu images will be lost whenever the service restarts.

Use `/healthz` as the health-check endpoint. It returns 200 only when SQLite is writable and a model API key is configured.

The current version has no user accounts; each session URL acts as an anonymous access credential. By default, the service allows 60 model requests per source IP per hour and 300 model requests across the service per hour. It also limits session writes, active sessions, and total server-side image storage. These safeguards help control MVP costs, but they are not a substitute for a production account system, monitoring, or alerting.

## Verify a Deployment

After deployment, run:

```bash
python3 scripts/smoke_public.py https://YOUR-SERVICE.onrender.com
```

The script checks HTTPS, model configuration, session creation and recovery, session deletion, and image persistence.

To include one real menu-recognition request:

```bash
python3 scripts/smoke_public.py \
  https://YOUR-SERVICE.onrender.com \
  --menu-image /path/to/menu.jpg
```

The smoke test deletes only the sessions it creates and does not modify user sessions.
