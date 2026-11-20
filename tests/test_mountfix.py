# -*- coding: utf-8 -*-
"""rclone mount 파일 하나만 못 읽을 때: vfs/forget -> 다시 -> 원격에서 직접 받기 (tgup/mountfix.py, Mirror._bring_local_safe)"""
import asyncio
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="mountfix-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False

from tgup import folder_watch, mountfix  # noqa: E402

VIDEO = {"streams": [{"codec_type": "video", "height": 720}], "format": {"duration": "60"}}


class FakeRc(http.server.BaseHTTPRequestHandler):
    calls = []
    vfses = ["gds2:"]

    def do_POST(self):
        body = urllib.parse.parse_qs(self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode())
        FakeRc.calls.append((self.path.strip("/"), {k: v[0] for k, v in body.items()}, self.headers.get("Authorization")))
        out = {"vfses": FakeRc.vfses} if self.path.endswith("vfs/list") else {"result": {}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class MountfixTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="mf-")
        self.mnt = os.path.join(self.d, "gds2")
        os.makedirs(os.path.join(self.mnt, "영화"))
        self.mounts = os.path.join(self.d, "mounts")
        with open(self.mounts, "w") as f:
            f.write(f"gds2: {self.mnt} fuse.rclone rw 0 0\n/dev/sda1 / ext4 rw 0 0\n")
        self.proc = os.path.join(self.d, "proc")
        os.environ.pop("RCLONE_RC_MAP", None)
        os.environ.pop("PLEX_RC_URL", None)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        os.environ.pop("RCLONE_RC_MAP", None)

    def _proc(self, pid, argv):
        os.makedirs(os.path.join(self.proc, str(pid)))
        with open(os.path.join(self.proc, str(pid), "cmdline"), "wb") as f:
            f.write(b"\0".join(a.encode() for a in argv) + b"\0")

    def test_mount_of(self):
        m = mountfix.mount_of(os.path.join(self.mnt, "영화", "a.mkv"), self.mounts)
        self.assertEqual((m["path"], m["remote"], m["rel"]), (self.mnt, "gds2:", "영화/a.mkv"))
        self.assertIsNone(mountfix.mount_of("/etc/hosts", self.mounts))

    def test_proc_rc_and_order(self):
        m = mountfix.mount_of(os.path.join(self.mnt, "a.mkv"), self.mounts)
        self._proc(10, ["/usr/bin/rclone", "mount", "gds2:", self.mnt, "--rc", "--rc-addr=0.0.0.0:5590",
                        "--rc-user", "u", "--rc-pass", "p"])
        self._proc(11, ["/usr/bin/rclone", "mount", "other:", "/mnt/other", "--rc"])   # 다른 마운트
        self._proc(12, ["/usr/bin/rclone", "mount", "gds2:", self.mnt])                # --rc 없음
        got = mountfix.proc_rc(m, self.proc)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "http://127.0.0.1:5590")
        self.assertTrue(got[0][1].startswith("Basic "))
        os.environ["RCLONE_RC_MAP"] = f"/mnt/x=http://1.1.1.1:1;{self.mnt}=http://a:b@127.0.0.1:5591"
        urls = [u for u, _ in mountfix.rc_candidates(m, self.proc)]
        self.assertEqual(urls, ["http://127.0.0.1:5590", "http://127.0.0.1:5591"])   # 프로세스 먼저, 그다음 RCLONE_RC_MAP

    def test_pick_fs(self):
        self.assertEqual(mountfix._pick_fs(["gds2:"], "gds2:"), "")
        self.assertEqual(mountfix._pick_fs(["a:", "gds2:"], "gds2:"), "gds2:")
        self.assertIsNone(mountfix._pick_fs(["a:", "b:"], "gds2:"))

    def test_forget_sync_calls_rc(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), FakeRc)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            FakeRc.calls, FakeRc.vfses = [], ["other:", "gds2:"]
            os.environ["RCLONE_RC_MAP"] = f"{self.mnt}=http://u:p@127.0.0.1:{srv.server_port}"
            ok, how = mountfix.forget_sync(os.path.join(self.mnt, "영화", "a.mkv"), self.mounts, self.proc)
            self.assertTrue(ok, how)
            cmds = [c[0] for c in FakeRc.calls]
            self.assertEqual(cmds, ["vfs/list", "vfs/forget", "vfs/refresh"])
            self.assertEqual(FakeRc.calls[1][1], {"file": "영화/a.mkv", "fs": "gds2:"})
            self.assertEqual(FakeRc.calls[2][1]["dir"], "영화")
            self.assertTrue(FakeRc.calls[1][2].startswith("Basic "))
            FakeRc.calls, FakeRc.vfses = [], ["a:", "b:"]   # 다른 마운트의 RC면 forget 안 함
            ok, how = mountfix.forget_sync(os.path.join(self.mnt, "a.mkv"), self.mounts, self.proc)
            self.assertFalse(ok)
            self.assertEqual([c[0] for c in FakeRc.calls], ["vfs/list"])
        finally:
            srv.shutdown()

    def test_forget_without_rc(self):
        ok, how = mountfix.forget_sync(os.path.join(self.mnt, "a.mkv"), self.mounts, self.proc)
        self.assertFalse(ok)
        self.assertIn("RC 주소", how)
        ok, _ = mountfix.forget_sync("/etc/hosts", self.mounts, self.proc)
        self.assertFalse(ok)


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class SafeReadTest(unittest.TestCase):
    """Mirror._bring_local_safe / _probe_safe - 마운트·RC·rclone은 가짜"""

    def setUp(self):
        from tgup import plex_to_tg as m
        self.m = m
        self.tmp = tempfile.mkdtemp(prefix="safe-")
        self.mir = m.Mirror(None, None, lambda *a: None, None)
        self.log = []
        self.saved = (mountfix.mount_of, mountfix.forget, mountfix.remote_copy, folder_watch.probe)
        self.good_after = 99      # 몇 번째 읽기부터 정상인지 (마운트)
        self.remote_ok = True
        self.reads = 0

        mountfix.mount_of = lambda p, *a: {"path": "/mnt/gds2", "remote": "gds2:", "rel": "a.mkv"} if p.startswith("/mnt/") else None

        async def forget(p):
            self.log.append("forget")
            return True, "ok"

        async def remote_copy(p, dest, progress=None):
            self.log.append("copyto")
            if not self.remote_ok:
                raise folder_watch.FolderError("rclone 실패")
            with open(dest, "w") as f:
                f.write("remote")
            return dest

        async def probe(p):
            if not os.path.exists(p):   # (가짜 마운트 경로 - 낡은 캐시)
                return {}
            with open(p) as f:
                return VIDEO if f.read() in ("remote", "good") else {}

        async def bring(src, subs, tmp, title):
            self.reads += 1
            self.log.append("read")
            dest = os.path.join(tmp, "src.mkv")
            with open(dest, "w") as f:
                f.write("good" if self.reads >= self.good_after else "stale")
            return dest, []
        mountfix.forget, mountfix.remote_copy = forget, remote_copy
        folder_watch.probe = probe
        self.mir._bring_local = bring

    def tearDown(self):
        mountfix.mount_of, mountfix.forget, mountfix.remote_copy, folder_watch.probe = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_safe(self):
        return asyncio.run(self.mir._bring_local_safe("/mnt/gds2/a.mkv", [], self.tmp, "t"))

    def test_first_read_ok(self):
        self.good_after = 1
        local, _subs, info, note = self.run_safe()
        self.assertEqual((self.log, note), (["read"], ""))
        self.assertTrue(info)

    def test_forget_then_ok(self):
        self.good_after = 2
        _l, _s, info, note = self.run_safe()
        self.assertEqual(self.log, ["read", "forget", "read"])
        self.assertIn("vfs/forget 후 정상", note)

    def test_fallback_remote_copy(self):
        local, _s, info, note = self.run_safe()
        self.assertEqual(self.log, ["read", "forget", "read", "copyto"])
        self.assertIn("원격에서 직접 받음", note)
        with open(local) as f:
            self.assertEqual(f.read(), "remote")

    def test_read_error_then_remote(self):
        async def bad(*a):
            self.log.append("read")
            raise RuntimeError("서버로 복사한 파일의 크기가 원본과 다릅니다")
        self.mir._bring_local = bad
        _l, _s, _i, note = self.run_safe()
        self.assertEqual(self.log, ["read", "forget", "read", "copyto"])
        self.assertIn("원격에서 직접 받음", note)

    def test_remote_also_fails(self):
        self.remote_ok = False
        with self.assertRaises(RuntimeError) as cm:
            self.run_safe()
        self.assertIn("원격으로도", str(cm.exception))

    def test_no_space_not_retried(self):
        async def full(*a):
            self.log.append("read")
            raise RuntimeError("서버 임시 폴더에 자리가 모자랍니다")
        self.mir._bring_local = full
        with self.assertRaises(RuntimeError):
            self.run_safe()
        self.assertEqual(self.log, ["read"])

    def test_probe_safe_music(self):
        path = os.path.join(self.tmp, "x")   # (가짜 마운트 경로는 /mnt/ 로 시작)
        self.log.clear()
        got = asyncio.run(self.mir._probe_safe("/mnt/gds2/a.flac", self.tmp, "t", "video"))
        self.assertEqual(self.log, ["forget", "copyto"])
        self.assertIn("원격에서 직접 받음", got[2])
        self.assertTrue(got[0].startswith(self.tmp))
        self.log.clear()
        got = asyncio.run(self.mir._probe_safe("/mnt/gds2/a.flac", self.tmp, "t", "video", fetch=False))
        self.assertEqual((self.log, got[2]), (["forget"], ""))
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
