#!/usr/bin/env python3
"""Verify a deployed Bonjour Menu service without leaving test data behind."""

import argparse
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request


TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def request_json(base_url, path, method="GET", payload=None, timeout=30):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url + "/", path.lstrip("/")),
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def request_bytes(base_url, path, timeout=30):
    with urllib.request.urlopen(
        urllib.parse.urljoin(base_url + "/", path.lstrip("/")), timeout=timeout
    ) as response:
        return response.status, response.headers.get_content_type(), response.read()


def request_page(base_url, path="/", timeout=30):
    with urllib.request.urlopen(
        urllib.parse.urljoin(base_url + "/", path.lstrip("/")), timeout=timeout
    ) as response:
        return response.status, response.headers, response.read()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def analyze_menu(base_url, image_path):
    image_path = pathlib.Path(image_path)
    mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
    image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    status, result = request_json(
        base_url,
        "/api/analyze-menu",
        "POST",
        {"image": f"data:{mime_type};base64,{image}", "guideCandidates": []},
        timeout=180,
    )
    check(status == 200, "真实菜单识别没有返回 200")
    check(len(result.get("dishes", [])) > 0, "真实菜单识别没有返回菜品")
    return len(result["dishes"])


def run(base_url, menu_image=None):
    parsed = urllib.parse.urlparse(base_url)
    check(parsed.scheme in {"http", "https"} and parsed.netloc, "请提供完整的 http(s) URL")
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        check(parsed.scheme == "https", "公开环境必须使用 HTTPS")

    session_id = None
    try:
        status, headers, page = request_page(base_url)
        check(status == 200 and b'id="app"' in page, "产品首页不可用")
        check("default-src 'self'" in headers.get("Content-Security-Policy", ""), "缺少内容安全策略")
        check(headers.get("X-Content-Type-Options") == "nosniff", "缺少内容类型保护")

        status, health = request_json(base_url, "/healthz")
        check(status == 200 and health == {"status": "ok", "modelConfigured": True}, "健康检查未通过")

        status, model = request_json(base_url, "/api/status")
        check(status == 200 and model.get("liveModel"), "模型未启用")

        marker = "public-smoke-v1"
        status, created = request_json(
            base_url,
            "/api/sessions",
            "POST",
            {"state": {"pages": [], "selections": {}, "smokeMarker": marker}},
        )
        check(status == 201 and created.get("sessionId"), "无法创建点餐会话")
        session_id = created["sessionId"]

        image_key = "smoke-image"
        data_url = "data:image/png;base64," + base64.b64encode(TEST_PNG).decode("ascii")
        status, saved = request_json(
            base_url,
            f"/api/sessions/{session_id}/images/{image_key}",
            "POST",
            {"dataUrl": data_url},
        )
        check(status == 201 and saved.get("imageKey") == image_key, "无法保存菜单原图")

        status, restored = request_json(base_url, f"/api/sessions/{session_id}")
        check(status == 200 and restored.get("state", {}).get("smokeMarker") == marker, "会话恢复失败")

        status, mime_type, image = request_bytes(
            base_url, f"/api/sessions/{session_id}/images/{image_key}"
        )
        check(status == 200 and mime_type == "image/png" and image == TEST_PNG, "原图恢复失败")

        dish_count = analyze_menu(base_url, menu_image) if menu_image else None
        return {
            "status": "ok",
            "session": "create/restore/delete",
            "image": "save/restore",
            "dishes": dish_count,
        }
    finally:
        if session_id:
            try:
                request_json(base_url, f"/api/sessions/{session_id}", "DELETE")
            except Exception as error:
                print(f"警告：清理冒烟会话失败：{error}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="例如 https://bonjour-menu.onrender.com")
    parser.add_argument("--menu-image", help="可选：再用一张真实菜单调用模型识别")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.base_url.rstrip("/"), args.menu_image), ensure_ascii=False, indent=2))
    except (RuntimeError, OSError, urllib.error.HTTPError) as error:
        print(f"冒烟验收失败：{error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
