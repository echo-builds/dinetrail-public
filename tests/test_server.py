import json
import os
import pathlib
import tempfile
import time
import unittest
import base64
from unittest.mock import patch

os.environ["MODEL_API_TYPE"] = "openai_compatible"
os.environ["MODEL_API_KEY"] = "test-key"
os.environ["MODEL_BASE_URL"] = "https://models.example/v1"
os.environ["MODEL_NAME"] = "test-vision-model"
os.environ["MODEL_COMPAT_MODE"] = "standard"
os.environ["OCR_PROVIDER"] = "none"

import server


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        result = {
            "choices": [{
                "message": {"content": json.dumps([{
                    "message": "ok",
                    "dishIds": [],
                    "actions": [],
                }])},
            }],
        }
        return json.dumps(result).encode("utf-8")


class ModelRequestTest(unittest.TestCase):
    def test_parses_ecb_eur_cny_reference_rate(self):
        payload = b'''<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
          xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
          <Cube><Cube time="2026-11-16"><Cube currency="USD" rate="1.10"/>
          <Cube currency="CNY" rate="7.4000"/></Cube></Cube></gesmes:Envelope>'''
        self.assertEqual(server.parse_ecb_eur_cny(payload),
                         {"rate": 7.4, "date": "2026-11-16", "source": "ECB"})

    def test_sample_chat_uses_referenced_dish_for_default_question(self):
        result = server.fallback_chat("介绍一下这道菜", {
            "dishes": [
                {"id": "soup", "nameZh": "洋葱汤", "aiDecisionHint": "咸鲜，配芝士面包。"},
                {"id": "duck", "nameZh": "油封鸭腿", "aiDecisionHint": "肉嫩，油脂较多。"},
            ],
            "referencedDishId": "duck",
            "selections": {},
        })
        self.assertEqual(result, {"message": "油封鸭腿：肉嫩，油脂较多。", "dishIds": ["duck"], "actions": []})

    def test_rate_limits_are_atomic_and_recover_after_window(self):
        with server.RATE_LOCK:
            server.RATE_EVENTS.clear()
        limits = [("global", "all", 3), ("client", "203.0.113.8", 2)]

        self.assertEqual(server.consume_rate_limits(limits, now=100), (True, 0))
        self.assertEqual(server.consume_rate_limits(limits, now=101), (True, 0))
        allowed, retry_after = server.consume_rate_limits(limits, now=102)

        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)
        self.assertEqual(len(server.RATE_EVENTS[("global", "all")]), 2)
        with patch.object(server, "RATE_LIMIT_WINDOW_SECONDS", 10):
            self.assertEqual(server.consume_rate_limits(limits, now=112), (True, 0))

    def test_model_limits_always_include_client_and_optional_session(self):
        without_session = server.model_rate_limits("203.0.113.8")
        with_session = server.model_rate_limits("203.0.113.8", "a" * 32)

        self.assertIn(("model-client", "203.0.113.8", server.MODEL_REQUESTS_PER_WINDOW), without_session)
        self.assertFalse(any(item[0] == "model-session" for item in without_session))
        self.assertIn(("model-client", "203.0.113.8", server.MODEL_REQUESTS_PER_WINDOW), with_session)
        self.assertIn(("model-session", "a" * 32, server.MODEL_REQUESTS_PER_SESSION_WINDOW), with_session)

    def test_daily_model_limit_has_clear_user_message(self):
        with patch.object(server, "RATE_LIMIT_WINDOW_SECONDS", 24 * 60 * 60):
            self.assertEqual(server.rate_limit_message("model"), "今日体验次数已用完，请明天再试")
            self.assertEqual(server.rate_limit_message("session"), "请求过于频繁，请稍后再试")

    def test_active_session_capacity_is_enforced(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(server, "SESSION_DATA_DIR", pathlib.Path(directory)), \
                patch.object(server, "SESSION_MAX_ACTIVE", 1):
            server.create_dining_session({"pages": []})
            with self.assertRaisesRegex(ValueError, "会话已满"):
                server.create_dining_session({"pages": []})

    def test_active_session_id_accepts_only_live_persisted_sessions(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "SESSION_DATA_DIR", pathlib.Path(directory)):
            created = server.create_dining_session({"pages": []})

            self.assertEqual(server.active_session_id(created["sessionId"]), created["sessionId"])
            self.assertIsNone(server.active_session_id("not-a-session"))
            self.assertIsNone(server.active_session_id("0" * 32))

    def test_health_check_requires_model_configuration(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(server, "SESSION_DATA_DIR", pathlib.Path(directory)), \
                patch.object(server, "API_KEY", ""):
            status, payload = server.health_status()

        self.assertEqual(status, 503)
        self.assertEqual(payload, {"status": "unavailable", "modelConfigured": False})

    def test_health_check_accepts_writable_database_and_model(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(server, "SESSION_DATA_DIR", pathlib.Path(directory)), \
                patch.object(server, "API_KEY", "test-key"):
            status, payload = server.health_status()

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok", "modelConfigured": True})

    def test_persists_dining_session_and_image(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "SESSION_DATA_DIR", pathlib.Path(directory)):
            created = server.create_dining_session({"pages": [], "selections": {}})
            session_id = created["sessionId"]
            image = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xd9").decode("ascii")

            saved = server.save_session_image(session_id, "menu-image-1", image)
            updated = server.update_dining_session(session_id, {"pages": [{"assetKey": "menu-image-1"}], "selections": {}})
            restored = server.load_dining_session(session_id)
            restored_image = server.load_session_image(session_id, "menu-image-1")

            self.assertEqual(saved["imageKey"], "menu-image-1")
            self.assertIsNotNone(updated)
            self.assertEqual(restored["state"]["pages"][0]["assetKey"], "menu-image-1")
            self.assertEqual(restored_image, ("image/jpeg", b"\xff\xd8\xff\xd9"))

    def test_parses_xiaohongshu_initial_state(self):
        page = b'''<html><head><meta property="og:title" content="Paris food"></head><body><script>
        window.__INITIAL_STATE__={"note":{"noteDetailMap":{"abc123":{"note":{"title":"Paris food","desc":"Must order duck confit","imageList":[{"urlDefault":"https://sns-img-qc.xhscdn.com/note.jpg"}]}}}},"unused":undefined};
        </script></body></html>'''

        result = server.parse_xhs_html(page, "abc123")

        self.assertTrue(result["found_note"])
        self.assertIn("Must order duck confit", result["text"])
        self.assertEqual(result["images"], ["https://sns-img-qc.xhscdn.com/note.jpg"])

    def test_parses_xiaohongshu_mobile_initial_state(self):
        page = b'''<html><body><script>
        window.__INITIAL_STATE__={"noteData":{"data":{"noteData":{"noteId":"abc123","title":"Paris food","desc":"Must order duck confit","imageList":[{"urlDefault":"https://sns-img-qc.xhscdn.com/mobile.jpg"}]}}}};
        </script></body></html>'''

        result = server.parse_xhs_html(page, "abc123")

        self.assertTrue(result["found_note"])
        self.assertIn("Must order duck confit", result["text"])
        self.assertEqual(result["images"], ["https://sns-img-qc.xhscdn.com/mobile.jpg"])

    def test_parses_one_preferred_url_for_each_xiaohongshu_image(self):
        page = b'''<html><body><script>
        window.__INITIAL_STATE__={"note":{"noteDetailMap":{"abc123":{"note":{"title":"Paris food","desc":"Menu","user":{"avatar":"https://sns-avatar-qc.xhscdn.com/avatar/user.jpg"},"imageList":[
          {"urlDefault":"https://sns-img-qc.xhscdn.com/one-full.jpg","urlPre":"https://sns-img-qc.xhscdn.com/one-preview.jpg"},
          {"urlDefault":"https://sns-img-qc.xhscdn.com/two-full.jpg"},
          {"infoList":[{"url":"https://sns-img-qc.xhscdn.com/three-info.jpg"}]}
        ]}}}}};
        </script></body></html>'''

        result = server.parse_xhs_html(page, "abc123")

        self.assertEqual(result["images"], [
            "https://sns-img-qc.xhscdn.com/one-preview.jpg",
            "https://sns-img-qc.xhscdn.com/two-full.jpg",
            "https://sns-img-qc.xhscdn.com/three-info.jpg",
        ])

    def test_xiaohongshu_source_falls_back_to_mobile_user_agent(self):
        login = b'<html><body>login</body></html>'
        mobile = b'''<html><body><script>
        window.__INITIAL_STATE__={"noteData":{"data":{"noteData":{"noteId":"abc123","title":"Paris food","desc":"Must order duck confit","imageList":[]}}}};
        </script></body></html>'''
        responses = [
            (login, "text/html", "https://www.xiaohongshu.com/login"),
            (mobile, "text/html", "https://www.xiaohongshu.com/discovery/item/abc123"),
        ]

        with patch.object(server, "bounded_fetch", side_effect=responses) as fetch:
            result = server.prepare_guide_source("https://www.xiaohongshu.com/explore/abc123?xsec_token=token")

        self.assertEqual(result["title"], "Paris food")
        self.assertIn("Must order duck confit", result["text"])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(fetch.call_args_list[1].kwargs["user_agent"], server.XHS_MOBILE_USER_AGENT)

    def test_rejects_generic_xiaohongshu_shell(self):
        page = b'<html><head><title>xiaohongshu</title></head><body><script>window.__INITIAL_STATE__={"feed":{"title":"popular"}}</script></body></html>'

        result = server.parse_xhs_html(page, "missing")

        self.assertFalse(result["found_note"])

    def test_rejects_non_xiaohongshu_source_url(self):
        with self.assertRaisesRegex(ValueError, "只支持小红书"):
            server.prepare_guide_source("https://example.com/post")

    def test_accepts_cn_share_link_with_escaped_url(self):
        page = b'''<html><body><script>
        window.__INITIAL_STATE__={"noteData":{"data":{"noteData":{"noteId":"abc123","title":"Bouillon Republique","desc":"Duck confit recommended","imageList":[]}}}};
        </script></body></html>'''
        with patch.object(
            server, "bounded_fetch",
            return_value=(page, "text/html", "https://www.xiaohongshu.com/discovery/item/abc123"),
        ) as fetch:
            result = server.prepare_guide_source(r"巴黎法餐 https\://xhslink.cn/o/ImNzNURQNH")
        self.assertEqual(result["title"], "Bouillon Republique")
        self.assertEqual(fetch.call_args.args[0], "https://xhslink.cn/o/ImNzNURQNH")
        self.assertTrue(server.is_xhs_page_url("https://xhslink.cn/o/ImNzNURQNH"))

    def test_openai_compatible_request_accepts_multiple_images(self):
        request = server.openai_compatible_request(
            "test",
            server.GUIDE_SCHEMA,
            "guide_candidates",
            ["data:image/jpeg;base64,YQ==", "data:image/png;base64,Yg=="],
            1024,
        )
        body = json.loads(request.data)

        self.assertEqual(request.full_url, "https://models.example/v1/chat/completions")
        self.assertEqual(len(body["messages"][0]["content"]), 3)
        self.assertEqual(body["messages"][0]["content"][2]["image_url"]["url"], "data:image/png;base64,Yg==")
        self.assertNotIn("enable_thinking", body)

    def test_openai_endpoint_accepts_base_or_full_chat_url(self):
        self.assertEqual(server.openai_chat_endpoint("https://models.example/v1"),
                         "https://models.example/v1/chat/completions")
        self.assertEqual(server.openai_chat_endpoint("https://models.example/v1/chat/completions"),
                         "https://models.example/v1/chat/completions")

    def test_model_json_parser_accepts_fenced_json(self):
        self.assertEqual(server.parse_model_json('```json\n{"ok": true}\n```'), {"ok": True})

    def test_guide_schema_requires_verbatim_source_quote(self):
        item_schema = server.GUIDE_SCHEMA["properties"]["items"]["items"]

        self.assertIn("sourceQuote", item_schema["required"])
        self.assertEqual(item_schema["properties"]["sourceQuote"]["type"], "string")
        self.assertIn("rating", item_schema["required"])
        self.assertEqual(item_schema["properties"]["rating"]["maximum"], 5)

    def test_menu_prompt_includes_every_orderable_category(self):
        prompt = server.menu_analysis_prompt([])

        self.assertIn("不得按品类排除内容", prompt)
        self.assertIn("酒类、鸡尾酒、咖啡、茶、果汁、软饮", prompt)
        self.assertIn("以图片的视觉栏目、字号、对齐和上下关系为准", prompt)
        self.assertIn("不得补充常识配方", prompt)
        self.assertIn("priceOptions", prompt)
        self.assertNotIn("酒水不作为菜品", prompt)

    def test_visual_regions_keep_column_order_and_remap_boxes(self):
        region_results = [
            {
                "id": "left", "title": "现场菜单", "pricing": {"mode": "a_la_carte", "fixedPrice": 0, "note": ""},
                "dishes": [{"id": "soup", "original": "French Onion Soup", "descriptionOriginal": "", "nameZh": "法式洋葱汤", "summary": "", "decisionHint": "", "price": 6.5, "priceOptions": [], "tags": [], "guideMatchIds": [], "box": {"x": 100, "y": 200, "w": 200, "h": 30}}],
            },
            {
                "id": "right", "title": "现场菜单", "pricing": {"mode": "a_la_carte", "fixedPrice": 0, "note": ""},
                "dishes": [{"id": "tea", "original": "Tea", "descriptionOriginal": "", "nameZh": "茶", "summary": "", "decisionHint": "", "price": 3, "priceOptions": [], "tags": [], "guideMatchIds": [], "box": {"x": 100, "y": 300, "w": 200, "h": 30}}],
            },
        ]
        regions = [
            {"image": "data:image/jpeg;base64,YQ==", "x": 0, "y": 0, "w": 0.5, "h": 1},
            {"image": "data:image/jpeg;base64,Yg==", "x": 0.5, "y": 0, "w": 0.5, "h": 1},
        ]

        with patch.object(server, "model_request", side_effect=region_results):
            result = server.analyze_visual_menu("prompt", regions[0]["image"], regions)

        self.assertEqual([dish["original"] for dish in result["dishes"]], ["French Onion Soup", "Tea"])
        self.assertEqual(result["dishes"][0]["box"]["x"], 50)
        self.assertEqual(result["dishes"][1]["box"]["x"], 550)

    def test_stream_menu_emits_complete_dishes_in_visual_order(self):
        regions = [
            {"image": "left", "x": 0, "y": 0, "w": 0.5, "h": 1},
            {"image": "right", "x": 0.5, "y": 0, "w": 0.5, "h": 1},
        ]

        def fake_stream(prompt, region, on_dish):
            dish_id = "soup" if region["image"] == "left" else "tea"
            result = {
                "title": "现场菜单",
                "pricing": {"mode": "a_la_carte", "fixedPrice": 0, "note": ""},
                "dishes": [{"id": dish_id, "original": "French Onion Soup" if dish_id == "soup" else "Tea",
                            "nameZh": "法式洋葱汤" if dish_id == "soup" else "茶", "price": 6.5 if dish_id == "soup" else 3,
                            "aiDecisionHint": "像浓汤，咸鲜" if dish_id == "soup" else "清淡茶香",
                            "box": {"x": 100, "y": 100, "w": 200, "h": 30}}],
            }
            on_dish(result["dishes"][0], result)
            if region["image"] == "left":
                time.sleep(0.03)
            return result

        events = []
        with patch.object(server, "stream_openai_compatible_region", side_effect=fake_stream):
            server.stream_visual_menu("prompt", "image", regions, events.append, [
                {"id": "guide-soup", "nameOriginal": "French Onion Soup", "nameZh": "法式洋葱汤"},
            ])

        self.assertEqual([event["type"] for event in events], ["start", "dish", "dish", "done"])
        self.assertEqual([event["dish"]["original"] for event in events[1:3]], ["French Onion Soup", "Tea"])
        self.assertEqual(events[1]["dish"]["aiDecisionHint"], "像浓汤，咸鲜")
        self.assertEqual(events[1]["dish"]["id"], "section-1-soup")
        self.assertEqual(events[1]["dish"]["guideMatchIds"], ["guide-soup"])
        self.assertEqual(events[2]["dish"]["guideMatchIds"], [])
        self.assertEqual(events[2]["dish"]["box"]["x"], 550)

    def test_menu_recommendation_requires_printed_evidence(self):
        dish = {"menuRecommendationLabel": "主厨推荐", "menuRecommendationEvidence": "CHEF'S SPECIAL"}
        server.verify_menu_recommendation(dish, [{"text": "CHEF'S SPECIAL"}])
        self.assertEqual(dish["menuRecommendationLabel"], "主厨推荐")
        unverified = {"menuRecommendationLabel": "本店特色", "menuRecommendationEvidence": "OUR DISHES"}
        server.verify_menu_recommendation(unverified, [{"text": "OUR DISHES"}])
        self.assertEqual(unverified["menuRecommendationLabel"], "")

    def test_streamed_dish_parser_accepts_split_json_objects(self):
        parser = server.StreamedDishParser()
        source = '{"id":"menu","title":"Lunch","pricing":{"mode":"a_la_carte","fixedPrice":0,"note":""},"dishes":[{"id":"one","original":"A \\"B\\"","box":{"x":1}},{"id":"two","original":"Tea","box":{"x":2}}]}'
        dishes = []
        for offset in range(0, len(source), 7):
            dishes.extend(parser.feed(source[offset:offset + 7]))
        self.assertEqual([dish["id"] for dish in dishes], ["one", "two"])
        self.assertEqual(parser.metadata["pricing"]["mode"], "a_la_carte")

    def test_visual_menu_removes_headings_and_does_not_invent_summary(self):
        menu = {"dishes": [
            {"id": "heading", "original": "WHITE", "nameZh": "白葡萄酒"},
            {"id": "drink", "original": "Mojito", "nameZh": "莫吉托", "descriptionOriginal": "", "price": 7},
        ]}

        result = server.canonicalize_visual_menu(menu)

        self.assertEqual([dish["original"] for dish in result["dishes"]], ["Mojito"])
        self.assertEqual(result["dishes"][0]["summary"], "菜单未注明配方或口味")

    def test_ocr_corrects_single_conflicting_price_on_same_row(self):
        menu = {"dishes": [{
            "id": "red-mojito", "original": "Red fruit mojito", "descriptionOriginal": "", "nameZh": "红果莫吉托",
            "summary": "", "decisionHint": "", "price": 8.5, "priceOptions": [], "tags": [], "guideMatchIds": [],
            "box": {"x": 0, "y": 0, "w": 1, "h": 1},
        }]}
        words = [
            {"text": "Red fruit mojito", "rotate_rect": [300, 200, 180, 24, 0]},
            {"text": "7,00 €", "rotate_rect": [520, 200, 55, 24, 0]},
        ]

        result = server.validate_visual_menu_with_ocr(menu, words, (1000, 800))

        self.assertEqual(result["dishes"][0]["price"], 7.0)
        self.assertTrue(result["dishes"][0]["priceCorrectedByOcr"])

    def test_ocr_menu_sections_split_on_uppercase_headings(self):
        words = [
            {"text": "BOTTLE BEERS"},
            {"text": "Corona 33 cl"},
            {"text": "6,00 €"},
            {"text": "HOT DRINKS"},
            {"text": "Espresso"},
            {"text": "2,00 €"},
        ]

        sections = server.ocr_menu_sections(words)

        self.assertEqual([section["title"] for section in sections], ["BOTTLE BEERS", "HOT DRINKS"])
        self.assertEqual(sections[1]["words"][1]["text"], "Espresso")

    def test_dense_ocr_menu_sections_are_structured_in_parallel_and_merged(self):
        words = [{"text": "BOTTLE BEERS"}]
        words.extend({"text": f"Beer item {index}"} for index in range(20))
        words.append({"text": "HOT DRINKS"})
        words.extend({"text": f"Coffee item {index}"} for index in range(20))
        section_result = {
            "id": "page",
            "title": "现场菜单",
            "pricing": {"mode": "a_la_carte", "fixedPrice": 0, "note": ""},
            "dishes": [{"id": "one", "original": "Item", "nameZh": "项目"}],
        }

        with patch.object(server, "model_request", return_value=section_result) as request:
            result = server.analyze_ocr_menu("prompt", words)

        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["pricing"]["mode"], "a_la_carte")
        self.assertEqual([dish["id"] for dish in result["dishes"]], ["section-1-one", "section-2-one"])

    def test_uses_explicit_stars_in_guide_rating(self):
        result = {"items": [{"nameOriginal": "油封鸭 🌟🌟🌟🌟", "rating": 2}]}

        server.apply_explicit_guide_ratings(result)

        self.assertEqual(result["items"][0]["rating"], 4)

    def test_uses_complete_verbatim_source_section_instead_of_model_snippet(self):
        source = "餐厅开场\n🐌黄油蜗牛⭐⭐⭐⭐\n第一次吃，黄油味很香，其实我吃不出来和普通的螺有什么区别🥺但是味道还可以吧\n🦆油封鸭⭐⭐⭐⭐\n法国特色，还是值得一试"
        result = {"items": [
            {"nameZh": "黄油蜗牛", "nameOriginal": "黄油蜗牛", "sourceQuote": "🐌黄油蜗牛⭐⭐⭐⭐"},
            {"nameZh": "油封鸭", "nameOriginal": "油封鸭", "sourceQuote": "法国特色"},
        ]}

        server.apply_verbatim_source_passages(result, source)

        self.assertEqual(
            result["items"][0]["sourceQuote"],
            "🐌黄油蜗牛⭐⭐⭐⭐\n第一次吃，黄油味很香，其实我吃不出来和普通的螺有什么区别🥺但是味道还可以吧",
        )
        self.assertEqual(result["items"][1]["sourceQuote"], "🦆油封鸭⭐⭐⭐⭐\n法国特色，还是值得一试")

    def test_keeps_model_quote_when_text_source_has_no_matching_name(self):
        result = {"items": [{"nameZh": "焦糖布蕾", "nameOriginal": "Crème brûlée", "sourceQuote": "截图里的完整原文"}]}

        server.apply_verbatim_source_passages(result, "正文只介绍了餐厅环境")

        self.assertEqual(result["items"][0]["sourceQuote"], "截图里的完整原文")

    def test_matches_dish_names_to_ocr_coordinates(self):
        menu = {"dishes": [{
            "original": "PANKO CHICKEN SCHNITZEL\n2 chicken breasts",
            "box": {"x": 0, "y": 0, "w": 1, "h": 1},
        }]}
        words = [{"text": "PANKO CHICKEN SCHNITZEL 179", "rotate_rect": [600, 400, 300, 40, 0]}]

        result = server.attach_ocr_boxes(menu, words, (1000, 800))

        self.assertEqual(result["dishes"][0]["boxSource"], "ocr")
        self.assertEqual(result["dishes"][0]["box"], {"x": 450.0, "y": 475.0, "w": 300.0, "h": 50.0})

    def test_ocr_location_recovers_horizontal_line_from_rotated_rectangle(self):
        menu = {"dishes": [{"original": "Demory IPA"}]}
        words = [{
            "text": "Demory IPA",
            "rotate_rect": [710, 920, 20, 110, -89],
            "location": [655, 910, 765, 910, 765, 930, 655, 930],
        }]

        result = server.attach_ocr_boxes(menu, words, (1000, 1000))

        self.assertEqual(result["dishes"][0]["box"], {"x": 655.0, "y": 910.0, "w": 110.0, "h": 20.0})

    def test_ocr_rotated_rectangle_fallback_uses_horizontal_dimensions(self):
        menu = {"dishes": [{"original": "Demory IPA"}]}
        words = [{"text": "Demory IPA", "rotate_rect": [710, 920, 20, 110, -89]}]

        result = server.attach_ocr_boxes(menu, words, (1000, 1000))

        self.assertEqual(result["dishes"][0]["box"], {"x": 655.0, "y": 910.0, "w": 110.0, "h": 20.0})

    def test_normalizes_multiple_menu_objects(self):
        result = server.normalize_result([
            {"id": "a", "title": "前菜", "dishes": [{"id": "one"}]},
            {"id": "b", "title": "主菜", "dishes": [{"id": "two"}]},
        ], server.MENU_SCHEMA, "menu_page")

        self.assertEqual(result["id"], "a")
        self.assertEqual([dish["id"] for dish in result["dishes"]], ["one", "two"])

    def test_normalizes_direct_dish_array(self):
        dishes = [{"id": "one", "original": "Soupe", "nameZh": "汤"}, {"id": "two", "original": "Canard", "nameZh": "鸭肉"}]
        result = server.normalize_result(dishes, server.MENU_SCHEMA, "menu_page")

        self.assertEqual(result["title"], "现场菜单")
        self.assertEqual(result["dishes"], dishes)
        self.assertEqual(result["pricing"]["mode"], "unknown")

    def test_rejects_false_generic_soup_guide_match(self):
        menu = {"dishes": [{
            "original": "Soupe de Poissons Maison",
            "nameZh": "自制鱼汤",
            "guideMatchIds": ["onion-soup"],
        }]}
        guide = [{
            "id": "onion-soup",
            "nameOriginal": "Soupe à l'oignon",
            "nameZh": "法式洋葱汤",
        }]

        result = server.validate_guide_matches(menu, guide)

        self.assertEqual(result["dishes"][0]["guideMatchIds"], [])

    def test_keeps_specific_duck_confit_guide_match(self):
        menu = {"dishes": [{
            "original": "Confit de canard, pommes sarladaises",
            "nameZh": "油封鸭腿配萨拉代兹土豆",
            "guideMatchIds": ["duck-confit"],
        }]}
        guide = [{
            "id": "duck-confit",
            "nameOriginal": "Confit de Canard",
            "nameZh": "油封鸭腿",
        }]

        result = server.validate_guide_matches(menu, guide)

        self.assertEqual(result["dishes"][0]["guideMatchIds"], ["duck-confit"])

    def test_rejects_generic_steak_as_specific_menu_match(self):
        menu = {"dishes": [{
            "original": "Entrecote grillee au thym, frites maison",
            "nameZh": "百里香烤肋眼牛排配薯条",
            "guideMatchIds": ["generic-steak"],
        }]}
        guide = [{
            "id": "generic-steak",
            "nameOriginal": "🐂牛排🌟🌟🌟",
            "nameZh": "牛排",
        }]

        result = server.validate_guide_matches(menu, guide)

        self.assertEqual(result["dishes"][0]["guideMatchIds"], [])

    def test_assigns_guide_match_when_guide_arrives_after_menu(self):
        menu = {"dishes": [
            {"id": "duck", "original": "Confit de canard, pommes sarladaises", "nameZh": "油封鸭腿"},
            {"id": "fish", "original": "Soupe de Poissons Maison", "nameZh": "自制鱼汤"},
        ]}
        guide = [
            {"id": "duck-confit", "nameOriginal": "Confit de canard", "nameZh": "油封鸭腿"},
            {"id": "onion-soup", "nameOriginal": "Soupe a l'oignon", "nameZh": "法式洋葱汤"},
        ]

        result = server.assign_guide_matches(menu, guide)

        self.assertEqual(result["dishes"][0]["guideMatchIds"], ["duck-confit"])
        self.assertEqual(result["dishes"][1]["guideMatchIds"], [])

    def test_model_guide_matches_accepts_only_known_ids(self):
        dishes = [
            {"id": "duck", "original": "Confit de canard", "nameZh": "油封鸭腿", "summary": "咸香"},
            {"id": "fish", "original": "Filet de bar", "nameZh": "鲈鱼", "summary": "清淡"},
        ]
        guide = [{"id": "recommended-duck", "nameZh": "招牌鸭腿", "nameOriginal": "", "note": "推荐"}]
        model_result = {"items": [
            {"dishId": "duck", "guideItemIds": ["recommended-duck", "made-up-guide"]},
            {"dishId": "made-up-dish", "guideItemIds": ["recommended-duck"]},
        ]}

        with patch.object(server, "model_request", return_value=model_result):
            result = server.model_guide_matches(dishes, guide)

        self.assertEqual(result["duck"], ["recommended-duck"])
        self.assertEqual(result["fish"], [])
        self.assertNotIn("made-up-dish", result)

    def test_model_guide_matches_filters_generic_dish_even_if_model_returns_it(self):
        dishes = [{"id": "ribeye", "original": "Entrecote grillee", "nameZh": "烤肋眼牛排", "summary": "烧烤"}]
        guide = [{"id": "generic-steak", "nameZh": "牛排", "nameOriginal": "", "note": "熟度偏生"}]
        model_result = {"items": [{"dishId": "ribeye", "guideItemIds": ["generic-steak"]}]}

        with patch.object(server, "model_request", return_value=model_result):
            result = server.model_guide_matches(dishes, guide)

        self.assertEqual(result["ribeye"], [])

    def test_structured_image_request_and_response(self):
        def fake_urlopen(request, timeout):
            body = json.loads(request.data)
            self.assertEqual(request.full_url, "https://models.example/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            self.assertEqual(body["model"], "test-vision-model")
            self.assertEqual(body["response_format"]["type"], "json_schema")
            self.assertEqual(body["response_format"]["json_schema"]["schema"], server.CHAT_SCHEMA)
            self.assertEqual(body["max_tokens"], 8192)
            image = body["messages"][0]["content"][1]["image_url"]
            self.assertEqual(image, {"url": "data:image/jpeg;base64,YQ=="})
            return FakeResponse()

        with patch("urllib.request.urlopen", fake_urlopen):
            result = server.model_request(
                "test",
                server.CHAT_SCHEMA,
                "menu_chat",
                "data:image/jpeg;base64,YQ==",
            )

        self.assertEqual(result, {"message": "ok", "dishIds": [], "actions": []})

    def test_retries_temporary_model_overload(self):
        unavailable = __import__("urllib.error").error.HTTPError(
            "https://example.test",
            503,
            "unavailable",
            {},
            __import__("io").BytesIO(b'{"error":{"status":"UNAVAILABLE"}}'),
        )
        responses = [unavailable, FakeResponse()]

        with patch("urllib.request.urlopen", side_effect=responses) as urlopen, patch("time.sleep") as sleep:
            result = server.model_request("test", server.CHAT_SCHEMA, "menu_chat")

        self.assertEqual(result["message"], "ok")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
