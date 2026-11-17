#!/usr/bin/env python3
"""Run repeatable structural acceptance checks against real menu images."""

import argparse
import base64
import json
import mimetypes
import pathlib
import time
import urllib.error
import urllib.request


GENERIC_HINT_PHRASES = (
    "精致美味", "异域风情", "爱好者的天堂", "值得尝试", "健康选择",
    "经典结尾", "自然之味", "丰富多样", "好机会", "温柔",
)


def post_json(endpoint, path, payload, timeout=180):
    request = urllib.request.Request(
        endpoint.rstrip("/") + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def image_data_url(path):
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError(f"unsupported image type: {mime_type}")
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def enrich_hints(endpoint, result):
    enriched = post_json(endpoint, "/api/enrich-dishes", {"dishes": result.get("dishes", [])})
    hints = {item.get("id"): item.get("decisionHint") for item in enriched.get("items", [])}
    for dish in result.get("dishes", []):
        if hints.get(dish.get("id")):
            dish["decisionHint"] = hints[dish["id"]]


def validate_result(result):
    errors = []
    warnings = []
    dishes = result.get("dishes")
    pricing = result.get("pricing") or {}
    if not isinstance(dishes, list) or not dishes:
        return ["no dishes extracted"], warnings
    if pricing.get("mode") not in {"a_la_carte", "fixed_menu", "multiple_fixed_menus", "unknown"}:
        errors.append("invalid pricing mode")
    fixed_price = float(pricing.get("fixedPrice") or 0)
    if pricing.get("mode") == "fixed_menu" and fixed_price <= 0:
        errors.append("fixed menu has no fixed price")
    if pricing.get("mode") == "multiple_fixed_menus" and fixed_price != 0:
        errors.append("multiple fixed menus must not invent one fixed price")

    originals = []
    priced = 0
    for index, dish in enumerate(dishes, 1):
        label = f"dish {index}"
        for field in ("original", "nameZh", "summary", "decisionHint"):
            if not str(dish.get(field) or "").strip():
                errors.append(f"{label} missing {field}")
        original = str(dish.get("original") or "").strip().casefold()
        if original:
            originals.append(original)
        price = dish.get("price")
        if not isinstance(price, (int, float)) or price < 0:
            errors.append(f"{label} has invalid price")
        elif price > 0:
            priced += 1
        if pricing.get("mode") == "fixed_menu" and fixed_price and price == fixed_price:
            errors.append(f"{label} repeats fixed menu price")
        hint = str(dish.get("decisionHint") or "")
        if len(hint) > 60:
            warnings.append(f"{label} hint is longer than 60 characters")
        if any(phrase in hint for phrase in GENERIC_HINT_PHRASES):
            errors.append(f"{label} uses generic promotional hint")
        box = dish.get("box") or {}
        values = [box.get(key) for key in ("x", "y", "w", "h")]
        if not all(isinstance(value, (int, float)) for value in values):
            errors.append(f"{label} has invalid box")
        elif not (0 <= values[0] <= 1000 and 0 <= values[1] <= 1000 and 0 < values[2] <= 1000 and 0 < values[3] <= 1000):
            errors.append(f"{label} box is outside image bounds")

    duplicates = len(originals) - len(set(originals))
    if duplicates:
        warnings.append(f"{duplicates} duplicate original names")
    if pricing.get("mode") == "a_la_carte" and priced < max(1, len(dishes) // 2):
        warnings.append("less than half of à-la-carte dishes have prices")
    return errors, warnings


def evaluate(endpoint, path, expectation=None):
    started = time.monotonic()
    result = post_json(endpoint, "/api/analyze-menu", {"image": image_data_url(path), "guideItems": []})
    enrich_hints(endpoint, result)
    errors, warnings = validate_result(result)
    expectation = expectation or {}
    dish_count = len(result.get("dishes", []))
    if dish_count < int(expectation.get("minDishes", 1)):
        errors.append(f"extracted {dish_count} dishes; expected at least {expectation['minDishes']}")
    expected_pricing = expectation.get("pricingMode")
    if expected_pricing and result.get("pricing", {}).get("mode") != expected_pricing:
        errors.append(f"pricing mode is {result.get('pricing', {}).get('mode')}; expected {expected_pricing}")
    return {
        "file": str(path),
        "passed": not errors,
        "elapsedSeconds": round(time.monotonic() - started, 2),
        "dishCount": dish_count,
        "dishNames": [dish.get("original") for dish in result.get("dishes", [])[:8]],
        "pricing": result.get("pricing"),
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", type=pathlib.Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:4173")
    parser.add_argument("--expectations", type=pathlib.Path)
    args = parser.parse_args()
    expectations = {}
    if args.expectations:
        expectations = json.loads(args.expectations.read_text(encoding="utf-8"))
    reports = []
    for path in args.images:
        try:
            report = evaluate(args.endpoint, path, expectations.get(path.name))
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
            report = {"file": str(path), "passed": False, "errors": [str(error)], "warnings": []}
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False))
    passed = sum(1 for report in reports if report["passed"])
    print(json.dumps({"summary": {"passed": passed, "total": len(reports)}}, ensure_ascii=False))
    raise SystemExit(0 if passed == len(reports) else 1)


if __name__ == "__main__":
    main()
