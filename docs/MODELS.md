# 模型配置

DineTrail 不绑定特定模型供应商。自行部署时，需要选择一个支持图片理解和结构化 JSON 输出的模型服务，并配置自己的接口地址、模型名称与 API Key。

不是所有模型都适合菜单识别。所选模型至少应支持：

- 图片输入
- 稳定的结构化 JSON 输出
- 多语言菜单理解

## OpenAI-compatible 接口

适用于提供 OpenAI Chat Completions 兼容接口的云模型、网关或本地推理服务：

```text
MODEL_API_TYPE=openai_compatible
MODEL_BASE_URL=https://YOUR_PROVIDER.example/v1
MODEL_API_KEY=your_key
MODEL_NAME=your_vision_model
```

`MODEL_BASE_URL` 可以填写 API 根地址，也可以直接填写以 `/chat/completions` 结尾的完整地址。

按模型服务能力调整：

```text
MODEL_RESPONSE_FORMAT=json_schema
MODEL_STREAM=true
```

`MODEL_RESPONSE_FORMAT` 支持：

- `json_schema`：模型服务支持严格 JSON Schema 时使用
- `json_object`：只支持 JSON Object 模式时使用
- `prompt_only`：不支持 `response_format` 参数时使用，由提示词约束 JSON 输出

不支持流式 Chat Completions 时，将 `MODEL_STREAM` 设为 `false`。菜单仍会按识别区域逐批出现，但不会使用 token 流式解析。

少数服务使用 `max_completion_tokens`，可配置：

```text
MODEL_MAX_TOKENS_FIELD=max_completion_tokens
```

使用支持 thinking 参数的 Qwen 兼容接口时，可配置：

```text
MODEL_COMPAT_MODE=qwen
```

## Gemini 原生接口

```text
MODEL_API_TYPE=gemini
MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta
MODEL_API_KEY=your_key
MODEL_NAME=your_gemini_model
```

Gemini 原生接口当前使用完整响应，不进行 token 流式解析。

## 可选 OCR 坐标校准

主模型可以独立完成菜单识别、对话和点单。OCR 只用于把已选菜品更精确地标注回菜单原图，不配置也不影响核心流程。

当前坐标校准适配了 Qwen OCR：

```text
OCR_PROVIDER=qwen
OCR_BASE_URL=https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
OCR_API_KEY=your_key
OCR_MODEL=qwen-vl-ocr
```

不需要坐标校准时：

```text
OCR_PROVIDER=none
```

## 旧配置兼容

旧版的 `MODEL_PROVIDER`、`DASHSCOPE_API_KEY`、`QWEN_MODEL`、`QWEN_BASE_URL`、`GEMINI_API_KEY` 和 `GEMINI_MODEL` 仍可使用，但新部署建议使用通用变量。

API Key 只应保存在本地 `.env` 或部署平台的 Secret 中，不要提交到 GitHub。
