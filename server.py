#!/usr/bin/env python3
import base64
import collections
import concurrent.futures
import copy
import difflib
import html
import ipaddress
import json
import math
import mimetypes
import os
import pathlib
import queue
import re
import sqlite3
import struct
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = pathlib.Path(__file__).parent / "public"


def load_local_env():
    env_path = pathlib.Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)


load_local_env()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "4173"))


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def openai_chat_endpoint(base_url):
    base_url = str(base_url or "").strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
LEGACY_PROVIDER = os.environ.get("MODEL_PROVIDER", "").strip().lower()
PROVIDER = os.environ.get("MODEL_API_TYPE", "").strip().lower()
if not PROVIDER:
    PROVIDER = "gemini" if LEGACY_PROVIDER == "gemini" else "openai_compatible"
if PROVIDER in {"openai", "openai-compatible", "openai_compat"}:
    PROVIDER = "openai_compatible"
if PROVIDER not in {"openai_compatible", "gemini"}:
    raise RuntimeError("MODEL_API_TYPE 只支持 openai_compatible 或 gemini")

if PROVIDER == "openai_compatible":
    API_KEY = os.environ.get("MODEL_API_KEY") or DASHSCOPE_API_KEY
    MODEL = os.environ.get("MODEL_NAME") or os.environ.get("QWEN_MODEL", "")
    if not MODEL and DASHSCOPE_API_KEY:
        MODEL = "qwen3.8-flash"
    model_base_url = os.environ.get("MODEL_BASE_URL") or os.environ.get("QWEN_BASE_URL", "")
    if not model_base_url and DASHSCOPE_API_KEY:
        model_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL_ENDPOINT = openai_chat_endpoint(model_base_url)
else:
    API_KEY = os.environ.get("MODEL_API_KEY") or GEMINI_API_KEY
    MODEL = os.environ.get("MODEL_NAME") or os.environ.get("GEMINI_MODEL", "")
    if not MODEL and GEMINI_API_KEY:
        MODEL = "gemini-3.6-flash"
    MODEL_ENDPOINT = (
        os.environ.get("MODEL_BASE_URL")
        or os.environ.get("GEMINI_BASE_URL")
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")

MODEL_RESPONSE_FORMAT = os.environ.get("MODEL_RESPONSE_FORMAT", "json_schema").strip().lower()
if MODEL_RESPONSE_FORMAT not in {"json_schema", "json_object", "prompt_only"}:
    raise RuntimeError("MODEL_RESPONSE_FORMAT 只支持 json_schema、json_object 或 prompt_only")
MODEL_MAX_TOKENS_FIELD = os.environ.get("MODEL_MAX_TOKENS_FIELD", "max_tokens").strip()
if MODEL_MAX_TOKENS_FIELD not in {"max_tokens", "max_completion_tokens"}:
    raise RuntimeError("MODEL_MAX_TOKENS_FIELD 配置无效")
MODEL_STREAM_ENABLED = PROVIDER == "openai_compatible" and env_flag("MODEL_STREAM", True)
MODEL_COMPAT_MODE = os.environ.get("MODEL_COMPAT_MODE", "").strip().lower()
if not MODEL_COMPAT_MODE and (
    LEGACY_PROVIDER == "qwen" or "dashscope.aliyuncs.com" in MODEL_ENDPOINT
):
    MODEL_COMPAT_MODE = "qwen"

if not API_KEY or not MODEL or not MODEL_ENDPOINT:
    API_KEY = None

RETRY_DELAYS = (2, 5, 10)
MODEL_READ_TIMEOUT_SECONDS = int(os.environ.get("MODEL_READ_TIMEOUT_SECONDS", "240"))
OCR_READ_TIMEOUT_SECONDS = int(os.environ.get("OCR_READ_TIMEOUT_SECONDS", "120"))
MENU_SECTION_CONCURRENCY = int(os.environ.get("MENU_SECTION_CONCURRENCY", "4"))
OCR_PROVIDER = os.environ.get("OCR_PROVIDER", "").strip().lower()
if not OCR_PROVIDER:
    OCR_PROVIDER = "qwen" if DASHSCOPE_API_KEY else "none"
OCR_API_KEY = os.environ.get("OCR_API_KEY") or (DASHSCOPE_API_KEY if OCR_PROVIDER == "qwen" else None)
OCR_MODEL = os.environ.get("OCR_MODEL") or os.environ.get("QWEN_OCR_MODEL", "qwen-vl-ocr")
OCR_ENDPOINT = os.environ.get("OCR_BASE_URL") or os.environ.get(
    "QWEN_OCR_ENDPOINT",
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
)
OCR_ENABLED = OCR_PROVIDER == "qwen" and bool(OCR_API_KEY and OCR_MODEL and OCR_ENDPOINT)

XHS_PAGE_HOSTS = {
    "xiaohongshu.com", "www.xiaohongshu.com",
    "xhslink.com", "www.xhslink.com",
    "xhslink.cn", "www.xhslink.cn",
}
XHS_IMAGE_HOST_SUFFIX = ".xhscdn.com"
XHS_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
XHS_MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
XHS_MAX_PAGE_BYTES = 6 * 1024 * 1024
XHS_MAX_IMAGE_BYTES = 4 * 1024 * 1024
XHS_MAX_TOTAL_IMAGE_BYTES = 10 * 1024 * 1024
XHS_MAX_IMAGES = 9

ECB_EUR_CNY_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
EUR_CNY_CACHE = {"rate": None, "date": None, "fetched_at": 0}
EUR_CNY_LOCK = threading.Lock()


def parse_ecb_eur_cny(payload):
    root = ET.fromstring(payload)
    date = next((node.attrib["time"] for node in root.iter() if "time" in node.attrib), None)
    rate_text = next((node.attrib["rate"] for node in root.iter()
                      if node.attrib.get("currency") == "CNY" and "rate" in node.attrib), None)
    rate = float(rate_text) if rate_text else 0
    if not date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not math.isfinite(rate) or rate <= 0:
        raise ValueError("欧元兑人民币参考汇率暂不可用")
    return {"rate": rate, "date": date, "source": "ECB"}


def eur_cny_reference_rate():
    with EUR_CNY_LOCK:
        now = time.time()
        if EUR_CNY_CACHE["rate"] and now - EUR_CNY_CACHE["fetched_at"] < 6 * 3600:
            return {key: EUR_CNY_CACHE[key] for key in ("rate", "date", "source")}
        try:
            request = urllib.request.Request(ECB_EUR_CNY_URL, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=6) as response:
                payload = response.read(65537)
            if len(payload) > 65536:
                raise ValueError("汇率数据过大")
            result = parse_ecb_eur_cny(payload)
            EUR_CNY_CACHE.update(result, fetched_at=now)
            return result
        except (ValueError, ET.ParseError, urllib.error.URLError, TimeoutError, OSError):
            if EUR_CNY_CACHE["rate"] and now - EUR_CNY_CACHE["fetched_at"] < 72 * 3600:
                return {key: EUR_CNY_CACHE[key] for key in ("rate", "date", "source")}
            raise ValueError("人民币参考金额暂不可用")

SESSION_DATA_DIR = pathlib.Path(os.environ.get("SESSION_DATA_DIR", pathlib.Path(__file__).parent / ".data"))
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(48 * 60 * 60)))
SESSION_MAX_STATE_BYTES = 2 * 1024 * 1024
SESSION_MAX_IMAGE_BYTES = 8 * 1024 * 1024
SESSION_MAX_TOTAL_IMAGE_BYTES = 80 * 1024 * 1024
SESSION_MAX_STORED_IMAGE_BYTES = int(os.environ.get("SESSION_MAX_STORED_IMAGE_BYTES", str(512 * 1024 * 1024)))
SESSION_MAX_ACTIVE = int(os.environ.get("SESSION_MAX_ACTIVE", "500"))
SESSION_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
SESSION_IMAGE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")

RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "3600"))
MODEL_REQUESTS_PER_WINDOW = int(os.environ.get("MODEL_REQUESTS_PER_WINDOW", "60"))
MODEL_REQUESTS_PER_SESSION_WINDOW = int(os.environ.get("MODEL_REQUESTS_PER_SESSION_WINDOW", "90"))
MODEL_REQUESTS_GLOBAL_PER_WINDOW = int(os.environ.get("MODEL_REQUESTS_GLOBAL_PER_WINDOW", "300"))
SESSION_WRITES_PER_WINDOW = int(os.environ.get("SESSION_WRITES_PER_WINDOW", "600"))
MODEL_API_PATHS = {
    "/api/analyze-guide-source",
    "/api/analyze-guide",
    "/api/analyze-menu",
    "/api/analyze-menu-stream",
    "/api/match-guide",
    "/api/locate-menu",
    "/api/enrich-dishes",
    "/api/chat",
}
RATE_EVENTS = collections.defaultdict(collections.deque)
RATE_LOCK = threading.Lock()


GUIDE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["restaurant", "items"],
    "properties": {
        "restaurant": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "nameZh", "nameOriginal", "rating", "sentiment", "note", "sourceQuote"],
                "properties": {
                    "id": {"type": "string"},
                    "nameZh": {"type": "string"},
                    "nameOriginal": {"type": "string"},
                    "rating": {"type": "number", "minimum": 0, "maximum": 5},
                    "sentiment": {"type": "string", "enum": ["recommended", "mentioned", "caution"]},
                    "note": {"type": "string"},
                    "sourceQuote": {"type": "string"},
                },
            },
        },
    },
}

GUIDE_MATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["dishId", "guideItemIds"],
                "properties": {
                    "dishId": {"type": "string"},
                    "guideItemIds": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

MENU_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "title", "pricing", "dishes"],
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "pricing": {
            "type": "object",
            "additionalProperties": False,
            "required": ["mode", "fixedPrice", "note"],
            "properties": {
                "mode": {"type": "string", "enum": ["a_la_carte", "fixed_menu", "multiple_fixed_menus", "unknown"]},
                "fixedPrice": {"type": "number"},
                "note": {"type": "string"},
            },
        },
        "dishes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "original", "descriptionOriginal", "nameZh", "summary", "decisionHint", "price", "priceOptions", "tags", "guideMatchIds", "box"],
                "properties": {
                    "id": {"type": "string"},
                    "original": {"type": "string"},
                    "descriptionOriginal": {"type": "string"},
                    "nameZh": {"type": "string"},
                    "summary": {"type": "string"},
                    "decisionHint": {"type": "string"},
                    "price": {"type": "number"},
                    "priceOptions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["label", "price"],
                            "properties": {
                                "label": {"type": "string"},
                                "price": {"type": "number"},
                            },
                        },
                    },
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "guideMatchIds": {"type": "array", "items": {"type": "string"}},
                    "box": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["x", "y", "w", "h"],
                        "properties": {
                            "x": {"type": "number"}, "y": {"type": "number"},
                            "w": {"type": "number"}, "h": {"type": "number"},
                        },
                    },
                },
            },
        },
    },
}

ENRICH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "decisionHint"],
                "properties": {
                    "id": {"type": "string"},
                    "decisionHint": {"type": "string"},
                },
            },
        },
    },
}

