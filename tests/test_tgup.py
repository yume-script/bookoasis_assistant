# -*- coding: utf-8 -*-
"""텔레그램 자동 올리기 (tgup) - python3 -m unittest discover -s tests

aiohttp가 없으면 건너뛴다 (그 모듈만 꺼지는 것과 같게). 텔레그램·Plex에는 붙지 않는다.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="tgup-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class TgupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tgup import compat, service
        cls.compat, cls.service = compat, service
        cls.data = tempfile.mkdtemp(prefix="tgup-data-")
        compat.DATA_DIR = cls.data
        service.RUNNER.start()

    @classmethod
    def tearDownClass(cls):
        cls.service.RUNNER.stop()
        shutil.rmtree(cls.data, ignore_errors=True)

    def test_local_path_uses_plex_path_map(self):
        os.environ["PLEX_PATH_MAP"] = "/mnt/media=/data"
        try:
            self.assertEqual(self.compat.local_path("/data/영화/a.mkv"), "/mnt/media/영화/a.mkv")
            self.assertEqual(self.compat.local_path("/other/a.mkv"), "/other/a.mkv")
        finally:
            del os.environ["PLEX_PATH_MAP"]

    def test_settings_save_and_status(self):
        api_post, api_get, ApiError = self.service.api_post, self.service.api_get, self.service.ApiError
        data = self.compat.load()
        data.pop("telegram", None)   # API 값이 없으면 텔레그램에 붙지 않고 바로 "로그인 안 됨"
        self.compat.save(data)
        with self.assertRaises(ApiError):   # 채널이 없는 규칙
            api_post("/api/tgup/settings", {"rules": [{"kind": "folder", "folder": "/tmp", "tg": "tg"}]})
        folder = tempfile.mkdtemp(prefix="tgup-folder-")
        try:
            res = api_post("/api/tgup/settings", {"interval": 5, "rules": [
                {"kind": "folder", "folder": folder, "tg": "tg", "channel": "-100123", "channel_title": "채널"}]})
            rule = res["settings"]["rules"][0]
            self.assertEqual((rule["kind"], rule["channel"], rule["height"]), ("folder", "-100123", 720))
            self.assertTrue(os.path.exists(os.path.join(self.data, "settings.json")))
            got = api_get("/api/tgup", {})
            self.assertEqual(got["settings"]["interval"], 5)
            self.assertIn("queue", got["status"])
            self.assertFalse(got["account"]["authorized"])
            # 항목 동작: 없는 것 취소는 400, 전체 취소는 0개
            with self.assertRaises(ApiError):
                api_post("/api/tgup/item", {"rule": rule["id"], "key": "없음", "action": "cancel"})
            self.assertEqual(api_post("/api/tgup/item", {"action": "cancel_all"})["count"], 0)
            with self.assertRaises(ApiError):
                api_post("/api/tgup/item", {"action": "nope"})
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_account_api_values(self):
        api_post, ApiError = self.service.api_post, self.service.ApiError
        with self.assertRaises(ApiError):
            api_post("/api/tgup/account", {"action": "save_api", "api_id": "abc", "api_hash": "x"})
        with self.assertRaises(ApiError):   # Hash 없음
            api_post("/api/tgup/account", {"action": "save_api", "api_id": "123"})
        from tgup import tgaccount
        data = self.compat.load()
        data["telegram"] = {"api_id": "123", "api_hash": "abc"}
        self.compat.save(data)
        self.assertEqual(tgaccount.api_conf()["api_id"], "123")
        self.assertEqual(oct(os.stat(os.path.join(self.data, "settings.json")).st_mode & 0o777), "0o600")

    def test_folder_list(self):
        res = self.service.api_get("/api/tgup/folders", {"path": ROOT})
        self.assertIn("tgup", res["dirs"])
        with self.assertRaises(self.service.ApiError):
            self.service.api_get("/api/tgup/없는주소", {})


if __name__ == "__main__":
    unittest.main()
