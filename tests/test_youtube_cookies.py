# -*- coding: utf-8 -*-
"""유튜브 쿠키: 저장 검사(Netscape 형식·youtube.com), yt-dlp 인자, 로그인 요구 오류 알아보기"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="ytc-"))

from tgup import compat, youtube  # noqa: E402

GOOD = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1999999999\tSID\tabc\n.youtube.com\tTRUE\t/\tTRUE\t1999999999\tHSID\tdef\n"


class CookieTest(unittest.TestCase):
    def setUp(self):
        compat.DATA_DIR = tempfile.mkdtemp(prefix="ytc-data-")
        self.env = os.environ.pop("YTDLP_COOKIES", None)
        self.addCleanup(lambda: os.environ.__setitem__("YTDLP_COOKIES", self.env) if self.env else os.environ.pop("YTDLP_COOKIES", None))

    def test_save_and_args(self):
        self.assertEqual(youtube.cookie_args(), [])
        self.assertFalse(youtube.cookies_status()["set"])
        self.assertEqual(youtube.save_cookies(GOOD), 2)
        p = youtube.cookies_path()
        self.assertEqual(youtube.cookie_args(), ["--cookies", p])
        self.assertEqual(oct(os.stat(p).st_mode & 0o777), "0o600")             # 이 서버만 읽게
        st = youtube.cookies_status()
        self.assertTrue(st["set"] and st["source"] == "upload" and "text" not in st)   # 내용은 돌려주지 않음
        self.assertTrue(youtube.delete_cookies())
        self.assertEqual(youtube.cookie_args(), [])

    def test_reject_bad(self):
        with self.assertRaises(ValueError):
            youtube.save_cookies("hello world")
        with self.assertRaises(ValueError):
            youtube.save_cookies(".google.com\tTRUE\t/\tTRUE\t1999999999\tSID\tabc\n")   # youtube.com 쿠키 없음
        self.assertFalse(youtube.cookies_status()["set"])

    def test_env_path_wins(self):
        youtube.save_cookies(GOOD)
        f = os.path.join(compat.DATA_DIR, "mine.txt")
        open(f, "w").write(GOOD)
        os.environ["YTDLP_COOKIES"] = f
        self.assertEqual(youtube.cookie_args(), ["--cookies", f])
        self.assertEqual(youtube.cookies_status()["source"], "env")

    def test_login_required_detected(self):
        tail = ["ERROR: [youtube] kzAfNg6pAvI: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication."]
        e = youtube._fail(tail, 1)
        self.assertIsInstance(e, youtube.LoginRequired)
        self.assertIn("쿠키 파일", str(e))
        youtube.save_cookies(GOOD)
        self.assertIn("만료", str(youtube._fail(tail, 1)))                  # 쿠키가 있는데도면 만료·막힘
        other = youtube._fail(["ERROR: [youtube] abc: Video unavailable. This video is private"], 1)
        self.assertNotIsInstance(other, youtube.LoginRequired)
        self.assertIn("Video unavailable", str(other))                      # 오류 앞부분이 남음


if __name__ == "__main__":
    unittest.main()


try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class NoRetryTest(unittest.TestCase):
    def test_login_required_gives_up_without_retry(self):
        import asyncio
        from tgup import plex_to_tg as m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="ytc-run-")
        mir = m.Mirror(None, None, lambda *a: None, None)
        mir._route = lambda tg: "direct"

        async def nothing(*a, **k):
            return 0
        mir._drop_partial = nothing
        mir._resumable = lambda *a: None

        async def upload(rule, key, max_gb, test=False):
            raise youtube.LoginRequired("유튜브가 로그인(봇 확인)을 요구합니다 - [유튜브 보내기] 탭에서 쿠키 파일(cookies.txt)을 넣어 주세요.")
        mir.upload = upload
        rule = {"id": "yt1", "tg": "tg", "kind": "folder", "media": "youtube", "folder": compat.DATA_DIR, "enabled": True,
                "channel": "-1", "channel_title": "c"}
        mir.queue = [{"rule": "yt1", "key": "yt-AAAAAAAAAAA", "title": "영상"}]
        asyncio.run(mir.run_queue({"rules": [rule], "hours": "", "encode_slots": 1, "max_gb": 2}))
        st = m.load_state()
        h = st["history"][0]
        self.assertFalse(h["ok"])
        self.assertIn("다시 시도하지 않음", h["note"])
        self.assertNotIn("yt-AAAAAAAAAAA", (st["rules"].get("yt1") or {}).get("retry") or {})
