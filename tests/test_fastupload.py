# -*- coding: utf-8 -*-
"""빠른 업로드 (tgup/fastupload.py): 512KB 조각을 여러 줄로 동시에 - 가짜 클라이언트로 조각을 모아 원본과 같은지"""
import asyncio
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import telethon  # noqa: F401
    HAVE_TELETHON = True
except ImportError:
    HAVE_TELETHON = False


@unittest.skipUnless(HAVE_TELETHON, "telethon 없음")
class FastUploadTest(unittest.TestCase):
    def run_upload(self, size, conns=4, fail_once=None):
        from tgup import fastupload
        path = os.path.join(tempfile.mkdtemp(prefix="fu-"), "v.mp4")
        data = os.urandom(size)
        with open(path, "wb") as f:
            f.write(data)
        got, inflight, peak, failed = {}, [0], [0], set()

        class Client:   # 연결을 더 열지 못함(세션 없음) -> 이 연결에 겹쳐 보냄
            async def __call__(self, req):
                inflight[0] += 1
                peak[0] = max(peak[0], inflight[0])
                await asyncio.sleep(0.01)
                inflight[0] -= 1
                if fail_once is not None and req.file_part == fail_once and fail_once not in failed:
                    failed.add(fail_once)
                    raise ConnectionError("끊김")
                got[req.file_part] = (req.file_id, req.bytes, getattr(req, "file_total_parts", None))
                return True
        prog = []
        handle = asyncio.run(fastupload.upload(Client(), path, conns, lambda d, t: prog.append((d, t))))
        return handle, got, data, peak[0], prog

    def test_big_file_parallel(self):
        from telethon.tl.types import InputFileBig
        handle, got, data, peak, prog = self.run_upload(11 * 1024 * 1024 + 5)
        self.assertIsInstance(handle, InputFileBig)
        self.assertEqual(handle.parts, 23)                                   # 512KB 조각
        self.assertEqual(b"".join(got[i][1] for i in range(handle.parts)), data)
        self.assertEqual({v[0] for v in got.values()}, {handle.id})
        self.assertEqual({v[2] for v in got.values()}, {23})
        self.assertEqual(peak, 4)                                            # 동시에 4개
        self.assertEqual(prog[-1], (len(data), len(data)))

    def test_small_file_and_retry(self):
        from telethon.tl.types import InputFile
        handle, got, data, peak, _ = self.run_upload(1024 * 1024 + 1, conns=2, fail_once=1)
        self.assertIsInstance(handle, InputFile)
        self.assertEqual(handle.parts, 3)
        self.assertEqual(b"".join(got[i][1] for i in range(3)), data)       # 끊긴 조각도 다시 올림

    def test_one_connection(self):
        _h, _g, _d, peak, _ = self.run_upload(2 * 1024 * 1024, conns=1)
        self.assertEqual(peak, 1)


if __name__ == "__main__":
    unittest.main()
