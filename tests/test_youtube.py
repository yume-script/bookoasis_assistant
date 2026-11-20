# -*- coding: utf-8 -*-
"""텔레그램 자동 올리기 - 유튜브 규칙 (tgup/youtube.py, Mirror.add_youtube / upload_youtube). 유튜브·텔레그램에는 붙지 않는다 (가짜 yt-dlp)"""
import asyncio
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="yt-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False

from tgup import compat, youtube  # noqa: E402

# 가짜 yt-dlp: -o 틀대로 영상·정보·한국어 자막을 만들고 진행 줄을 찍는다 (재생목록은 id 두 개)
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if "--flat-playlist" in a:
    print("aaaaaaaaaaa"); print("bbbbbbbbbbb"); sys.exit(0)
if "fail" in a[-1]:
    print("ERROR: [youtube] fail: Video unavailable", file=sys.stderr); sys.exit(1)
out = a[a.index("-o") + 1]
vid = a[-1].split("v=")[-1]
base = out.replace(".%(ext)s", "")
open(base + ".mp4", "wb").write(b"x" * 1000)
json.dump({"id": vid, "title": "고양이 / 영상: 1편", "uploader": "냥채널", "upload_date": "20250102",
           "description": "설명입니다", "webpage_url": a[-1], "formats": [1, 2, 3]}, open(base + ".info.json", "w"))
open(base + ".ko.srt", "w").write("1\n00:00:01,000 --> 00:00:02,000\nhi\n")
print("yp:500/1000"); print("yp:1000/1000")
with open(os.environ["FAKE_ARGS"], "w") as f:
    json.dump(a, f)