STREAM_MENU_SCHEMA = copy.deepcopy(MENU_SCHEMA)
STREAM_DISH_SCHEMA = STREAM_MENU_SCHEMA["properties"]["dishes"]["items"]
STREAM_DISH_SCHEMA["required"].append("aiDecisionHint")
STREAM_DISH_SCHEMA["properties"]["aiDecisionHint"] = {"type": "string"}
STREAM_DISH_SCHEMA["required"].extend(["menuRecommendationLabel", "menuRecommendationEvidence"])
STREAM_DISH_SCHEMA["properties"]["menuRecommendationLabel"] = {"type": "string"}
STREAM_DISH_SCHEMA["properties"]["menuRecommendationEvidence"] = {"type": "string"}

CHAT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["message", "dishIds", "actions"],
    "properties": {
        "message": {"type": "string"},
        "dishIds": {"type": "array", "items": {"type": "string"}},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "dishId"],
                "properties": {
                    "type": {"type": "string", "enum": ["add", "remove"]},
                    "dishId": {"type": "string"},
                },
            },
        },
    },
}


def image_inputs(image):
    if not image:
        return []
    return [image] if isinstance(image, str) else list(image)


def openai_compatible_request(prompt, schema, name, image, max_output_tokens, stream=False):
    request_prompt = prompt
    if MODEL_RESPONSE_FORMAT != "json_schema":
        request_prompt = (
            f"{prompt}\n"
            "返回内容必须是一个 JSON 值，不要使用 Markdown 代码块或添加解释。"
            "JSON 必须严格符合以下 Schema，所有 required 字段都必须返回：\n"
            f"{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}"
        )
    content = [{"type": "text", "text": request_prompt}]
    for item in image_inputs(image):
        if not item.startswith("data:image/") or ";base64," not in item:
            raise ValueError("图片格式无效")
        content.append({"type": "image_url", "image_url": {"url": item}})
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        MODEL_MAX_TOKENS_FIELD: max_output_tokens,
    }
    if MODEL_RESPONSE_FORMAT == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": name, "strict": True, "schema": schema},
        }
    elif MODEL_RESPONSE_FORMAT == "json_object":
        payload["response_format"] = {"type": "json_object"}
    if MODEL_COMPAT_MODE == "qwen":
        payload["enable_thinking"] = False
    if stream:
        payload["stream"] = True
    return urllib.request.Request(
        MODEL_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )


def qwen_request(prompt, schema, name, image, max_output_tokens, stream=False):
    """Backward-compatible alias for older integrations."""
    return openai_compatible_request(prompt, schema, name, image, max_output_tokens, stream)


def gemini_request(prompt, schema, image, max_output_tokens):
    parts = [{"text": prompt}]
    for item in image_inputs(image):
        if not item.startswith("data:") or "," not in item:
            raise ValueError("图片必须是 data URL")
        header, data = item.split(",", 1)
        mime_type = header[5:].split(";", 1)[0]
        if not mime_type.startswith("image/") or ";base64" not in header:
            raise ValueError("图片格式无效")
        parts.append({"inlineData": {"mimeType": mime_type, "data": data}})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
            "maxOutputTokens": max_output_tokens,
        },
    }
    model_path = urllib.parse.quote(MODEL, safe="-._")
    return urllib.request.Request(
        f"{MODEL_ENDPOINT}/models/{model_path}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )


def normalize_result(parsed, schema, name):
    if schema.get("type") != "object":
        return parsed
    if isinstance(parsed, dict):
        required = set(schema.get("required", []))
        if required and not required.issubset(parsed):
            nested = [
                value for value in parsed.values()
                if isinstance(value, dict) and required.issubset(value)
            ]
            if len(nested) == 1:
                return nested[0]
        return parsed
    if not isinstance(parsed, list):
        return parsed
    objects = [item for item in parsed if isinstance(item, dict)]
    if len(objects) != len(parsed) or not objects:
        return parsed
    if len(objects) == 1:
        return objects[0]
    if name == "menu_page":
        if all(isinstance(item.get("dishes"), list) for item in objects):
            return {
                "id": objects[0].get("id", "menu-page"),
                "title": objects[0].get("title", "现场菜单"),
                "pricing": objects[0].get("pricing", {"mode": "unknown", "fixedPrice": 0, "note": ""}),
                "dishes": [dish for item in objects for dish in item["dishes"]],
            }
        if all("original" in item and "nameZh" in item for item in objects):
            return {
                "id": "menu-page",
                "title": "现场菜单",
                "pricing": {"mode": "unknown", "fixedPrice": 0, "note": ""},
                "dishes": objects,
            }
    if name == "guide_candidates" and all("nameZh" in item for item in objects):
        return {"restaurant": "", "items": objects}
    return parsed


FRENCH_NAME_STOP_WORDS = {
    "a", "au", "aux", "avec", "de", "des", "du", "et", "la", "le", "les",
    "maison", "notre", "nos", "pour", "sa", "son", "sur", "un", "une",
}

GENERIC_GUIDE_DISH_NAMES = {
    "牛排", "牛肉", "猪肉", "羊肉", "鸡肉", "烤鸡", "烤鸡肉", "鸭肉", "鱼", "海鲜",
    "汤", "沙拉", "意面", "面", "汉堡", "甜点", "蛋糕", "咖啡", "茶", "酒",
}


def normalized_name(value):
    decomposed = unicodedata.normalize("NFKD", str(value or "").lower())
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def informative_name_tokens(value):
    return {token for token in normalized_name(value).split() if token not in FRENCH_NAME_STOP_WORDS and len(token) > 1}


def normalized_chinese_name(value):
    return "".join(re.findall(r"[\u3400-\u9fff]", str(value or "")))


def chinese_bigrams(value):
    text = normalized_chinese_name(value)
    return {text[index:index + 2] for index in range(max(0, len(text) - 1))}


def generic_guide_item(guide_item):
    return normalized_chinese_name(guide_item.get("nameZh")) in GENERIC_GUIDE_DISH_NAMES


def dish_matches_guide_item(dish, guide_item):
    if generic_guide_item(guide_item):
        return False
    dish_original = normalized_name(str(dish.get("original", "")).splitlines()[0])
    guide_original = normalized_name(guide_item.get("nameOriginal"))
    if min(len(dish_original), len(guide_original)) >= 5 and (
        dish_original in guide_original or guide_original in dish_original
    ):
        return True
    dish_tokens = informative_name_tokens(dish_original)
    guide_tokens = informative_name_tokens(guide_original)
    common = dish_tokens & guide_tokens
    if len(common) >= 2 and len(common) / max(1, len(guide_tokens)) >= 0.67:
        return True

    dish_zh = normalized_chinese_name(dish.get("nameZh"))
    guide_zh = normalized_chinese_name(guide_item.get("nameZh"))
    if min(len(dish_zh), len(guide_zh)) >= 2 and (dish_zh in guide_zh or guide_zh in dish_zh):
        return True
    guide_pairs = chinese_bigrams(guide_zh)
    common_pairs = chinese_bigrams(dish_zh) & guide_pairs
    return bool(guide_pairs) and len(common_pairs) / len(guide_pairs) >= 0.6


def validate_guide_matches(menu, guide_items):
    guide_by_id = {
        str(item.get("id")): item
        for item in guide_items
        if isinstance(item, dict) and item.get("id")
    }
    for dish in menu.get("dishes", []):
        dish["guideMatchIds"] = [
            match_id
            for match_id in dish.get("guideMatchIds", [])
            if match_id in guide_by_id and dish_matches_guide_item(dish, guide_by_id[match_id])
        ]
    return menu


def assign_guide_matches(menu, guide_items):
    valid_items = [
        item for item in guide_items
        if isinstance(item, dict) and item.get("id")
    ]
    for dish in menu.get("dishes", []):
        dish["guideMatchIds"] = [
            str(item["id"])
            for item in valid_items
            if dish_matches_guide_item(dish, item)
        ]
    return menu


def model_guide_matches(dishes, guide_items):
    clean_dishes = [
        {
            "id": dish.get("id"),
            "original": dish.get("original", ""),
            "nameZh": dish.get("nameZh", ""),
            "summary": dish.get("summary", ""),
        }
        for dish in dishes
        if isinstance(dish, dict) and dish.get("id")
    ]
    clean_guide = [
        {
            "id": item.get("id"),
            "nameOriginal": item.get("nameOriginal", ""),
            "nameZh": item.get("nameZh", ""),
            "note": item.get("note", ""),
            "sourceQuote": item.get("sourceQuote", ""),
        }
        for item in guide_items
        if isinstance(item, dict) and item.get("id")
    ]
    if not clean_dishes or not clean_guide:
        return {dish["id"]: [] for dish in clean_dishes}
    prompt = (
        "严格按 JSON Schema 返回攻略菜与现场菜单的匹配。"
        "只匹配确实是同一个菜单项目的项，可以利用多语言名称、常见别名、主要食材、配料和制作方式。"
        "不要因为都是汤、牛排、甜点等宽泛类别就匹配。"
        "不确定时不匹配；宁可漏掉，不要误标。"
        "只能使用输入中已有的 dishId 和 guideItemIds。\n"
        f"攻略候选：{json.dumps(clean_guide, ensure_ascii=False)}\n"
        f"现场菜单：{json.dumps(clean_dishes, ensure_ascii=False)}"
    )
    result = model_request(prompt, GUIDE_MATCH_SCHEMA, "guide_menu_matches", max_output_tokens=4096)
    dish_ids = {dish["id"] for dish in clean_dishes}
    guide_by_id = {item["id"]: item for item in clean_guide}
    guide_ids = set(guide_by_id)
    matches = {dish_id: [] for dish_id in dish_ids}
    for item in result.get("items", []):
        dish_id = item.get("dishId")
        if dish_id not in dish_ids:
            continue
        matches[dish_id] = [
            guide_id for guide_id in item.get("guideItemIds", [])
            if guide_id in guide_ids and not generic_guide_item(guide_by_id[guide_id])
        ]
    return matches


def menu_analysis_prompt(guide_items):
    return (
        "你正在直接阅读一张法国餐厅菜单图片。以图片的视觉栏目、字号、对齐和上下关系为准，不得按 OCR 返回的文字先后顺序猜测。"
        "从左到右阅读栏目，每栏内从上到下，逐项提取每一个可辨认、可点单的项目，并严格保持这个视觉顺序。"
        "不得按品类排除内容：食物、酒类、鸡尾酒、咖啡、茶、果汁、软饮及其他饮品都必须识别。"
        "栏目标题、酒类颜色小标题、店名、地址、容量列标题和广告文字不是可点项目，严禁当成菜品。"
        "严格按JSON Schema返回一个对象，不要在最外层使用数组。"
        "先判断价格结构：只有每个项目旁边分别印了价格才是 a_la_carte；"
        "如果页面顶部只有一个 Menu/Formule 总价、下面是可选前菜主菜甜点，必须标为 fixed_menu，fixedPrice 填套餐总价，所有没有独立标价的项目 price 填0；"
        "如果同一页有多种不同价格的 Menu/Formule 套餐，必须标为 multiple_fixed_menus，fixedPrice 填0，note 简要列出套餐价格；"
        "多套餐页面仍要把每个明确写出的可选项逐项提取，不能把整个 Menu/Formule 或一组套餐折叠成一项。"
        "不能把套餐总价复制到每个项目。看不清价格或结构则标 unknown，禁止猜价。"
        "若某个项目只是套餐内另加费用，price 仍填0，并在 summary 中明确‘另加X欧’。"
        "original 只填菜单上的项目名原文，不要混入价格、栏目标题或你的解释。"
        "descriptionOriginal 逐字保留该项目下方明确印出的配料或说明；没有则返回空字符串。"
        "nameZh 是忠实中文译名。summary 只翻译 descriptionOriginal 中明确写出的信息，不得补充常识配方、口感、评价或推荐；原图没有说明时 summary 和 decisionHint 统一填‘菜单未注明配方或口味’。"
        "decisionHint 与 summary 保持同义并压缩为一行，不得另外发挥。tags 只放原文明确支持的信息，否则返回空数组。guideMatchIds 始终返回空数组，攻略匹配由后续步骤完成。"
        "价格只能使用该项目同一行或明确对齐的数字，看不清就填0，不得借用上下项价格。"
        "只有一个价格时填 price，priceOptions 返回空数组。同一酒款或饮品按 15cl、50cl、75cl 等容量有多个价格时，price 填0，priceOptions 完整返回每个容量和对应价格。"
        "box 使用用户上传的完整原图左上为原点的0到1000相对坐标。"
        "box 必须紧密包住该项目的原文名称文字行，不要包含描述、价格、邻近项目或空白区域。"
        "先在图中确认名称的真实位置，再返回坐标；看不清的项目不要输出，更不能猜测。"
        "没有明确菜单总标题时，title 写‘现场菜单’。"
    )


def result_shape(value):
    if isinstance(value, dict):
        return f"object(keys={list(value.keys())[:8]})"
    if isinstance(value, list):
        first = value[0] if value else None
        first_detail = f", first_keys={list(first.keys())[:8]}" if isinstance(first, dict) else f", first_type={type(first).__name__}"
        return f"array(length={len(value)}{first_detail})"
    return type(value).__name__


def parse_model_json(value):
    if isinstance(value, (dict, list)):
        return value
    text = str(value or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_positions = [position for position in (text.find("{"), text.find("[")) if position >= 0]
        if not start_positions:
            raise
        parsed, _ = json.JSONDecoder().raw_decode(text[min(start_positions):])
        return parsed


def openai_message_content(result):
    choices = result.get("choices", [])
    content = choices[0].get("message", {}).get("content") if choices else None
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") in {None, "text", "output_text"}
        )
    return content


def model_request(prompt, schema, name, image=None, max_output_tokens=8192):
    if not API_KEY:
        raise RuntimeError("尚未配置模型 API Key")
    request = (
        openai_compatible_request(prompt, schema, name, image, max_output_tokens)
        if PROVIDER == "openai_compatible"
        else gemini_request(prompt, schema, image, max_output_tokens)
    )
    result = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            with urllib.request.urlopen(request, timeout=MODEL_READ_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:800]
            if error.code in {429, 500, 502, 503, 504} and attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
                continue
            if error.code in {429, 500, 502, 503, 504}:
                raise RuntimeError("模型服务暂时繁忙，请稍后重试") from error
            raise RuntimeError(f"模型接口失败 ({error.code}): {detail}") from error
    if PROVIDER == "openai_compatible":
        output_text = openai_message_content(result)
    else:
        output_text = None
        for candidate in result.get("candidates", []):
            text_parts = [part.get("text", "") for part in candidate.get("content", {}).get("parts", [])]
            if any(text_parts):
                output_text = "".join(text_parts)
                break
    if not output_text:
        block_reason = result.get("promptFeedback", {}).get("blockReason")
        detail = f"（{block_reason}）" if block_reason else ""
        raise RuntimeError(f"模型没有返回结构化结果{detail}")
    try:
        parsed = parse_model_json(output_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("模型返回了无效 JSON") from error
    parsed = normalize_result(parsed, schema, name)
    if schema.get("type") == "object" and not isinstance(parsed, dict):
        print(f"Unexpected {name} result shape: {result_shape(parsed)}")
        raise RuntimeError("模型返回的数据结构不符合要求")
    missing = [key for key in schema.get("required", []) if key not in parsed]
    if missing:
        print(f"Unexpected {name} result shape: {result_shape(parsed)}")
        raise RuntimeError(f"模型结果缺少必要字段：{', '.join(missing)}")
    return parsed


def first_http_url(value):
    match = re.search(r"https?://[^\s<>\"']+", str(value or ""))
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?，。；：！？、）】》")


def is_xhs_page_url(value):
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in XHS_PAGE_HOSTS


def is_xhs_image_url(value):
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and (host == "xhscdn.com" or host.endswith(XHS_IMAGE_HOST_SUFFIX))


class RestrictedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed):
        super().__init__()
        self.allowed = allowed

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        if not self.allowed(new_url):
            raise ValueError("链接跳转到了不受支持的站点")
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def bounded_fetch(url, allowed, max_bytes, accept, user_agent=None):
    if not allowed(url):
        raise ValueError("只支持小红书公开分享链接")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent or XHS_USER_AGENT, "Accept": accept},
    )
    opener = urllib.request.build_opener(RestrictedRedirectHandler(allowed))
    with opener.open(request, timeout=25) as response:
        final_url = response.geturl()
        if not allowed(final_url):
            raise ValueError("链接跳转到了不受支持的站点")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise ValueError("小红书内容过大，请改用截图导入")
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("小红书内容过大，请改用截图导入")
        return payload, response.headers.get_content_type(), final_url


class XhsHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title_parts = []
        self.scripts = []
        self._in_title = False
        self._script_parts = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "script":
            self._script_parts = []
        if tag == "meta":
            key = values.get("property") or values.get("name")
            content = values.get("content")
            if key and content:
                self.meta[key.lower()] = content

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._script_parts is not None:
            self.scripts.append("".join(self._script_parts))
            self._script_parts = None

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._script_parts is not None:
            self._script_parts.append(data)


def balanced_object(source, offset):
    start = source.find("{", offset)
    if start < 0:
        return None
    depth = 0
    quote = None
    escaped = False
    for index in range(start, len(source)):
        character = source[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return None


def replace_js_undefined(source):
    output = []
    index = 0
    quote = None
    escaped = False
    while index < len(source):
        character = source[index]
        if quote:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {'"', "'"}:
            quote = character
            output.append(character)
            index += 1
            continue
        if source.startswith("undefined", index):
            output.append("null")
            index += len("undefined")
            continue
        output.append(character)
        index += 1
    return "".join(output)


def unique_append(values, value, limit=100):
    cleaned = html.unescape(str(value or "")).strip()
    if cleaned and cleaned not in values and len(values) < limit:
        values.append(cleaned)


def collect_state_content(value, texts, preferred_images, other_images, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).lower()
            child_path = path + (lower,)
            if isinstance(child, str) and lower in {"title", "desc", "description", "content", "notedesc"}:
                if 2 <= len(child.strip()) <= 12000:
                    unique_append(texts, child, 30)
            collect_state_content(child, texts, preferred_images, other_images, child_path)
        return
    if isinstance(value, list):
        for child in value:
            collect_state_content(child, texts, preferred_images, other_images, path)
        return
    if not isinstance(value, str) or not is_xhs_image_url(value):
        return
    image_context = any(key in {"imagelist", "image_list", "images", "imageinfo", "noteimages"} for key in path)
    unique_append(preferred_images if image_context else other_images, value)


def first_image_url(value):
    if isinstance(value, str):
        return value if is_xhs_image_url(value) else None
    if isinstance(value, list):
        for child in value:
            found = first_image_url(child)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    for key in ("urlPre", "url_pre", "previewUrl", "preview_url", "urlDefault", "url_default", "url"):
        found = first_image_url(value.get(key))
        if found:
            return found
    for key in ("infoList", "info_list", "imageInfo", "image_info"):
        found = first_image_url(value.get(key))
        if found:
            return found
    return None


def note_image_urls(note):
    if not isinstance(note, dict):
        return []
    image_list = None
    for key in ("imageList", "image_list", "images", "noteImages", "note_images"):
        if isinstance(note.get(key), list):
            image_list = note[key]
            break
    if image_list is None:
        return []
    images = []
    for image in image_list:
        unique_append(images, first_image_url(image))
    return images


def apply_explicit_guide_ratings(result):
    for item in result.get("items", []):
        explicit = len(re.findall(r"[⭐🌟★]", str(item.get("nameOriginal") or "")))
        try:
            rating = float(item.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0
        item["rating"] = min(5, explicit) if explicit else max(0, min(5, rating))
    return result


def guide_item_aliases(item):
    aliases = []
    for value in (item.get("nameZh"), item.get("nameOriginal")):
        text = str(value or "").strip()
        for candidate in [text, re.sub(r"[（(].*?[）)]", "", text), *re.findall(r"[\u3400-\u9fff]{2,}", text)]:
            cleaned = candidate.strip()
            if len(cleaned) >= 2 and cleaned not in aliases:
                aliases.append(cleaned)
    return sorted(aliases, key=len, reverse=True)


def apply_verbatim_source_passages(result, source_text):
    """Replace model snippets with exact, complete text sections when the source is textual."""
    text = str(source_text or "")
    items = result.get("items", []) if isinstance(result, dict) else []
    if not text or not isinstance(items, list):
        return result

    located = []
    for item in items:
        if not isinstance(item, dict):
            continue
        hits = [(text.find(alias), alias) for alias in guide_item_aliases(item) if text.find(alias) >= 0]
        if hits:
            position, alias = min(hits, key=lambda hit: hit[0])
            located.append((position, alias, item))
    located.sort(key=lambda entry: entry[0])

    for index, (position, alias, item) in enumerate(located):
        start = text.rfind("\n", 0, position) + 1
        if index + 1 < len(located):
            next_position = located[index + 1][0]
            end = text.rfind("\n", start, next_position)
            if end < start:
                end = next_position
        else:
            end = len(text)
        lines = text[start:end].splitlines()
        kept = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if kept:
                    break
                continue
            if kept and re.match(r"^[^\w\u3400-\u9fff]", stripped):
                break
            kept.append(stripped)
        passage = "\n".join(kept).strip()
        if alias in passage and passage:
            item["sourceQuote"] = passage[:1200]
    return result


def note_from_state(state, note_id=None):
    mobile_note = (
        state.get("noteData", {}).get("data", {}).get("noteData")
        if isinstance(state, dict)
        else None
    )
    if isinstance(mobile_note, dict) and mobile_note:
        mobile_note_id = str(mobile_note.get("noteId") or "")
        if not note_id or not mobile_note_id or mobile_note_id == note_id:
            return mobile_note

    note_root = state.get("note", {}) if isinstance(state, dict) else {}
    detail_map = note_root.get("noteDetailMap") or note_root.get("note_detail_map")
    if not isinstance(detail_map, dict) or not detail_map:
        return None
    entry = detail_map.get(note_id) if note_id else None
    if not isinstance(entry, dict):
        entry = next((value for value in detail_map.values() if isinstance(value, dict)), None)
    if not entry:
        return None
    note = entry.get("note") if isinstance(entry.get("note"), dict) else entry
    return note if isinstance(note, dict) else None


def parse_xhs_html(payload, note_id=None):
    parser = XhsHtmlParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    texts = []
    images = []
    title = parser.meta.get("og:title") or "".join(parser.title_parts).strip()
    description = parser.meta.get("og:description") or parser.meta.get("description") or ""
    unique_append(texts, title, 30)
    unique_append(texts, description, 30)
    for key in ("og:image", "twitter:image"):
        image_url = parser.meta.get(key)
        if image_url and is_xhs_image_url(image_url):
            unique_append(images, image_url)

    preferred_images = []
    other_images = []
    found_note = False
    for script in parser.scripts:
        marker = script.find("__INITIAL_STATE__")
        if marker < 0:
            continue
        candidate = balanced_object(script, marker)
        if not candidate:
            continue
        try:
            state = json.loads(replace_js_undefined(candidate))
        except json.JSONDecodeError:
            continue
        note = note_from_state(state, note_id)
        if note:
            found_note = True
            title = str(note.get("title") or title).strip()
            texts = []
            images = []
            preferred_images = note_image_urls(note)
            fallback_images = []
            collect_state_content(note, texts, fallback_images, other_images)
            if not preferred_images:
                preferred_images = fallback_images
        else:
            collect_state_content(state, texts, preferred_images, other_images)
        break
    for image_url in preferred_images or other_images:
        unique_append(images, image_url)
    return {"title": title, "text": "\n".join(texts)[:20000], "images": images, "found_note": found_note}


def image_data_url(url):
    payload, content_type, _ = bounded_fetch(url, is_xhs_image_url, XHS_MAX_IMAGE_BYTES, "image/avif,image/webp,image/*")
    if not content_type.startswith("image/"):
        raise ValueError("小红书图片地址返回了非图片内容")
    return f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}", len(payload)


def prepare_guide_source(source):
    source = str(source or "").strip()
    if len(source) < 4:
        raise ValueError("请粘贴小红书分享链接或分享文案")
    if len(source) > 30000:
        raise ValueError("分享文案过长，请只保留一篇攻略")
    # Shared text can arrive with Markdown-escaped URL punctuation (https\:// or https:\/\/).
    url = first_http_url(source.replace(r"\/", "/").replace(r"\:", ":"))
    if not url:
        return {"type": "text", "url": None, "title": "分享文案", "text": source, "images": [], "image_count": 0}
    parsed = None
    final_url = url
    errors = []
    # App 分享链接常将桌面 UA 导向登录页，但会向移动 UA 返回完整 H5 状态树。
    # 这里采用 media-parser 的双 UA 回退思路，但只保留本产品需要的单篇公开笔记读取。
    for user_agent in (XHS_USER_AGENT, XHS_MOBILE_USER_AGENT):
        try:
            payload, content_type, candidate_url = bounded_fetch(
                url,
                is_xhs_page_url,
                XHS_MAX_PAGE_BYTES,
                "text/html,application/xhtml+xml",
                user_agent=user_agent,
            )
            if content_type not in {"text/html", "application/xhtml+xml"}:
                errors.append("链接未返回笔记网页")
                continue
            candidate_path = urllib.parse.urlparse(candidate_url).path
            if "/login" in candidate_path or "website-login/error" in candidate_path:
                errors.append("访问被导向登录页")
                continue
            note_match = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]+)", candidate_path)
            candidate = parse_xhs_html(payload, note_match.group(1) if note_match else None)
            if not candidate["found_note"]:
                errors.append("网页中没有可读取的笔记数据")
                continue
            parsed = candidate
            final_url = candidate_url
            break
        except (ValueError, urllib.error.URLError, TimeoutError) as error:
            errors.append(str(error))
    if not parsed:
        detail = errors[-1] if errors else "未知错误"
        raise ValueError(f"没有读取到这篇公开笔记：{detail}")
    data_urls = []
    total_bytes = 0
    for image_url in parsed["images"]:
        if len(data_urls) >= XHS_MAX_IMAGES:
            break
        try:
            data_url, size = image_data_url(image_url)
        except Exception as error:
            print(f"Skip Xiaohongshu image: {error}")
            continue
        if total_bytes + size > XHS_MAX_TOTAL_IMAGE_BYTES:
            break
        data_urls.append(data_url)
        total_bytes += size
    if not parsed["text"] and not data_urls:
        raise ValueError("没有从这篇公开笔记读取到正文或图片，请改用截图导入")
    return {
        "type": "xiaohongshu",
        "url": final_url,
        "title": parsed["title"] or "小红书攻略",
        "text": parsed["text"] or source,
        "images": data_urls,
        "image_count": len(data_urls),
    }


