# Deployment Guide

This repository includes a `Dockerfile` and `render.yaml`, and can be deployed to Render or any other platform that supports Docker containers.

## Render

Create a service from the repository using Render Blueprint. The default `render.yaml` configuration includes:

- A free Docker web service in the Frankfurt region
- A `/healthz` health check
- 10 model requests per source IP per day, 20 per dining session per day, and 100 across the public demo per day

When creating the service, provide `MODEL_BASE_URL`, `MODEL_API_KEY`, and `MODEL_NAME` in the Render dashboard. These values are not committed to the repository. The selected model must accept images and produce structured output; see [Model Configuration](MODELS.en.md).

Visitors can upload their own menu images. The model API key stays on the server and is never sent to the browser or committed to the repository.

Render Free Web Services sleep after inactivity, so the first visit may take about a minute to wake up. They also do not support persistent disks, which means server-side sessions and images can disappear after a restart. The same browser keeps a local copy of the meal and reconnects with a new server session after recovery. This setup is appropriate for a portfolio demo, not a production service. See [Render Free](https://render.com/docs/free).

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

The current version has no user accounts; each session URL acts as an anonymous access credential. The default public-demo configuration allows 10 model requests per source IP per day, 20 per dining session per day, and 100 globally per day, with additional caps on session writes, active sessions, and stored images. Limits are kept in memory and reset when a free instance restarts; disable automatic billing or set a hard provider-side quota as the final cost guardrail. These are portfolio-demo controls, not a replacement for production authentication, monitoring, and alerting.

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
