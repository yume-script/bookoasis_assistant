# -*- coding: utf-8 -*-
"""[자막 없이 바로 올리기] 규칙: 자막을 기다리지 않고 자막 판별도 안 하지만, 있는 자막은 입히고 mp4로 - 진짜 ffmpeg로"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="direct-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    import telethon  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE and HAVE_FFMPEG, "aiohttp·telethon·ffmpeg 필요")
class DirectUploadTest(unittest.TestCase):
    def test_no_wait_uploads_original_without_encoding(self):
        from tgup import compat, plex_to_tg as m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="direct-data-")
        root = tempfile.mkdtemp(prefix="direct-src-")
        srt = os.path.join(root, "s.srt")
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,500 --> 00:00:01,500\n안녕하세요\n")
        video = os.path.join(root, "Show.S01E01.mkv")   # mpeg4 영상 + 소프트 자막 (예전엔 자막까지 입혀 인코딩)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:r=10:d=3", "-f", "lavfi", "-i", "sine=d=3",
                        "-i", srt, "-map", "0", "-map", "1", "-map", "2", "-c:v", "mpeg4", "-c:a", "mp3", "-c:s", "srt", video], check=True)
        shutil.copy(srt, os.path.join(root, "Show.S01E01.ko.srt"))   # 옆 자막 파일도 있음
        sent = []

        class Client:
            async def send_file(self, peer, path, **kw):
                sent.append((os.path.basename(path), kw))
                return types.SimpleNamespace(id=len(sent))

            async def get_me(self):
                return types.SimpleNamespace(premium=False)

        class Tg:
            async def authorized_client(self):
                return Client()

            async def peer(self, ch):
                return ch
        rule = m.clean_settings({"rules": [{"id": "d1", "kind": "folder", "folder": root, "tg": "tg", "channel": "-100",
                                            "wait_subs": False, "burn_subs": False, "height": 720}]})["rules"][0]
        self.assertTrue(rule["burn_subs"])   # 바로 올리기는 있는 자막을 입힌다

        async def run():
            mir = m.Mirror(None, None, lambda *a: Tg(), None)
            mir._duplicate = lambda *a, **k: asyncio.sleep(0, "")
            mir._find_poster = lambda *a, **k: asyncio.sleep(0, "")
            lane = m.Lane("tg")
            m._LANE.set(lane)
            lane.current_job = {"rule": "d1", "key": "Show.S01E01.mkv", "tg": "tg"}
            return await mir.upload(rule, "Show.S01E01.mkv", 2, test=True)
        try:
            note = asyncio.run(run())
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertEqual([n for n, _ in sent], ["Show.S01E01.mp4"])   # 자막을 입혀 mp4 하나 (자막 파일은 따로 안 올림)
        self.assertIn("자막 기다리지 않고 바로 올림", note)
        self.assertIn("자막 입힘", note)


if __name__ == "__main__":
    unittest.main()
