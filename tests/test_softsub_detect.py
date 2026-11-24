# -*- coding: utf-8 -*-
"""소프트 자막 내용으로 언어 알아보기 (5분 간격으로 조금씩 읽음) · 자막 판단용 장면 5분 간격 이어 붙이기 - 진짜 ffmpeg로"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="softsub-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

from tgup import folder_watch as fw  # noqa: E402


def _srt(path, line, every=20, until=700):
    with open(path, "w", encoding="utf-8") as f:
        for i, t in enumerate(range(0, until, every), 1):
            f.write(f"{i}\n00:{t // 60:02d}:{t % 60:02d},000 --> 00:{t // 60:02d}:{t % 60:02d},900\n{line} {i}\n\n")


class PureTest(unittest.TestCase):
    def test_sample_times_and_ratio(self):
        self.assertEqual(fw.sample_times(3600), [300, 600, 900, 1200, 1500, 1800, 2100, 2400])   # 5분마다 최대 8곳
        self.assertEqual(fw.sample_times(700), [300, 600])
        self.assertEqual(fw.sample_times(120), [0])
        self.assertGreater(fw.korean_ratio("안녕하세요 오늘은 날씨가 좋네요"), 0.9)
        self.assertLess(fw.korean_ratio("Hello there, how are you today"), 0.1)
        self.assertIsNone(fw.korean_ratio("... 123"))

    def test_classify_uses_detected(self):
        und_ko = {"codec": "subrip", "lang": "", "detected": "ko"}
        und_en = {"codec": "subrip", "lang": "und", "detected": "other"}
        kor_but_en = {"codec": "subrip", "lang": "kor", "detected": "other"}
        eng_but_ko = {"codec": "ass", "lang": "eng", "detected": "ko"}
        self.assertTrue(fw.classify_subs([und_ko])["usable"])
        r = fw.classify_subs([und_en])
        self.assertFalse(r["usable"])
        self.assertIn("한국어 아님", r["why"])
        self.assertFalse(fw.classify_subs([kor_but_en])["usable"])     # 표시만 kor
        self.assertTrue(fw.classify_subs([eng_but_ko])["usable"])      # 표시가 잘못된 한국어
        self.assertTrue(fw.classify_subs([{"codec": "subrip", "lang": ""}])["usable"])   # 못 읽었으면 예전처럼 (표시 없음 = 씀)

    def test_text_subs_order_by_detected(self):
        info = {"streams": [{"codec_type": "subtitle", "codec_name": "subrip", "index": 2, "tags": {"language": "kor"}},
                            {"codec_type": "subtitle", "codec_name": "subrip", "index": 3, "tags": {}}]}
        self.assertEqual([x[0] for x in fw.text_subs(info)], [2, 3])
        self.assertEqual([x[0] for x in fw.text_subs(info, {2: "other", 3: "ko"})], [3, 2])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 없음")
class FfmpegTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="softsub-")
        ko, en = os.path.join(cls.d, "ko.srt"), os.path.join(cls.d, "en.srt")
        _srt(ko, "안녕하세요 오늘도 좋은 하루 보내세요")
        _srt(en, "Hello there my friend how are you")
        cls.mkv = os.path.join(cls.d, "v.mkv")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=1:d=700", "-i", ko, "-i", en,
                        "-map", "0", "-map", "1", "-map", "2", "-c:v", "libx264", "-preset", "ultrafast", "-c:s", "srt",
                        "-metadata:s:s:1", "language=kor", cls.mkv], check=True)   # 한국어 트랙은 표시 없음, 영어 트랙에 kor 표시

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def test_detect(self):
        async def run():
            info = await fw.probe(self.mkv)
            tracks = fw.stream_tracks(info)
            await fw.detect_sub_langs(self.mkv, tracks, fw.duration(info))
            return tracks
        tracks = asyncio.run(run())
        self.assertEqual([t["detected"] for t in tracks], ["ko", "other"])
        r = fw.classify_subs(tracks)
        self.assertTrue(r["usable"])
        self.assertEqual(r["korean"], 1)

    @unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
    def test_shot_sheet(self):
        from tgup import plex_to_tg as m
        mir = m.Mirror(None, None, lambda *a: None, None)
        out = os.path.join(self.d, "sheet.jpg")
        asyncio.run(mir._grab_sheet(["-i", self.mkv], 700, out))   # 5분·10분 두 장 -> 한 장으로
        w = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.strip()
        self.assertGreater(int(w), 480)   # 가로로 두 장 이어 붙음
        self.assertFalse(os.path.exists(out + ".parts"))
        strips = os.path.join(self.d, "strips.jpg")   # LLM용: 장면마다 아래 25%만 위아래로
        asyncio.run(mir._grab_sheet(["-i", self.mkv], 700, strips, strips=True))
        wh = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", strips],
                            capture_output=True, text=True).stdout.strip().split(",")
        w, hgt = int(wh[0]), int(wh[1])
        self.assertEqual(w, 960)
        self.assertLess(hgt, 960 * 90 / 160 * 0.25 * 2 + 20)   # 띠 두 개 (원본 높이의 25%씩)


if __name__ == "__main__":
    unittest.main()
