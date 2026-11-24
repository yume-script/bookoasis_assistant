# -*- coding: utf-8 -*-
"""인코딩 결과 남겨 두기: 서버를 다시 켜도(업데이트 등) 같은 항목을 처음부터 다시 인코딩하지 않는다 (Mirror._encode_burn)"""
import asyncio
import os
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="enccache-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class EncCacheTest(unittest.TestCase):
    def test_reuse_after_restart_and_drop_after_upload(self):
        from tgup import compat, folder_watch, plex_to_tg as m
        compat.DATA_DIR = tempfile.mkdtemp(prefix="enccache-data-")
        data = compat.load()
        data["plex_to_tg"] = m.clean_settings({"rules": [{"id": "r1", "kind": "folder", "folder": "/tmp", "tg": "tg", "channel": "-1"}]})
        compat.save(data)
        work = tempfile.mkdtemp(prefix="enccache-work-")
        src = os.path.join(work, "a.mkv")
        with open(src, "wb") as f:
            f.write(b"x" * 1000)
        runs = []

        def mirror():
            mir = m.Mirror(None, None, lambda *a: None, None)

            async def run(local, make, out, duration, title, tmp, burn_name):
                runs.append(title)
                with open(out, "wb") as f:
                    f.write(b"encoded")
                return folder_watch.Plan(["-c:v", "libx264"], ["H.264로 인코딩"], (), "cpu"), False, ""
            mir._encode_burn_run = run
            return mir

        async def go(mir, out):
            lane = m.Lane("")
            m._LANE.set(lane)
            lane.current_job = {"rule": "r1", "key": "a.mkv"}
            return await mir._encode_burn(src, None, out, 60, "제목", work, None)
        out1 = os.path.join(work, "o1.mp4")
        plan, burned, why = asyncio.run(go(mirror(), out1))
        self.assertEqual(runs, ["제목"])
        out2 = os.path.join(work, "o2.mp4")                       # 서버를 다시 켠 뒤 (새 Mirror, 새 임시 폴더)
        plan2, burned2, _ = asyncio.run(go(mirror(), out2))
        self.assertEqual(runs, ["제목"])                          # 다시 인코딩하지 않음
        with open(out2, "rb") as f:
            self.assertEqual(f.read(), b"encoded")
        self.assertEqual((list(plan2[1]), plan2.encoder, burned2), (["H.264로 인코딩"], "cpu", False))
        self.assertTrue(plan2)
        m.enc_cache_drop("r1", "a.mkv")                          # 다 올리면 지움 -> 다음엔 다시 인코딩
        asyncio.run(go(mirror(), os.path.join(work, "o3.mp4")))
        self.assertEqual(len(runs), 2)
        with open(src, "ab") as f:                                # 원본이 바뀌면(크기) 다른 결과
            f.write(b"y")
        asyncio.run(go(mirror(), os.path.join(work, "o4.mp4")))
        self.assertEqual(len(runs), 3)
        for name in os.listdir(m._enc_dir()):                     # 오래된 것 정리
            os.utime(os.path.join(m._enc_dir(), name), (time.time() - 5 * 86400,) * 2)
        self.assertGreater(m.enc_cache_sweep(), 0)
        self.assertEqual(os.listdir(m._enc_dir()), [])


if __name__ == "__main__":
    unittest.main()
