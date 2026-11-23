# Model Configuration

DineTrail is not tied to a particular model vendor. A self-hosted deployment needs a model service that accepts images and returns structured JSON, along with the endpoint, model name, and API key chosen by the deployer.

Not every model is suitable for menu recognition. The selected model should support at least:

- Image input
- Reliable structured JSON output
- Multilingual menu understanding

## OpenAI-Compatible Endpoints

Use this mode for a cloud provider, gateway, or local inference server that implements the OpenAI Chat Completions API:

```text
MODEL_API_TYPE=openai_compatible
MODEL_BASE_URL=https://YOUR_PROVIDER.example/v1
MODEL_API_KEY=your_key
MODEL_NAME=your_vision_model
```

`MODEL_BASE_URL` may be an API root or a full URL ending in `/chat/completions`.

Adjust these settings to match the endpoint's capabilities:

```text
MODEL_RESPONSE_FORMAT=json_schema
MODEL_STREAM=true
```

Supported `MODEL_RESPONSE_FORMAT` values:

- `json_schema`: for endpoints with strict JSON Schema support
- `json_object`: for endpoints that support JSON Object mode only
- `prompt_only`: for endpoints that do not accept a `response_format` parameter; the prompt still requires JSON output

If the endpoint does not support streaming Chat Completions, set `MODEL_STREAM=false`. Menu items will still arrive in batches as image regions finish, but DineTrail will not parse token-level output.

Some providers use `max_completion_tokens` instead of `max_tokens`:

```text
MODEL_MAX_TOKENS_FIELD=max_completion_tokens
```

For a Qwen-compatible endpoint that supports the `enable_thinking` parameter, set:

```text
MODEL_COMPAT_MODE=qwen
```

## Native Gemini API

```text
MODEL_API_TYPE=gemini
MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta
MODEL_API_KEY=your_key
MODEL_NAME=your_gemini_model
```

The native Gemini adapter currently uses complete responses rather than token-level streaming.

## Optional OCR Coordinate Calibration

The primary model handles menu recognition, chat, and ordering on its own. OCR is used only to place more precise highlights over selected dishes in the source menu image, so it is optional.

Qwen OCR is currently supported for coordinate calibration:

```text
OCR_PROVIDER=qwen
OCR_BASE_URL=https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
OCR_API_KEY=your_key
OCR_MODEL=qwen-vl-ocr
```

To run without coordinate calibration:

```text
OCR_PROVIDER=none
```

## Legacy Environment Variables

The older `MODEL_PROVIDER`, `DASHSCOPE_API_KEY`, `QWEN_MODEL`, `QWEN_BASE_URL`, `GEMINI_API_KEY`, and `GEMINI_MODEL` variables remain supported for backward compatibility. New deployments should use the generic variables above.

Keep API keys in a local `.env` file or in the deployment platform's secret store. Never commit them to GitHub.