def session_connection():
    SESSION_DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(SESSION_DATA_DIR / "sessions.sqlite3"), timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS session_images (
            session_id TEXT NOT NULL,
            image_key TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            image_bytes BLOB NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (session_id, image_key),
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )"""
    )
    return connection


def validate_session_id(session_id):
    if not SESSION_ID_PATTERN.fullmatch(str(session_id or "")):
        raise ValueError("点餐会话地址无效")
    return str(session_id)


def validate_image_key(image_key):
    if not SESSION_IMAGE_KEY_PATTERN.fullmatch(str(image_key or "")):
        raise ValueError("图片标识无效")
    return str(image_key)


def state_json(state):
    if not isinstance(state, dict):
        raise ValueError("点餐会话状态无效")
    cleaned = {key: value for key, value in state.items() if key != "busy"}
    encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > SESSION_MAX_STATE_BYTES:
        raise ValueError("本次点餐内容过多，请结束后开始新的点餐")
    return encoded


def cleanup_expired_sessions(connection, now=None):
    current = now or time.time()
    connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (current,))


def consume_rate_limits(limits, now=None):
    """Atomically consume all named limits or reject without consuming any."""
    current = time.time() if now is None else now
    window_start = current - RATE_LIMIT_WINDOW_SECONDS
    with RATE_LOCK:
        buckets = []
        for bucket_name, identity, limit in limits:
            events = RATE_EVENTS[(bucket_name, identity)]
            while events and events[0] <= window_start:
                events.popleft()
            buckets.append((events, limit))
        blocked = [(events, limit) for events, limit in buckets if limit <= 0 or len(events) >= limit]
        if blocked:
            oldest = [events[0] for events, limit in blocked if limit > 0 and events]
            retry_after = RATE_LIMIT_WINDOW_SECONDS if not oldest else max(
                1,
                min(RATE_LIMIT_WINDOW_SECONDS, int(min(oldest) + RATE_LIMIT_WINDOW_SECONDS - current) + 1),
            )
            return False, retry_after
        for events, _ in buckets:
            events.append(current)
    return True, 0


def model_rate_limits(client, dining_session=None):
    """Protect both the free shared quota and each visitor's daily allowance."""
    limits = [
        ("model-global", "all", MODEL_REQUESTS_GLOBAL_PER_WINDOW),
        ("model-client", client, MODEL_REQUESTS_PER_WINDOW),
    ]
    if dining_session:
        limits.append(("model-session", dining_session, MODEL_REQUESTS_PER_SESSION_WINDOW))
    return limits


def rate_limit_message(kind):
    if kind == "model" and RATE_LIMIT_WINDOW_SECONDS >= 23 * 60 * 60:
        return "今日体验次数已用完，请明天再试"
    return "请求过于频繁，请稍后再试"


def create_dining_session(state):
    now = time.time()
    session_id = uuid.uuid4().hex
    encoded = state_json(state)
    with session_connection() as connection:
        cleanup_expired_sessions(connection, now)
        active_count = connection.execute("SELECT count(*) FROM sessions WHERE expires_at > ?", (now,)).fetchone()[0]
        if active_count >= SESSION_MAX_ACTIVE:
            raise ValueError("当前点餐会话已满，请稍后再试")
        connection.execute(
            "INSERT INTO sessions (id, state_json, created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, encoded, now, now, now + SESSION_TTL_SECONDS),
        )
    return {"sessionId": session_id, "state": json.loads(encoded), "expiresAt": now + SESSION_TTL_SECONDS}


def health_status():
    try:
        with session_connection() as connection:
            connection.execute("SELECT 1").fetchone()
        if not API_KEY:
            return 503, {"status": "unavailable", "modelConfigured": False}
        return 200, {"status": "ok", "modelConfigured": True}
    except Exception as error:
        print(f"Health check failed: {error}")
        return 503, {"status": "unavailable", "modelConfigured": bool(API_KEY)}


def load_dining_session(session_id):
    session_id = validate_session_id(session_id)
    now = time.time()
    with session_connection() as connection:
        row = connection.execute(
            "SELECT state_json, updated_at, expires_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        if row[2] <= now:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return None
        return {"sessionId": session_id, "state": json.loads(row[0]), "updatedAt": row[1], "expiresAt": row[2]}


def active_session_id(value):
    try:
        session_id = validate_session_id(value)
    except ValueError:
        return None
    now = time.time()
    with session_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM sessions WHERE id = ? AND expires_at > ?",
            (session_id, now),
        ).fetchone()
    return session_id if row else None


def update_dining_session(session_id, state):
    session_id = validate_session_id(session_id)
    encoded = state_json(state)
    now = time.time()
    with session_connection() as connection:
        cursor = connection.execute(
            "UPDATE sessions SET state_json = ?, updated_at = ?, expires_at = ? WHERE id = ? AND expires_at > ?",
            (encoded, now, now + SESSION_TTL_SECONDS, session_id, now),
        )
        if not cursor.rowcount:
            return None
    return {"sessionId": session_id, "updatedAt": now, "expiresAt": now + SESSION_TTL_SECONDS}


def decode_session_image(data_url):
    if not isinstance(data_url, str) or not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("图片格式无效")
    header, encoded = data_url.split(",", 1)
    mime_type = header[5:].split(";", 1)[0].lower()
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("只支持 JPEG、PNG 或 WebP 图片")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as error:
        raise ValueError("图片数据无效") from error
    if not payload or len(payload) > SESSION_MAX_IMAGE_BYTES:
        raise ValueError("单张图片超过服务端保存上限")
    signatures = {
        "image/jpeg": payload.startswith(b"\xff\xd8"),
        "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
    }
    if not signatures[mime_type]:
        raise ValueError("图片内容与格式不一致")
    return mime_type, payload


