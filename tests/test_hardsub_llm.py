# -*- coding: utf-8 -*-
"""하드섭 자동 판단 (선택) - 가짜 LiteLLM(OpenAI 호환) 서버로 (tgup/hardsub_llm.py, Mirror._judge_waiting)"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="hardsub-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp
    from aiohttp import web
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False

from tgup import hardsub_llm  # noqa: E402


class PureTest(unittest.TestCase):
    def test_settings_and_parse(self):
        self.assertEqual(hardsub_llm.settings(None), {"enabled": False, "url": "", "model": "", "auto": True})
        self.assertEqual(hardsub_llm.settings({"enabled": 1, "url": "127.0.0.1:4000/", "model": " g "})["url"], "http://127.0.0.1:4000")
        self.assertEqual(hardsub_llm.ready({"enabled": False}), "꺼짐")
        self.assertIn("모델", hardsub_llm.ready({"enabled": True, "url": "http://x"}))
        v = hardsub_llm.parse('```json\n{"hardsub": true, "korean": true, "confidence": 0.93, "reason": "아래 자막"}\n```')
        self.assertTrue(hardsub_llm.is_go(v))
        self.assertEqual(hardsub_llm.label(v), "LLM: 한국어 하드섭 (93%)")
        self.assertFalse(hardsub_llm.is_go({**v, "confidence": 0.5}))
        self.assertFalse(hardsub_llm.is_go({**v, "korean": False}))
        self.assertEqual(hardsub_llm._endpoint("http://h:4000/v1"), "http://h:4000/v1/chat/completions")
        with self.assertRaises(ValueError):
            hardsub_llm.parse("모르겠어요")


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class JudgeTest(unittest.TestCase):
    def test_judge_and_auto_upload(self):
        from tgup import compat, plex_to_tg as m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="hardsub-data-")
        seen = []

        async def handler(request):
            body = await request.json()
            seen.append((request.headers.get("Authorization"), body))
            ans = {"hardsub": True, "korean": True, "confidence": 0.9, "reason": "화면 아래 한국어 대사"}
            return web.json_response({"choices": [{"message": {"content": json.dumps(ans, ensure_ascii=False)}}]})

        async def run():
            app = web.Application()
            app.router.add_post("/v1/chat/completions", handler)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            port = site._server.sockets[0].getsockname()[1]
            data = compat.load()
            data["plex_to_tg"] = m.clean_settings({"rules": [{"id": "r1", "kind": "folder", "folder": "/tmp", "tg": "tg", "channel": "-100"}],
                                                   "hardsub_llm": {"enabled": True, "url": f"http://127.0.0.1:{port}", "model": "gemini-flash"}})
            data["hardsub_llm_key"] = "sk-test"
            compat.save(data)
            st = m.load_state()
            st["rules"]["r1"] = {"done": [], "fails": {}, "waiting": {"a.mkv": {"title": "드라마 E01", "since": 1}}}
            m.save_state(st)
            shot = m._shot_path("r1", "a.mkv")
            os.makedirs(os.path.dirname(shot), exist_ok=True)
            with open(shot, "wb") as f:
                f.write(b"\xff\xd8jpeg")
            async with aiohttp.ClientSession() as http:
                mir = m.Mirror(None, None, lambda *a: None, lambda: http)
                mir.queue, mir.wake = [], lambda: None
                await mir._judge_waiting()
            await runner.cleanup()
            return mir
        mir = asyncio.run(run())
        auth, body = seen[0]
        self.assertEqual(auth, "Bearer sk-test")
        self.assertEqual(body["model"], "gemini-flash")
        self.assertTrue(body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(mir.queue[0]["key"], "a.mkv")                       # 한국어 하드섭 -> 바로 올리기
        self.assertTrue(mir.queue[0]["force"])
        self.assertIn("한국어 하드섭", mir.queue[0]["note_pre"])
        self.assertNotIn("a.mkv", m.load_state()["rules"]["r1"].get("waiting") or {})


if __name__ == "__main__":
    unittest.main()