'''


class ParseTest(unittest.TestCase):
    def test_video_id(self):
        v = "dQw4w9WgXcQ"
        for u in (f"https://www.youtube.com/watch?v={v}&t=10s", f"https://youtu.be/{v}?si=x", f"https://m.youtube.com/shorts/{v}",
                  f"https://www.youtube.com/live/{v}", f"https://www.youtube.com/embed/{v}", f"https://music.youtube.com/watch?v={v}&list=PLx"):
            self.assertEqual(youtube.video_id(u), v, u)
        for u in ("https://example.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=short", "nope"):
            self.assertEqual(youtube.video_id(u), "")
        self.assertEqual(youtube.playlist_id("https://www.youtube.com/playlist?list=PLabcdefghij123"), "PLabcdefghij123")
        self.assertEqual(youtube.split_urls("https://a.b/1\n https://a.b/1, https://a.b/2 글"), ["https://a.b/1", "https://a.b/2"])

    def test_fields_and_caption(self):
        from tgup.plex_to_tg import make_caption
        f = youtube.fields({"title": "제목", "uploader": "채널", "upload_date": "20240305", "webpage_url": "https://youtu.be/x",
                            "description": "가" * 700}, {})
        self.assertEqual((f["date"], f["year"]), ("2024-03-05", ""))
        self.assertTrue(f["summary"].endswith("…") and len(f["summary"]) == 601)
        cap = make_caption(youtube.YT_CAPTION, f)
        self.assertTrue(cap.startswith("제목\n\n📺 채널 · 2024-03-05\n🔗 https://youtu.be/x"))

    def test_fmt_select(self):
        self.assertIn("[height<=720]", youtube.fmt_select(720))
        self.assertNotIn("height", youtube.fmt_select(0))


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ytdl-")
        exe = os.path.join(self.d, "yt-dlp")
        with open(exe, "w") as f:
            f.write(FAKE.replace("#!/usr/bin/env python3", "#!" + sys.executable))
        os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
        os.environ["YTDLP_PATH"] = exe
        os.environ["FAKE_ARGS"] = os.path.join(self.d, "args.json")
        self.folder = os.path.join(self.d, "rule")

    def tearDown(self):
        os.environ.pop("YTDLP_PATH", None)
        shutil.rmtree(self.d, ignore_errors=True)

    def test_download_names_and_cleanup(self):
        key = "yt-AAAAAAAAAAA"
        youtube.save_request(self.folder, key, "https://www.youtube.com/watch?v=AAAAAAAAAAA")
        prog = []
        path = asyncio.run(youtube.download("https://www.youtube.com/watch?v=AAAAAAAAAAA", self.folder, key, 720, lambda d, t: prog.append((d, t))))
        self.assertEqual(os.path.basename(path), "고양이 _ 영상_ 1편 [AAAAAAAAAAA].mp4")
        self.assertTrue(os.path.exists(path[:-4] + ".ko.srt"))   # 자막도 같은 이름 (옆 자막으로 올라감)
        self.assertEqual(prog[-1], (1000, 1000))
        with open(os.environ["FAKE_ARGS"]) as f:
            args = json.load(f)
        self.assertIn("--merge-output-format", args)
        self.assertIn(youtube.fmt_select(720), args)
        self.assertEqual(youtube.find_file(self.folder, key), path)       # 다시 시도할 때는 받아 둔 것
        self.assertEqual(youtube.load_info(self.folder, key)["uploader"], "냥채널")
        youtube.cleanup(self.folder, key, path)
        self.assertEqual(os.listdir(self.folder), [])

    def test_download_error(self):
        with self.assertRaises(RuntimeError) as cm:
            asyncio.run(youtube.download("https://www.youtube.com/watch?v=fail", self.folder, "yt-fail", 720))
        self.assertIn("Video unavailable", str(cm.exception))

    def test_expand_playlist(self):
        got = asyncio.run(youtube.expand("https://www.youtube.com/playlist?list=PLabcdefghij123\nhttps://youtu.be/aaaaaaaaaaa"))
        self.assertEqual([v for v, _ in got], ["aaaaaaaaaaa", "bbbbbbbbbbb"])   # 같은 영상은 한 번
        with self.assertRaises(ValueError):
            asyncio.run(youtube.expand("https://example.com/x"))


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class MirrorYoutubeTest(DownloadTest):
    def setUp(self):
        super().setUp()
        from tgup import plex_to_tg as m
        self.m = m
        compat.DATA_DIR = os.path.join(self.d, "data")
        os.makedirs(compat.DATA_DIR)
        st = m.clean_settings({"rules": [{"id": "yt1", "kind": "youtube", "tg": "tg", "channel": "-100", "channel_title": "유튜브",
                                          "wait_subs": True, "height": 1080}]})
        self.rule = st["rules"][0]
        data = compat.load()
        data["plex_to_tg"] = st
        compat.save(data)

    def test_rule_settings(self):
        r = self.rule
        self.assertEqual((r["kind"], r["media"], r["wait_subs"], r["height"], r["section_title"]), ("folder", "youtube", False, 1080, "유튜브"))
        self.assertEqual(r["folder"], youtube.rule_folder("yt1"))
        self.assertEqual(r["caption"], youtube.YT_CAPTION)

    def test_add_and_upload(self):
        m = self.m
        mir = m.Mirror(None, None, lambda *a: None, None)
        mir.queue, mir.wake = [], lambda: None
        n, dup = asyncio.run(mir.add_youtube("yt1", "https://youtu.be/AAAAAAAAAAA https://www.youtube.com/watch?v=AAAAAAAAAAA"))
        self.assertEqual((n, dup, mir.queue[0]["key"]), (1, 0, "yt-AAAAAAAAAAA"))
        self.assertEqual(asyncio.run(mir.add_youtube("yt1", "https://youtu.be/AAAAAAAAAAA")), (0, 1))
        with self.assertRaises(ValueError):
            asyncio.run(mir.add_youtube("nope", "https://youtu.be/AAAAAAAAAAA"))
        calls = []

        async def fake_upload_file(rule, key, max_gb, test=False, extra_fields=None):
            calls.append((rule, key, extra_fields))
            self.assertTrue(os.path.exists(os.path.join(rule["folder"], key)))
            return "그대로 올림"
        mir.upload_file = fake_upload_file

        async def run():
            lane = m.Lane("tg")
            m._LANE.set(lane)
            lane.job = mir.queue[0]
            lane.current_job = {"rule": "yt1", "key": "yt-AAAAAAAAAAA", "tg": "tg"}
            return await mir.upload(self.rule, "yt-AAAAAAAAAAA", 2)
        note = asyncio.run(run())
        self.assertEqual(note, "그대로 올림")
        rule, key, f = calls[0]
        self.assertEqual(key, "고양이 _ 영상_ 1편 [AAAAAAAAAAA].mp4")
        self.assertFalse(rule["wait_subs"])
        self.assertEqual((f["name"], f["uploader"], f["date"]), ("고양이 / 영상: 1편", "냥채널", "2025-01-02"))
        self.assertEqual(mir.queue[0]["title"], "고양이 / 영상: 1편")   # 진행 목록·기록에 영상 제목
        self.assertEqual(os.listdir(self.rule["folder"]), [])         # 다 올렸으니 받은 것은 지움

    def test_folder_scan_and_send_skip_youtube(self):
        mir = self.m.Mirror(None, None, lambda *a: None, None)
        with self.assertRaises(ValueError):
            mir.send_files("yt1", ["a.mp4"])


if __name__ == "__main__":
    unittest.main()