def save_session_image(session_id, image_key, data_url):
    session_id = validate_session_id(session_id)
    image_key = validate_image_key(image_key)
    mime_type, payload = decode_session_image(data_url)
    now = time.time()
    with session_connection() as connection:
        cleanup_expired_sessions(connection, now)
        session = connection.execute(
            "SELECT 1 FROM sessions WHERE id = ? AND expires_at > ?",
            (session_id, now),
        ).fetchone()
        if not session:
            return None
        previous = connection.execute(
            "SELECT length(image_bytes) FROM session_images WHERE session_id = ? AND image_key = ?",
            (session_id, image_key),
        ).fetchone()
        used = connection.execute(
            "SELECT COALESCE(sum(length(image_bytes)), 0) FROM session_images WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        projected = used - (previous[0] if previous else 0) + len(payload)
        if projected > SESSION_MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("本次点餐保存的原图过多，请减少图片或开始新的点餐")
        stored = connection.execute(
            "SELECT COALESCE(sum(length(image_bytes)), 0) FROM session_images"
        ).fetchone()[0]
        stored_projected = stored - (previous[0] if previous else 0) + len(payload)
        if stored_projected > SESSION_MAX_STORED_IMAGE_BYTES:
            raise ValueError("服务端图片容量暂时已满，请稍后再试")
        connection.execute(
            """INSERT INTO session_images (session_id, image_key, mime_type, image_bytes, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id, image_key) DO UPDATE SET
                 mime_type = excluded.mime_type,
                 image_bytes = excluded.image_bytes,
                 created_at = excluded.created_at""",
            (session_id, image_key, mime_type, payload, now),
        )
        connection.execute(
            "UPDATE sessions SET updated_at = ?, expires_at = ? WHERE id = ?",
            (now, now + SESSION_TTL_SECONDS, session_id),
        )
    return {"imageKey": image_key, "byteSize": len(payload)}


def load_session_image(session_id, image_key):
    session_id = validate_session_id(session_id)
    image_key = validate_image_key(image_key)
    now = time.time()
    with session_connection() as connection:
        row = connection.execute(
            """SELECT image.mime_type, image.image_bytes
               FROM session_images image
               JOIN sessions session ON session.id = image.session_id
               WHERE image.session_id = ? AND image.image_key = ? AND session.expires_at > ?""",
            (session_id, image_key, now),
        ).fetchone()
        return row


def delete_dining_session(session_id):
    session_id = validate_session_id(session_id)
    with session_connection() as connection:
        cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return bool(cursor.rowcount)


def jpeg_dimensions(image):
    if not image or not image.startswith("data:image/jpeg;base64,"):
        raise ValueError("定位图片必须是 JPEG data URL")
    raw = base64.b64decode(image.split(",", 1)[1])
    if raw[:2] != b"\xff\xd8":
        raise ValueError("JPEG 图片无效")
    offset = 2
    while offset + 9 < len(raw):
        if raw[offset] != 0xFF:
            offset += 1
            continue
        marker = raw[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(raw):
            break
        segment_length = struct.unpack(">H", raw[offset:offset + 2])[0]
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height, width = struct.unpack(">HH", raw[offset + 3:offset + 7])
            return width, height
        offset += segment_length
    raise ValueError("无法读取 JPEG 尺寸")


def qwen_ocr_lines(image):
    payload = {
        "model": OCR_MODEL,
        "input": {
            "messages": [{
                "role": "user",
                "content": [{
                    "image": image,
                    "min_pixels": 3072,
                    "max_pixels": 8388608,
                    "enable_rotate": False,
                }],
            }],
        },
        "parameters": {"ocr_options": {"task": "advanced_recognition"}},
    }
    request = urllib.request.Request(
        OCR_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {OCR_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            with urllib.request.urlopen(request, timeout=OCR_READ_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            if error.code in {429, 500, 502, 503, 504} and attempt < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[attempt])
                continue
            raise
    content = result.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", [])
    for item in content:
        words = item.get("ocr_result", {}).get("words_info")
        if isinstance(words, list):
            return words
    raise RuntimeError("OCR 没有返回文字坐标")


def ocr_menu_evidence(words):
    evidence = []
    for index, item in enumerate(words or []):
        text = str(item.get("text", "")).strip() if isinstance(item, dict) else ""
        if not text:
            continue
        rect = item.get("rotate_rect") or item.get("rotateRect") or []
        evidence.append({"index": index, "text": text, "rect": rect[:5] if isinstance(rect, list) else []})
    return json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))


def ocr_menu_sections(words):
    def is_heading(text):
        letters = [character for character in text if character.isalpha()]
        return 3 <= len(letters) <= 48 and all(character == character.upper() for character in letters)

    sections = []
    current = []
    title = ""
    for item in words or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        if is_heading(text):
            if current:
                sections.append({"title": title or "未分类", "words": current})
            title = text
            current = [item]
        else:
            current.append(item)
    if current:
        sections.append({"title": title or "未分类", "words": current})
    useful = [section for section in sections if len(section["words"]) > 1]
    return useful or [{"title": "整页菜单", "words": list(words or [])}]


def merge_menu_section_results(results):
    dishes = []
    pricing_modes = []
    notes = []
    fixed_prices = []
    for section_index, result in enumerate(results):
        pricing = result.get("pricing", {}) if isinstance(result, dict) else {}
        pricing_modes.append(pricing.get("mode", "unknown"))
        if pricing.get("note"):
            notes.append(str(pricing["note"]))
        fixed_price = pricing.get("fixedPrice")
        if fixed_price:
            fixed_prices.append(fixed_price)
        for item_index, dish in enumerate(result.get("dishes", []) if isinstance(result, dict) else []):
            if not isinstance(dish, dict):
                continue
            copied = dict(dish)
            copied["id"] = f"section-{section_index + 1}-{copied.get('id') or item_index + 1}"
            dishes.append(copied)
    if pricing_modes and all(mode == "a_la_carte" for mode in pricing_modes):
        mode = "a_la_carte"
    elif fixed_prices and len(set(fixed_prices)) == 1:
        mode = "fixed_menu"
    elif any(mode == "multiple_fixed_menus" for mode in pricing_modes) or len(set(fixed_prices)) > 1:
        mode = "multiple_fixed_menus"
    else:
        mode = "unknown"
    return {
        "id": "menu-page",
        "title": "现场菜单",
        "pricing": {
            "mode": mode,
            "fixedPrice": fixed_prices[0] if mode == "fixed_menu" else 0,
            "note": "；".join(dict.fromkeys(notes)),
        },
        "dishes": dishes,
    }


def analyze_ocr_menu(prompt, words):
    combined_text = "\n".join(str(item.get("text", "")) for item in words if isinstance(item, dict))
    sections = ocr_menu_sections(words)
    should_split = (
        len(words or []) >= 40
        and len(sections) >= 2
        and not re.search(r"\b(?:MENU|FORMULE)\b", combined_text, re.IGNORECASE)
    )
    if not should_split:
        ocr_prompt = (
            f"{prompt}\n"
            "以下是菜单 OCR 逐行结果，text 是必须翻译和结构化的原文，rect 是原图像素坐标。"
            "标题不作为可点项目；单独出现的价格要根据同栏位置和阅读顺序与项目配对。"
            "box 先返回 x=0,y=0,w=1,h=1，服务端会用 OCR 坐标校准。\n"
            f"OCR：{ocr_menu_evidence(words)}"
        )
        return model_request(ocr_prompt, MENU_SCHEMA, "menu_page", max_output_tokens=16384)

    def analyze_section(section):
        section_prompt = (
            f"{prompt}\n"
            "这是同一张菜单中拆出的一个栏目，只返回本栏目内的可点项目，不要补充其他栏目。"
            "栏目标题不作为可点项目；单独出现的价格要根据同栏位置和阅读顺序与项目配对。"
            "box 先返回 x=0,y=0,w=1,h=1，服务端会用 OCR 坐标校准。\n"
            f"栏目：{section['title']}\nOCR：{ocr_menu_evidence(section['words'])}"
        )
        return model_request(section_prompt, MENU_SCHEMA, "menu_page", max_output_tokens=6144)

    worker_count = max(1, min(MENU_SECTION_CONCURRENCY, len(sections)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(analyze_section, sections))
    return merge_menu_section_results(results)


def normalized_text(value):
    return "".join(character.upper() for character in str(value or "") if character.isalnum())


def line_match_score(dish_name, ocr_text):
    target = normalized_text(dish_name)
    candidate = normalized_text(ocr_text)
    if not target or not candidate:
        return 0
    if target == candidate:
        return 1
    if candidate.startswith(target):
        return 0.98
    if target in candidate:
        return 0.92
    return difflib.SequenceMatcher(None, target, candidate).ratio()


def attach_ocr_boxes(menu, words, image_size):
    width, height = image_size
    if not width or not height:
        return menu
    for dish in menu.get("dishes", []):
        dish_name = next((line.strip() for line in str(dish.get("original", "")).splitlines() if line.strip()), "")
        ranked = sorted(
            ((line_match_score(dish_name, word.get("text")), word) for word in words),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.58:
            dish["boxSource"] = "model"
            continue
        matched_word = ranked[0][1]
        vertices = matched_word.get("location") or []
        bounds = None
        if len(vertices) >= 8:
            try:
                coordinates = [float(value) for value in vertices[:8]]
                if all(math.isfinite(value) for value in coordinates):
                    xs, ys = coordinates[::2], coordinates[1::2]
                    bounds = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
            except (TypeError, ValueError):
                pass
        if bounds is None:
            rect = matched_word.get("rotate_rect") or matched_word.get("rotateRect") or []
            if len(rect) < 4:
                dish["boxSource"] = "model"
                continue
            center_x, center_y, box_width, box_height = (float(value) for value in rect[:4])
            if len(rect) >= 5 and abs(float(rect[4])) > 45:
                box_width, box_height = box_height, box_width
            bounds = (center_x - box_width / 2, center_y - box_height / 2, box_width, box_height)
        left, top, box_width, box_height = bounds
        if box_width <= 0 or box_height <= 0:
            dish["boxSource"] = "model"
            continue
        dish["box"] = {
            "x": max(0, min(1000, left / width * 1000)),
            "y": max(0, min(1000, top / height * 1000)),
            "w": max(1, min(1000, box_width / width * 1000)),
            "h": max(1, min(1000, box_height / height * 1000)),
        }
        dish["boxSource"] = "ocr"
    return menu


MENU_NON_ITEM_HEADINGS = {
    "STARTERS", "OUR STARTERS", "SALADS", "OUR SALADS", "DISHES", "OUR DISHES",
    "TOASTS", "OUR TOASTS", "DESSERTS", "OUR DESSERTS", "WINES", "OUR WINES",
    "WHITE", "RED", "ROSE", "ROSÉ", "COCKTAILS", "OUR COCKTAILS", "BOARDS",
    "APERO BOARDS", "APÉRO BOARDS", "BOTTLE BEERS", "DRAFT BEERS", "HOT DRINKS",
    "COLD DRINKS", "TEAS", "WHISKIES", "ALCOHOLS AND LIQUEURS", "JUICES",
    "MINERAL WATERS", "CHEESES", "FROMAGES", "FORMULE", "MENU",
}


def normalized_heading(value):
    value = unicodedata.normalize("NFKD", str(value or "").upper())
    return " ".join(re.findall(r"[A-Z]+", value))


def normalize_price_options(value):
    options = []
    for option in value if isinstance(value, list) else []:
        if not isinstance(option, dict):
            continue
        try:
            price = float(option.get("price") or 0)
        except (TypeError, ValueError):
            price = 0
        label = str(option.get("label") or "").strip()
        if label and price > 0:
            options.append({"label": label, "price": price})
    return options


def canonicalize_visual_menu(menu):
    dishes = []
    seen = set()
    for index, raw_dish in enumerate(menu.get("dishes", []) if isinstance(menu, dict) else []):
        if not isinstance(raw_dish, dict):
            continue
        dish = dict(raw_dish)
        original = str(dish.get("original") or "").strip()
        if not original or normalized_heading(original) in MENU_NON_ITEM_HEADINGS:
            continue
        options = normalize_price_options(dish.get("priceOptions"))
        try:
            price = float(dish.get("price") or 0)
        except (TypeError, ValueError):
            price = 0
        if options:
            price = 0
        key = (normalized_text(original), round(price, 2), tuple((item["label"], item["price"]) for item in options))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        description = str(dish.get("descriptionOriginal") or "").strip()
        summary = str(dish.get("summary") or "").strip()
        if not description:
            summary = "菜单未注明配方或口味"
        elif not summary:
            summary = description
        dish.update({
            "id": str(dish.get("id") or f"item-{index + 1}"),
            "original": original,
            "descriptionOriginal": description,
            "nameZh": str(dish.get("nameZh") or original).strip(),
            "summary": summary,
            "decisionHint": summary.replace("\n", " ").strip(),
            "price": price,
            "priceOptions": options,
            "tags": list(dish.get("tags") or []),
            "guideMatchIds": [],
            "box": dish.get("box") if isinstance(dish.get("box"), dict) else {"x": 0, "y": 0, "w": 1, "h": 1},
        })
        dishes.append(dish)
    menu["dishes"] = dishes
    return menu


def remap_region_boxes(menu, region):
    region_x = float(region.get("x", 0))
    region_y = float(region.get("y", 0))
    region_w = float(region.get("w", 1))
    region_h = float(region.get("h", 1))
    for dish in menu.get("dishes", []):
        box = dish.get("box") if isinstance(dish.get("box"), dict) else {}
        dish["box"] = {
            "x": max(0, min(1000, (region_x + float(box.get("x", 0)) / 1000 * region_w) * 1000)),
            "y": max(0, min(1000, (region_y + float(box.get("y", 0)) / 1000 * region_h) * 1000)),
            "w": max(1, min(1000, float(box.get("w", 1)) * region_w)),
            "h": max(1, min(1000, float(box.get("h", 1)) * region_h)),
        }
        dish["boxSource"] = "vision"
    return menu


def visual_menu_regions(image, regions=None):
    clean_regions = []
    for index, region in enumerate(regions or []):
        if not isinstance(region, dict) or not region.get("image"):
            continue
        try:
            clean_regions.append({
                "image": region["image"],
                "x": max(0, min(1, float(region.get("x", 0)))),
                "y": max(0, min(1, float(region.get("y", 0)))),
                "w": max(0.01, min(1, float(region.get("w", 1)))),
                "h": max(0.01, min(1, float(region.get("h", 1)))),
                "index": index,
            })
        except (TypeError, ValueError):
            continue
    if not clean_regions:
        clean_regions = [{"image": image, "x": 0, "y": 0, "w": 1, "h": 1, "index": 0}]
    return clean_regions[:4]


def visual_region_prompt(prompt, region):
    return (
        f"{prompt}\n"
        f"这是原菜单的第 {region['index'] + 1} 个视觉栏目裁图。"
        "只返回裁图内完整可见的可点项目，从上到下保持顺序。"
        "box 使用当前裁图的0到1000相对坐标，服务端会映射回原图。"
    )


def analyze_visual_region(prompt, region):
    result = model_request(visual_region_prompt(prompt, region), MENU_SCHEMA, "menu_page", region["image"], 8192)
    return remap_region_boxes(result, region)


def analyze_visual_menu(prompt, image, regions=None):
    clean_regions = visual_menu_regions(image, regions)

    def analyze_region(region):
        return analyze_visual_region(prompt, region)

    worker_count = max(1, min(MENU_SECTION_CONCURRENCY, len(clean_regions)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(analyze_region, clean_regions))
    return canonicalize_visual_menu(merge_menu_section_results(results))


def decision_hint_prompt(dishes):
    compact = [{
        "id": dish.get("id"),
        "original": dish.get("original"),
        "nameZh": dish.get("nameZh"),
        "descriptionOriginal": dish.get("descriptionOriginal", ""),
        "menuDescriptionZh": dish.get("summary") if dish.get("descriptionOriginal") else "",
        "tags": dish.get("tags", []),
    } for dish in dishes]
    return (
        "严格按JSON Schema返回，每个输入 id 恰好返回一条 decisionHint，id 原样返回。"
        "给中国用户一句能帮助点餐的理解：能准确类比常见食物时先说像什么，再说核心味型或口感；"
        "必要时加一个最关键的踩雷提醒。每条尽量不超过30个中文字，不换行。"
        "菜单描述是这家店明确印出的事实；常见做法和味型只是一般餐饮知识，不能写成这家店确定的配方。"
        "不要把原文没有写的主食材、配料、星级或博主态度说成事实。"
        "类比只比较形态、味型或口感，不得顺带增加食材：焗蛋不说成有米饭，"
        "未注明肉种的汉堡不说成牛肉饼，未注明肝的肉冻不说成肝酱或含内脏。"
        "生食、内脏、膻味、少见食材等提醒只能基于菜名或菜单描述明确支持的信息；不确定就省略。"
        "蜗牛不是内脏；烟熏或腌制不等于生鱼片。找不到准确类比时直接说味道和口感。"
        "不要重复菜名译文，不要使用‘精致美味、值得尝试、异域风情’等空话。"
        "示例：‘像芝士洋葱浓汤，咸甜鲜。’‘像蒜香炒螺肉，弹韧；食材少见。’"
        "‘生牛肉碎，口感柔软；不接受生食慎点。’"
        f"菜单项目：{json.dumps(compact, ensure_ascii=False)}"
    )


def enrich_menu_dishes(dishes):
    if not dishes:
        return []
    result = model_request(decision_hint_prompt(dishes), ENRICH_SCHEMA, "dish_decision_hints", max_output_tokens=4096)
    hints = {
        str(item.get("id")): str(item.get("decisionHint") or "").replace("\n", " ").strip()
        for item in result.get("items", []) if isinstance(item, dict)
    }
    for dish in dishes:
        dish["aiDecisionHint"] = hints.get(str(dish.get("id")), "")
    return dishes


def streaming_menu_prompt():
    return (
        menu_analysis_prompt([])
        + "额外的 aiDecisionHint 是面向中国用户的一句话点餐理解：能准确类比常见食物时先说像什么，"
        "再说核心味型或口感，必要时加一个最关键的踩雷提醒，尽量不超过30个中文字。"
        "summary 和 decisionHint 仍只翻译菜单事实，aiDecisionHint 才可以使用稳妥的一般餐饮知识。"
        "不要把未写出的主食材或配料当作这家店的事实。焗蛋不能说有米饭；未注明肉种的汉堡不能说牛肉饼；"
        "未注明肝的肉冻不能说肝酱或内脏。生食、内脏、膻味等提醒必须有菜名或菜单描述支持，"
        "不确定就省略。蜗牛不是内脏；烟熏或腌制不等于生鱼片。不要空泛推荐。"
        "menuRecommendationLabel 仅当菜单原图在该菜旁边，或在该菜明确所属的推荐栏目中，"
        "印有本店特色、主厨推荐、店长推荐、招牌菜等推荐字样时填写相应中文短标签，否则填空字符串。"
        "menuRecommendationEvidence 必须逐字抄下原图对应的推荐字样，没有则填空字符串。"
        "OUR DISHES、OUR STARTERS、OUR DESSERTS 等普通分类标题不是推荐。"
    )


MENU_RECOMMENDATION_LABELS = {"本店特色", "主厨推荐", "厨师推荐", "店长推荐", "招牌菜", "今日推荐", "菜单推荐"}
MENU_RECOMMENDATION_TERMS = re.compile(
    r"chef|special|signature|recommend|recommand|favorite|favourite|maison|sugg[eé]r|sp[eé]cial|coup de c[oœ]ur|招牌|推荐|特色",
    re.IGNORECASE,
)


def verify_menu_recommendation(dish, words):
    label = str(dish.get("menuRecommendationLabel") or "").strip()
    evidence = str(dish.get("menuRecommendationEvidence") or "").strip()
    if label not in MENU_RECOMMENDATION_LABELS or not evidence or not MENU_RECOMMENDATION_TERMS.search(evidence):
        dish["menuRecommendationLabel"] = ""
        dish["menuRecommendationEvidence"] = ""
        return dish
    if words and not any(
        line_match_score(evidence, word.get("text", "")) >= 0.6
        for word in words if isinstance(word, dict)
    ):
        dish["menuRecommendationLabel"] = ""
        dish["menuRecommendationEvidence"] = ""
    return dish


class StreamedDishParser:
    def __init__(self):
        self.text = ""
        self.position = None
        self.object_start = None
        self.depth = 0
        self.in_string = False
        self.escaped = False
        self.metadata = {}

    def feed(self, delta):
        self.text += delta
        if self.position is None:
            match = re.search(r'"dishes"\s*:\s*\[', self.text)
            if not match:
                return []
            self.position = match.end()
            try:
                self.metadata = json.loads(self.text[:match.start()].rstrip().rstrip(",") + "}")
            except json.JSONDecodeError:
                self.metadata = {}
        completed = []
        while self.position < len(self.text):
            character = self.text[self.position]
            if self.object_start is None:
                if character == "{":
                    self.object_start = self.position
                    self.depth = 1
                elif character == "]":
                    self.position = len(self.text)
                    break
            elif self.in_string:
                if self.escaped:
                    self.escaped = False
                elif character == "\\":
                    self.escaped = True
                elif character == '"':
                    self.in_string = False
            elif character == '"':
                self.in_string = True
            elif character == "{":
                self.depth += 1
            elif character == "}":
                self.depth -= 1
                if self.depth == 0:
                    completed.append(json.loads(self.text[self.object_start:self.position + 1]))
                    self.object_start = None
            self.position += 1
        return completed


def stream_openai_compatible_region(prompt, region, on_dish):
    request = openai_compatible_request(visual_region_prompt(prompt, region), STREAM_MENU_SCHEMA,
                                        "menu_page_stream", region["image"], 12288, stream=True)
    parser = StreamedDishParser()
    emitted = 0
    with urllib.request.urlopen(request, timeout=MODEL_READ_TIMEOUT_SECONDS) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            packet = json.loads(data)
            choices = packet.get("choices") or []
            delta = choices[0].get("delta", {}).get("content") if choices else None
            if not isinstance(delta, str) or not delta:
                continue
            for dish in parser.feed(delta):
                on_dish(dish, parser.metadata)
                emitted += 1
    try:
        result = json.loads(parser.text)
    except json.JSONDecodeError as error:
        raise RuntimeError("菜单模型流式结果不完整") from error
    if not isinstance(result, dict) or not isinstance(result.get("dishes"), list):
        raise RuntimeError("菜单模型流式结果缺少菜品")
    for dish in result["dishes"][emitted:]:
        on_dish(dish, result)
    return result


def stream_qwen_region(prompt, region, on_dish):
    """Backward-compatible alias for older integrations."""
    return stream_openai_compatible_region(prompt, region, on_dish)


def stream_visual_menu(prompt, image, regions, emit, guide_items=None):
    clean_regions = visual_menu_regions(image, regions)
    guide_items = [item for item in (guide_items or []) if isinstance(item, dict) and item.get("id")]
    emit({"type": "start", "regions": len(clean_regions)})

    def read_ocr():
        if not OCR_ENABLED:
            return None
        try:
            return qwen_ocr_lines(image)
        except (ValueError, RuntimeError, urllib.error.URLError, TimeoutError) as error:
            print(f"Visual menu OCR validation skipped: {error}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ocr_executor:
        ocr_future = ocr_executor.submit(read_ocr)
        channels = [queue.Queue() for _ in clean_regions]

        def analyze_region(index, region):
            channel = channels[index]
            emitted = 0

            def on_dish(raw_dish, metadata):
                nonlocal emitted
                menu = canonicalize_visual_menu(remap_region_boxes({"dishes": [raw_dish]}, region))
                words = ocr_future.result()
                if words and menu["dishes"]:
                    menu = validate_visual_menu_with_ocr(menu, words, jpeg_dimensions(image))
                for dish in menu["dishes"]:
                    verify_menu_recommendation(dish, words)
                    assign_guide_matches({"dishes": [dish]}, guide_items)
                    channel.put({"type": "dish", "dish": dish, "ordinal": emitted,
                                 "title": metadata.get("title", "现场菜单"),
                                 "pricing": metadata.get("pricing", {})})
                    emitted += 1

            try:
                if PROVIDER == "openai_compatible" and MODEL_STREAM_ENABLED:
                    try:
                        result = stream_openai_compatible_region(streaming_menu_prompt(), region, on_dish)
                    except Exception as error:
                        if emitted:
                            raise
                        print(f"Menu token stream unavailable, using complete response: {error}")
                        result = model_request(visual_region_prompt(prompt, region), MENU_SCHEMA,
                                               "menu_page", region["image"], 8192)
                        enrich_menu_dishes(result.get("dishes", []))
                        for raw_dish in result.get("dishes", []):
                            on_dish(raw_dish, result)
                else:
                    result = model_request(visual_region_prompt(prompt, region), MENU_SCHEMA,
                                           "menu_page", region["image"], 8192)
                    enrich_menu_dishes(result.get("dishes", []))
                    for raw_dish in result.get("dishes", []):
                        on_dish(raw_dish, result)
                channel.put({"type": "region-done", "title": result.get("title", "现场菜单"),
                             "pricing": result.get("pricing", {})})
            except Exception as error:
                channel.put({"type": "region-error", "message": str(error)})

        worker_count = max(1, min(MENU_SECTION_CONCURRENCY, len(clean_regions)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(analyze_region, index, region) for index, region in enumerate(clean_regions)]
            results = []
            seen = set()
            failures = 0
            for index, channel in enumerate(channels):
                while True:
                    event = channel.get()
                    if event["type"] == "dish":
                        dish = event["dish"]
                        key = (normalized_text(dish["original"]), round(float(dish.get("price") or 0), 2),
                               tuple((option["label"], option["price"]) for option in dish.get("priceOptions", [])))
                        if key in seen:
                            continue
                        seen.add(key)
                        dish["id"] = f"section-{index + 1}-{dish['id']}"
                        emit({"type": "dish", "index": index, "ordinal": event["ordinal"],
                              "title": event["title"], "pricing": event["pricing"], "dish": dish})
                    elif event["type"] == "region-error":
                        failures += 1
                        emit({"type": "region-error", "index": index, "message": event["message"]})
                        break
                    else:
                        results.append({"pricing": event["pricing"], "dishes": []})
                        break
            for future in futures:
                future.result()
    if not results:
        emit({"type": "error", "message": "这页菜单没有识别成功，请重试"})
        return
    pricing = merge_menu_section_results(results)["pricing"]
    emit({"type": "done", "pricing": pricing, "failures": failures})


def ocr_numeric_prices(text):
    normalized = str(text or "").replace("，", ",").replace("€", " ")
    prices = []
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:[,.]\d{1,2})?)(?!\d)", normalized):
        try:
            value = float(match.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0.5 <= value <= 500:
            prices.append(value)
    return prices


def validate_visual_menu_with_ocr(menu, words, image_size):
    menu = attach_ocr_boxes(menu, words, image_size)
    width, height = image_size
    for dish in menu.get("dishes", []):
        name = dish.get("original", "")
        ranked = sorted(
            ((line_match_score(name, word.get("text", "")), word) for word in words if isinstance(word, dict)),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < 0.7:
            dish["ocrVerified"] = False
            continue
        dish["ocrVerified"] = True
        rect = ranked[0][1].get("rotate_rect", [])
        if len(rect) < 4 or dish.get("priceOptions"):
            continue
        center_x, center_y = float(rect[0]), float(rect[1])
        nearby = []
        for word in words:
            if not isinstance(word, dict):
                continue
            other = word.get("rotate_rect", [])
            if len(other) < 4:
                continue
            other_x, other_y = float(other[0]), float(other[1])
            if abs(other_y - center_y) <= max(32, height * 0.025) and abs(other_x - center_x) <= max(260, width * 0.25):
                nearby.extend(ocr_numeric_prices(word.get("text")))
        distinct = sorted({round(value, 2) for value in nearby})
        model_price = round(float(dish.get("price") or 0), 2)
        if len(distinct) == 1 and model_price > 0 and model_price not in distinct:
            dish["price"] = distinct[0]
            dish["priceCorrectedByOcr"] = True
    return canonicalize_visual_menu(menu)


def fallback_chat(message, state):
    dishes = state.get("dishes", [])
    referenced = next((dish for dish in dishes if dish.get("id") == state.get("referencedDishId")), None)
    if referenced and message.strip() == "介绍一下这道菜":
        detail = referenced.get("aiDecisionHint") or referenced.get("summary") or "菜单暂未提供更多介绍，可以继续问我它的食材和味道。"
        return {"message": f"{referenced.get('nameZh') or referenced.get('original')}：{detail}", "dishIds": [referenced["id"]], "actions": []}
    selections = state.get("selections", {})
    selected = [dish for dish in dishes if selections.get(dish.get("id"))]
    if any(word in message for word in ["生", "熟", "内脏"]):
        ids = [dish["id"] for dish in dishes if dish.get("id") in {"duck-confit", "beef-bourguignon", "steak-tartare"}]
        return {"message": "这页的牛肉塔塔是生牛肉。油封鸭腿和红酒炖牛肉都是全熟；如果想避开生食，可以从这两道里比较。", "dishIds": ids, "actions": []}
    if any(word in message for word in ["腻", "搭配", "太多", "组合", "还缺"]):
        names = "、".join(dish["nameZh"] for dish in selected)
        message_text = f"你现在选了 {names}。整体偏浓郁，可以补一道酸甜或清爽的菜。" if selected else "可以先选一道主菜，再根据口味补前菜或甜点。"
        ids = [dish["id"] for dish in dishes if dish.get("id") in {"oeuf-mayo", "tarte-tatin"}]
        return {"message": message_text, "dishIds": ids, "actions": []}
    matched = [dish for dish in dishes if dish.get("guideMatchIds")]
    if any(word in message for word in ["攻略", "推荐", "找到"]):
        if matched:
            names = "、".join(dish["nameZh"] for dish in matched)
            return {"message": f"目前找到了 {len(matched)} 道攻略提到的菜：{names}。它们只是线索，我没有替你加入点菜单。", "dishIds": [dish["id"] for dish in matched], "actions": []}
        return {"message": "当前已扫描页面还没有找到攻略菜，可以继续扫描后面的菜单页。", "dishIds": [], "actions": []}
    return {"message": "我会只基于已经扫描的菜单回答。你可以问某个项目是什么、比较两个项目，或让我检查当前点单组合。", "dishIds": [dish["id"] for dish in dishes[:3]], "actions": []}


class Handler(SimpleHTTPRequestHandler):
    server_version = "BonjourMenu/0.1"

    def end_headers(self):
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; script-src 'self'; style-src 'self' https://cdn.jsdelivr.net; font-src 'self' https://cdn.jsdelivr.net data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0].lstrip("/") or "index.html"
        candidate = (ROOT / clean).resolve()
        if ROOT.resolve() not in candidate.parents and candidate != ROOT.resolve():
            return str(ROOT / "index.html")
        return str(candidate)

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, str(value))
        self.end_headers()
        self.wfile.write(body)

    def client_identity(self):
        forwarded = self.headers.get("X-Forwarded-For", "")
        candidate = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return str(self.client_address[0])

    def allow_limited_request(self, kind):
        client = self.client_identity()
        if kind == "model":
            dining_session = active_session_id(self.headers.get("X-Dining-Session", ""))
            limits = model_rate_limits(client, dining_session)
        else:
            limits = [("session-write", client, SESSION_WRITES_PER_WINDOW)]
        allowed, retry_after = consume_rate_limits(limits)
        if allowed:
            return True
        self.send_json(
            429,
            {"error": rate_limit_message(kind)},
            {"Retry-After": retry_after},
        )
        return False

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 18 * 1024 * 1024:
            raise ValueError("上传内容超过 18MB")
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def api_path_parts(self):
        path = urllib.parse.urlparse(self.path).path
        return [urllib.parse.unquote(part) for part in path.strip("/").split("/") if part]

    def send_api_error(self, error):
        print(error)
        self.send_json(400 if isinstance(error, ValueError) else 500, {"error": str(error)})

    def do_GET(self):
        request_path = urllib.parse.urlparse(self.path).path
        if request_path == "/api/fx/eur-cny":
            try:
                self.send_json(200, eur_cny_reference_rate())
            except ValueError as error:
                self.send_json(503, {"error": str(error)})
            return
        if request_path == "/healthz":
            status, payload = health_status()
            self.send_json(status, payload)
            return
        if request_path == "/api/status":
            self.send_json(200, {
                "liveModel": bool(API_KEY),
                "provider": PROVIDER if API_KEY else None,
                "model": MODEL if API_KEY else None,
                "streamingEnabled": bool(API_KEY and MODEL_STREAM_ENABLED),
                "ocrEnabled": OCR_ENABLED,
            })
            return
        parts = self.api_path_parts()
        if len(parts) == 3 and parts[:2] == ["api", "sessions"]:
            try:
                result = load_dining_session(parts[2])
                if not result:
                    self.send_json(404, {"error": "本次点餐不存在或已经过期"})
                else:
                    self.send_json(200, result)
            except Exception as error:
                self.send_api_error(error)
            return
        if len(parts) == 5 and parts[:2] == ["api", "sessions"] and parts[3] == "images":
            try:
                result = load_session_image(parts[2], parts[4])
                if not result:
                    self.send_json(404, {"error": "原图不存在或已经过期"})
                    return
                mime_type, payload = result
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self.wfile.write(payload)
            except Exception as error:
                self.send_api_error(error)
            return
        path = pathlib.Path(self.translate_path(self.path))
        if not path.exists() or path.is_dir():
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        try:
            request_path = urllib.parse.urlparse(self.path).path
            if request_path in MODEL_API_PATHS:
                if not self.allow_limited_request("model"):
                    return
            elif request_path == "/api/sessions" or re.fullmatch(r"/api/sessions/[^/]+/images/[^/]+", request_path):
                if not self.allow_limited_request("session"):
                    return
            body = self.read_json()
            parts = self.api_path_parts()
            if parts == ["api", "sessions"]:
                self.send_json(201, create_dining_session(body.get("state", {})))
                return
            if len(parts) == 5 and parts[:2] == ["api", "sessions"] and parts[3] == "images":
                result = save_session_image(parts[2], parts[4], body.get("dataUrl"))
                if not result:
                    self.send_json(404, {"error": "本次点餐不存在或已经过期"})
                else:
                    self.send_json(201, result)
                return
            if self.path == "/api/match-guide":
                dishes = body.get("dishes", [])
                guide_items = body.get("guideItems", [])
                if not isinstance(dishes, list) or not isinstance(guide_items, list):
                    raise ValueError("攻略匹配数据无效")
                matches = model_guide_matches(dishes, guide_items)
                self.send_json(200, {"items": [
                    {"id": dish.get("id"), "guideMatchIds": matches.get(dish.get("id"), [])}
                    for dish in dishes if isinstance(dish, dict) and dish.get("id")
                ]})
                return
            if self.path == "/api/analyze-guide-source":
                if not API_KEY:
                    self.send_json(503, {"error": "尚未配置模型 API Key，无法解析真实攻略"})
                    return
                guide_source = prepare_guide_source(body.get("source"))
                prompt = (
                    "严格按JSON Schema返回一个对象，最外层禁止数组。分析用户主动提供的一篇餐厅攻略。"
                    "只提取正文或图片中明确提到的餐厅和可点单项目，包括食物与饮品，不补充来源以外的信息。"
                    "区分推荐、普通提及和提醒；图片内文字也需要读取。"
                    "sourceQuote 必须逐字摘录来源中与这个项目有关的完整原文段落，从项目名称开始，保留后续全部评价、标点、表情和换行，禁止改写或概括；"
                    "只要来源存在评价，绝不能只返回项目名称或星级；如果确实只有名称，才返回包含该名称的原句。"
                    "rating 只记录来源明确写出的 1至5 星，没写星级时返回 0，禁止根据文字情绪推测星级。"
                    "sentiment 必须结合作者完整语义判断：明确喜欢、推荐或4至5星为recommended；明确不推荐、避雷、负面评价或1至2星为caution；纯描述或态度不明确为mentioned。"
                    "note 用一句中文概括作者态度，不要冒充原话。"
                    "同一个项目在正文和图片中重复出现时只保留一次。id 使用简短英文短横线格式。\n"
                    f"攻略标题：{guide_source['title']}\n攻略文字：{guide_source['text']}"
                )
                result = model_request(
                    prompt,
                    GUIDE_SCHEMA,
                    "guide_candidates",
                    guide_source["images"],
                    8192,
                )
                result = apply_explicit_guide_ratings(result)
                result = apply_verbatim_source_passages(result, guide_source["text"])
                result["sourceType"] = guide_source["type"]
                result["sourceUrl"] = guide_source["url"]
                result["sourceTitle"] = guide_source["title"]
                result["sourceImageCount"] = guide_source["image_count"]
                self.send_json(200, result)
                return
            if self.path == "/api/analyze-guide":
                if not API_KEY:
                    self.send_json(503, {"error": "尚未配置模型 API Key，无法解析真实攻略截图"})
                    return
                result = model_request(
                    "严格按JSON Schema返回一个对象，最外层禁止数组。分析这张用户主动上传的中文餐厅攻略截图。"
                    "只提取画面明确提到的餐厅和可点单项目，包括食物与饮品，不补充画面外信息。区分推荐、普通提及和提醒。"
                    "sourceQuote 必须逐字摘录截图中与这个项目有关的完整原文段落，从项目名称开始，保留后续全部评价、标点和表情，禁止改写或概括；只要有评价就不能只返回项目名称或星级。"
                    "rating 只记录截图明确写出的 1至5 星，没写星级时返回 0。"
                    "sentiment 必须结合完整语义判断为recommended、caution或mentioned。"
                    "note 用一句中文概括作者态度，不要冒充原话。id 使用简短英文短横线格式。",
                    GUIDE_SCHEMA, "guide_candidates", body.get("image"),
                )
                result = apply_explicit_guide_ratings(result)
                self.send_json(200, result)
                return
            if self.path == "/api/analyze-menu":
                if not API_KEY:
                    self.send_json(503, {"error": "尚未配置模型 API Key，无法解析真实菜单"})
                    return
                prompt = menu_analysis_prompt(body.get("guideItems", []))
                image = body.get("image")
                if OCR_ENABLED:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                        vision_future = executor.submit(analyze_visual_menu, prompt, image, body.get("regions"))
                        ocr_future = executor.submit(qwen_ocr_lines, image)
                        result = vision_future.result()
                        try:
                            ocr_words = ocr_future.result()
                            result = validate_visual_menu_with_ocr(result, ocr_words, jpeg_dimensions(image))
                        except (ValueError, RuntimeError, urllib.error.URLError, TimeoutError) as error:
                            print(f"Visual menu OCR validation skipped: {error}")
                else:
                    result = analyze_visual_menu(prompt, image, body.get("regions"))
                result = validate_guide_matches(result, body.get("guideItems", []))
                self.send_json(200, result)
                return
            if self.path == "/api/analyze-menu-stream":
                if not API_KEY:
                    self.send_json(503, {"error": "尚未配置模型 API Key，无法解析真实菜单"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                self.close_connection = True

                def emit(event):
                    self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()

                try:
                    stream_visual_menu(menu_analysis_prompt([]), body.get("image"), body.get("regions"), emit,
                                       body.get("guideItems"))
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as error:
                    print(f"Streaming menu failed: {error}")
                    try:
                        emit({"type": "error", "message": str(error)})
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                return
            if self.path == "/api/locate-menu":
                if not OCR_ENABLED:
                    self.send_json(503, {"error": "当前模型配置不支持 OCR 坐标校准"})
                    return
                image = body.get("image")
                menu = {"dishes": body.get("dishes", [])}
                result = attach_ocr_boxes(menu, qwen_ocr_lines(image), jpeg_dimensions(image))
                self.send_json(200, result)
                return
            if self.path == "/api/enrich-dishes":
                if not API_KEY:
                    self.send_json(503, {"error": "尚未配置模型 API Key"})
                    return
                dishes = body.get("dishes", [])
                if not isinstance(dishes, list) or any(not isinstance(dish, dict) for dish in dishes):
                    raise ValueError("菜品数据无效")
                enrich_menu_dishes(dishes)
                self.send_json(200, {"items": [
                    {"id": dish.get("id"), "decisionHint": dish.get("aiDecisionHint", "")}
                    for dish in dishes
                ]})
                return
            if self.path == "/api/chat":
                if not API_KEY and self.headers.get("X-Sample-Mode") != "1":
                    self.send_json(503, {"error": "尚未配置模型 API Key，无法进行真实菜单对话"})
                    return
                message = body.get("message", "")
                state = body.get("state", {})
                if not API_KEY:
                    self.send_json(200, fallback_chat(message, state))
                    return
                history = state.get("history", [])[-10:]
                menu_state = {key: value for key, value in state.items() if key != "history"}
                referenced = next((dish for dish in state.get("dishes", []) if dish.get("id") == state.get("referencedDishId")), None)
                referenced_context = json.dumps({"id": referenced.get("id"), "nameZh": referenced.get("nameZh"), "original": referenced.get("original")} if referenced else None, ensure_ascii=False)
                prompt = (
                    "严格按JSON Schema返回一个对象，最外层禁止数组。你是餐厅点餐决策助手。只根据提供的菜单状态和对话历史回答，不替用户做决定，不把推测说成菜单事实。"
                    "guide 里的项目只是用户到店前收集的候选，不代表现场菜单一定有；只有 dishes 中真实存在且 guideMatchIds 已匹配的项目，才可以说现场找到了攻略项目。"
                    "推荐、替换或列举可点项目时，只能使用 dishes 中的项目，绝不能把未匹配的攻略候选说成当前可点。"
                    "必须结合所有已扫描菜单页理解具体项目。用户使用‘这个’、‘它’、‘那道’等指代时，优先联系最近对话中提到的菜单项目；仍不明确时再追问。"
                    "本轮若有引用菜品，‘这道菜’等指代明确指向该项目。优先围绕它回答，但仍以菜单事实为准。"
                    "回答简洁，并返回与回答相关的真实 dishIds。只有用户明确命令加入或删除某个项目时，才返回 actions；推荐、比较和筛选时 actions 必须为空。"
                    "message 使用简洁纯文本，不要使用Markdown星号、标题或表格。"
                    f"最近对话：{json.dumps(history, ensure_ascii=False)}\n"
                    f"本轮引用菜品：{referenced_context}\n用户问题：{message}\n当前菜单与选择：{json.dumps(menu_state, ensure_ascii=False)}"
                )
                self.send_json(200, model_request(prompt, CHAT_SCHEMA, "menu_chat", max_output_tokens=2048))
                return
            self.send_json(404, {"error": "Not found"})
        except ValueError as error:
            self.send_api_error(error)
        except Exception as error:
            self.send_api_error(error)

    def do_PUT(self):
        try:
            if not self.allow_limited_request("session"):
                return
            parts = self.api_path_parts()
            if len(parts) != 3 or parts[:2] != ["api", "sessions"]:
                self.send_json(404, {"error": "Not found"})
                return
            body = self.read_json()
            result = update_dining_session(parts[2], body.get("state", {}))
            if not result:
                self.send_json(404, {"error": "本次点餐不存在或已经过期"})
            else:
                self.send_json(200, result)
        except Exception as error:
            self.send_api_error(error)

    def do_DELETE(self):
        try:
            parts = self.api_path_parts()
            if len(parts) != 3 or parts[:2] != ["api", "sessions"]:
                self.send_json(404, {"error": "Not found"})
                return
            deleted = delete_dining_session(parts[2])
            self.send_json(200, {"deleted": deleted})
        except Exception as error:
            self.send_api_error(error)

    def log_message(self, format_string, *args):
        print(f"[{self.log_date_time_string()}] {format_string % args}")


if __name__ == "__main__":
    mimetypes.add_type("image/svg+xml", ".svg")
    print(f"Bonjour Menu running at http://{HOST}:{PORT}")
    print(f"Live model enabled: {PROVIDER}/{MODEL}" if API_KEY else "Model unavailable: configure an API key")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
