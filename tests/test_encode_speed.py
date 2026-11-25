# -*- coding: utf-8 -*-
"""인코딩 빠르게: 하드웨어 인코더면 원본 디코딩도 그래픽 카드로(설정으로 끔), 인코딩 CPU 우선순위 설정"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="encspeed-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

from tgup import folder_watch as fw  # noqa: E402

HEVC = {"streams": [{"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv420p10le", "height": 1080},
                    {"codec_type": "audio", "codec_name": "eac3"}]}


class HwDecodeTest(unittest.TestCase):
    def test_hw_decode_args(self):
        dev = os.path.join(TMP, "renderD128")
        open(dev, "w").close()
        self.assertEqual(fw.hw_decode_args({"name": "qsv", "device": dev}), ["-hwaccel", "vaapi", "-hwaccel_device", dev])
        self.assertEqual(fw.hw_decode_args({"name": "nvenc"}), ["-hwaccel", "cuda"])
        self.assertEqual(fw.hw_decode_args({"name": "cpu"}), [])
        self.assertEqual(fw.hw_decode_args({"name": "qsv", "device": dev + "-없음"}), [])
        plan = fw.encode_plan(HEVC, ".mkv", 720, "s.srt", {"name": "qsv", "device": dev})
        self.assertEqual(plan.pre[:4], ["-hwaccel", "vaapi", "-hwaccel_device", dev])   # 입력 앞 (-i 전)
        self.assertIn("-init_hw_device", plan.pre)
        off = fw.encode_plan(HEVC, ".mkv", 720, "s.srt", {"name": "qsv", "device": dev, "hw_decode": False})
        self.assertNotIn("-hwaccel", off.pre)
        cpu = fw.encode_plan(HEVC, ".mkv", 720, None, {"name": "cpu"})
        self.assertNotIn("-hwaccel", cpu.pre)


class PrioritySettingTest(unittest.TestCase):
    def test_settings(self):
        try:
            from tgup import plex_to_tg as m
        except ImportError:
            self.skipTest("aiohttp 없음")
        st = m.clean_settings({"encode_priority": "normal", "hw_decode": False})
        self.assertEqual((st["encode_priority"], st["hw_decode"]), ("normal", False))
        st = m.clean_settings({"encode_priority": "realtime"})
        self.assertEqual((st["encode_priority"], st["hw_decode"]), ("low", True))
        self.assertEqual(m.ENCODE_NICE, {"low": 19, "normal": 10})


if __name__ == "__main__":
    unittest.main()
