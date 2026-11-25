# -*- coding: utf-8 -*-
"""텔레그램 올리기 인코딩: 한국어 음성으로 고정 (tgup/folder_watch.encode_plan / pick_audio)"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="koaudio-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

from tgup import folder_watch as fw  # noqa: E402

V = {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "height": 720, "index": 0}


def aud(i, lang="", codec="aac", title=""):
    return {"codec_type": "audio", "codec_name": codec, "index": i, "tags": {"language": lang, "title": title}}


class PlanTest(unittest.TestCase):
    def test_pick(self):
        a, ko, n = fw.pick_audio({"streams": [V, aud(1, "eng"), aud(2, "kor")]})
        self.assertEqual((a["index"], ko, n), (2, True, 2))
        a, ko, n = fw.pick_audio({"streams": [V, aud(1, "und", title="Commentary"), aud(2, "und", title="한국어 더빙")]})
        self.assertEqual((a["index"], ko), (2, True))
        a, ko, n = fw.pick_audio({"streams": [V, aud(1, "eng"), aud(2, "jpn")]})
        self.assertEqual((a["index"], ko), (1, False))                 # 한국어가 없으면 첫 트랙

    def test_plan(self):
        p = fw.encode_plan({"streams": [V, aud(1, "eng"), aud(2, "kor")]}, ".mp4", 1080)
        self.assertIsNotNone(p)                                        # 한국어가 뒤에 있으면 다시 담음 (영상은 복사)
        args = p[0]
        self.assertEqual(args[args.index("-map", 2) + 1], "0:2")
        self.assertEqual(args[args.index("-c:v") + 1], "copy")
        self.assertIn("language=kor", args)
        self.assertIn("한국어 음성만", p[1])
        self.assertIsNone(fw.encode_plan({"streams": [V, aud(1, "kor"), aud(2, "eng")]}, ".mp4", 1080))   # 이미 첫 트랙이 한국어
        p = fw.encode_plan({"streams": [V, aud(1, "eng", "ac3"), aud(2, "kor", "eac3")]}, ".mkv", 1080)
        args = p[0]
        self.assertEqual((args[args.index("-map", 2) + 1], args[args.index("-c:a") + 1]), ("0:2", "aac"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 없음")
class FfmpegTest(unittest.TestCase):
    def test_output_has_only_korean(self):
        d = tempfile.mkdtemp(prefix="koaudio-")
        self.addCleanup(shutil.rmtree, d, True)
        src, out = os.path.join(d, "s.mkv"), os.path.join(d, "o.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=160x90:r=10:d=2",
                        "-f", "lavfi", "-i", "sine=f=440:d=2", "-f", "lavfi", "-i", "sine=f=880:d=2",
                        "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "mp3",
                        "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=kor", src], check=True)
        import asyncio
        info = asyncio.run(fw.probe(src))
        p = fw.encode_plan(info, ".mkv", 0)
        subprocess.run(["ffmpeg", "-v", "error", "-i", src, *p[0], out], check=True)
        got = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name:stream_tags=language",
                              "-of", "csv=p=0", out], capture_output=True, text=True).stdout.split()
        self.assertEqual(got, ["aac,kor"])


if __name__ == "__main__":
    unittest.main()
