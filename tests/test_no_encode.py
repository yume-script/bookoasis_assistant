# -*- coding: utf-8 -*-
"""[인코딩 없이 올리기]: 영상은 그대로 복사(줄이기·자막 입히기 없이), 소리만 AAC·mp4로 - 인코딩 중에 눌러도 멈추고 복사로"""
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
TMP = tempfile.mkdtemp(prefix="noenc-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    import telethon  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

from tgup import folder_watch as fw  # noqa: E402


class PlanTest(unittest.TestCase):
    def test_video_copy_plan(self):
        info = {"streams": [{"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv420p10le", "height": 2160},
                            {"codec_type": "audio", "codec_name": "eac3"}]}
        p = fw.encode_plan(info, ".mkv", 720, "s.srt", {"name": "cpu", "video_copy": True})
        args = p[0]
        self.assertEqual(args[args.index("-c:v") + 1], "copy")             # 영상 그대로 (줄이기·자막 입히기 없음)
        self.assertEqual(args[args.index("-c:a") + 1], "aac")              # 소리는 AAC로
        self.assertNotIn("-vf", args)
        self.assertEqual(p.encoder, "copy")
        ok = {"streams": [{"codec_type": "video", "codec_name": "hevc"}, {"codec_type": "audio", "codec_name": "aac"}]}
        self.assertIsNone(fw.encode_plan(ok, ".mp4", 720, "s.srt", {"name": "cpu", "video_copy": True}))   # 손댈 것 없음


@unittest.skipUnless(HAVE and HAVE_FFMPEG, "aiohttp·telethon·ffmpeg 필요")
class NoEncodeTest(unittest.TestCase):
    def setUp(self):
        from tgup import compat, plex_to_tg as m
        self.m = m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="noenc-data-")
        self.root = tempfile.mkdtemp(prefix="noenc-src-")
        srt = os.path.join(self.root, "Show.S01E01.ko.srt")
        with open(srt, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,500 --> 00:00:01,500\n안녕하세요\n")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:r=10:d=3", "-f", "lavfi", "-i", "sine=d=3",
                        "-c:v", "mpeg4", "-c:a", "mp3", os.path.join(self.root, "Show.S01E01.mkv")], check=True)
        self.rule = m.clean_settings({"rules": [{"id": "n1", "kind": "folder", "folder": self.root, "tg": "tg", "channel": "-100",
                                                 "wait_subs": True, "burn_subs": True, "height": 720}]})["rules"][0]
        self.sent = []

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_upload(self, mir, job):
        sent = self.sent

        class Client:
            async def send_file(self, peer, path, **kw):
                sent.append((os.path.basename(path), path, kw))
                if path.endswith(".mp4"):
                    shutil.copy(path, os.path.join(TMP, "got.mp4"))
                return types.SimpleNamespace(id=len(sent))

            async def get_me(self):
                return types.SimpleNamespace(premium=False)

        class Tg:
            async def authorized_client(self):
                return Client()

            async def peer(self, ch):
                return ch
        mir.tg_for = lambda *a: Tg()
        mir._duplicate = lambda *a, **k: asyncio.sleep(0, "")
        mir._find_poster = lambda *a, **k: asyncio.sleep(0, "")
        m = self.m

        async def run():
            lane = m.Lane("tg")
            m._LANE.set(lane)
            lane.job = job
            lane.current_job = {"rule": "n1", "key": job["key"], "tg": "tg"}
            mir.queue = [job]
            return await mir.upload(self.rule, job["key"], 2, test=True)
        return asyncio.run(run())

    def codecs(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout.split()
        return out

    def test_marked_before(self):
        m = self.m
        mir = m.Mirror(None, None, lambda *a: None, None)
        note = self.run_upload(mir, {"rule": "n1", "key": "Show.S01E01.mkv", "title": "t", "no_encode": True})
        names = [n for n, _p, _k in self.sent]
        self.assertEqual(names[0], "Show.S01E01.mp4")
        self.assertEqual(self.codecs(os.path.join(TMP, "got.mp4")), ["mpeg4", "aac"])   # 영상 그대로, 소리 AAC
        self.assertNotIn("자막 입힘", note)
        self.assertIn("Show.S01E01.ko.srt", names)                                       # 자막은 파일로 같이

    def test_pressed_during_encode(self):
        m = self.m
        mir = m.Mirror(None, None, lambda *a: None, None)
        job = {"rule": "n1", "key": "Show.S01E01.mkv", "title": "t"}
        real = mir._encode_run
        calls = []

        async def run(src, args, out, duration, title, phase, cwd, pre=()):
            calls.append(phase)
            if len(calls) == 1:   # 인코딩(자막 입히기)이 돌던 중에 [인코딩 없이 올리기]를 누름
                mir.no_encode_item("n1", job["key"])
                return await real(src, args, out, duration, title, phase, cwd, pre)
            return await real(src, args, out, duration, title, phase, cwd, pre)
        mir._encode_run = run
        note = self.run_upload(mir, job)
        self.assertEqual(len(calls), 2)
        self.assertIn("자막 입힘", calls[0])
        self.assertEqual(calls[1], "영상 그대로 담는 중")
        self.assertEqual(self.codecs(os.path.join(TMP, "got.mp4")), ["mpeg4", "aac"])
        self.assertNotIn("자막 입힘", note)


if __name__ == "__main__":
    unittest.main()
