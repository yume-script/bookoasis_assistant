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
        from tgup import compat, notify, service
        cls.compat, cls.service = compat, service
        notify.CHECK_SEC = 0.2   # 알림 확인을 빨리
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

    def test_send_files(self):
        """파일 골라 보내기: 규칙 폴더 안을 보고(동영상만, 하위 폴더), 고른 파일을 진행 목록에 (폴더 밖은 막음)"""
        api_post, api_get, ApiError = self.service.api_post, self.service.api_get, self.service.ApiError
        from tgup import plex_to_tg
        self.assertEqual(plex_to_tg.clean_key("/a//b/./c.mkv"), "a/b/c.mkv")
        self.assertEqual(plex_to_tg.clean_key("a/../../etc/passwd"), "")
        self.assertEqual(plex_to_tg.clean_key("gdrive:x.mkv"), "")
        data = self.compat.load()
        data.pop("telegram", None)
        self.compat.save(data)
        folder = tempfile.mkdtemp(prefix="tgup-send-")
        try:
            os.makedirs(os.path.join(folder, "시즌1"))
            for rel in ("영화.mkv", "메모.txt", "시즌1/E01.mp4", ".숨김.mkv"):
                with open(os.path.join(folder, rel), "wb") as f:
                    f.write(b"x" * 10)
            res = api_post("/api/tgup/settings", {"rules": [
                {"kind": "folder", "folder": folder, "tg": "tg", "channel": "-100123", "channel_title": "채널"},
                {"kind": "music", "folder": folder, "tg": "tg", "channel": "-100124"}]})
            vid, mus = res["settings"]["rules"]
            top = api_get("/api/tgup/files", {"rule": vid["id"], "sub": ""})
            self.assertEqual((top["dirs"], [f["name"] for f in top["files"]]), (["시즌1"], ["영화.mkv"]))
            inner = api_get("/api/tgup/files", {"rule": vid["id"], "sub": "시즌1"})
            self.assertEqual([f["key"] for f in inner["files"]], ["시즌1/E01.mp4"])
            self.assertEqual(api_get("/api/tgup/files", {"rule": mus["id"], "sub": ""})["files"], [])   # 음악 규칙은 음악 파일만
            with self.assertRaises(ApiError):
                api_get("/api/tgup/files", {"rule": vid["id"], "sub": "../.."})
            with self.assertRaises(ApiError):
                api_post("/api/tgup/send", {"rule": vid["id"], "keys": ["메모.txt"]})   # 규칙이 올리지 않는 종류
            with self.assertRaises(ApiError):
                api_post("/api/tgup/send", {"rule": vid["id"], "keys": []})
            r = api_post("/api/tgup/send", {"rule": vid["id"], "keys": ["영화.mkv", "시즌1/E01.mp4"], "again": True})
            self.assertEqual(r["count"], 2)
            m = self.service.RUNNER.mirror
            jobs = [j for j in self.service.RUNNER.run(lambda: list(m.queue)) if j.get("rule") == vid["id"]]
            self.assertTrue(jobs and all(j.get("manual") and j.get("force") for j in jobs))   # (텔레그램 계정이 없어 줄에 남음)
            self.assertEqual(api_post("/api/tgup/send", {"rule": vid["id"], "keys": ["영화.mkv"]})["count"], 0)   # 이미 줄에 있음
            # MCP tgup_status (디스코드봇이 읽는 대기열): 진행 목록에 고른 두 파일, 채널 이름, 전화번호는 안 나옴
            import json as _json
            from gdw import mcp
            names = [t["name"] for t in mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, {"tgup": True}, None)[1]["result"]["tools"]]
            self.assertIn("tgup_status", names)
            code, reply = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "tgup_status", "arguments": {}}},
                                     {"tgup": True}, None)
            self.assertFalse(reply["result"]["isError"], reply)
            got = _json.loads(reply["result"]["content"][0]["text"])
            self.assertEqual(got["queue_total"], 2)
            self.assertIn("영화", {q["title"] for q in got["queue"]})
            self.assertEqual({q["channel"] for q in got["queue"]}, {"채널"})
            # 설정 도구 (다운로드 에이전트): 공통 칸·규칙 칸 바꾸기, 없는 칸·규칙은 오류, 규칙은 지우지 않음
            res = mcp.tgup_set_settings({"encode_slots": 2, "hours": "1-7"}, [{"id": vid["id"], "height": 1080, "wait_min": 60}])
            self.assertEqual(res["changed"]["encode_slots"], {"before": 1, "after": 2})
            st2 = mcp.tgup_settings()
            r0 = next(r for r in st2["rules"] if r["id"] == vid["id"])
            self.assertEqual((st2["hours"], r0["height"], r0["wait_min"], len(st2["rules"])), ("1-7", 1080, 60, 2))
            self.assertEqual(next(r for r in st2["rules"] if r["id"] == mus["id"])["media"], "music")   # 음악 규칙은 그대로
            res = mcp.tgup_set_settings({"encode_priority": "high"})   # (봇 채우기 운영: 재생 중 low ↔ 한가할 때 high)
            self.assertEqual((res["changed"]["encode_priority"]["after"], mcp.tgup_settings()["encode_priority"]), ("high", "high"))
            with self.assertRaises(mcp.ToolError):
                mcp.tgup_set_settings({"rules": []})
            with self.assertRaises(mcp.ToolError):
                mcp.tgup_set_settings(None, [{"id": "없음", "enabled": False}])
            with self.assertRaises(mcp.ToolError):
                mcp.tgup_set_settings(None, [{"id": vid["id"], "folder": "/etc"}])
        finally:
            api_post("/api/tgup/item", {"action": "cancel_all"})
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

    def test_many_accounts(self):
        """텔레그램 계정 여러 개: 첫 계정(tg)은 예전 세션 그대로, 더한 계정은 따로 세션 파일, 규칙이 쓰는 계정은 못 뺌"""
        from tgup import tgaccount
        api_post, api_get, ApiError = self.service.api_post, self.service.api_get, self.service.ApiError
        data = self.compat.load()
        data.pop("telegram", None)   # API 값이 없으면 텔레그램에 붙지 않는다
        data.pop("accounts", None)
        self.compat.save(data)
        self.assertEqual([a["id"] for a in tgaccount.accounts()], ["tg"])
        new = api_post("/api/tgup/account", {"action": "add", "name": "부계정"})["id"]
        self.assertEqual(new, "tg2")
        api_post("/api/tgup/account", {"action": "rename", "account": new, "name": "두 번째"})
        got = api_get("/api/tgup", {})
        self.assertEqual([(a["id"], a["title"]) for a in got["accounts"]][1], ("tg2", "두 번째"))
        self.assertTrue(all(not a["authorized"] for a in got["accounts"]))
        acc1, acc2 = self.service.RUNNER.get_account("tg"), self.service.RUNNER.get_account(new)
        self.assertTrue(acc1.session_path.endswith("/telegram.session"))           # 예전 계정 그대로
        self.assertTrue(acc2.session_path.endswith("/telegram_tg2.session"))
        self.assertNotEqual(acc1.peers_path, acc2.peers_path)
        folder = tempfile.mkdtemp(prefix="tgup-folder-")
        try:
            api_post("/api/tgup/settings", {"rules": [{"kind": "folder", "folder": folder, "tg": new, "channel": "-1001", "channel_title": "B"}]})
            with self.assertRaises(ApiError):   # 이 계정으로 올리는 규칙이 있음
                api_post("/api/tgup/account", {"action": "remove", "account": new})
            api_post("/api/tgup/settings", {"rules": []})
            api_post("/api/tgup/account", {"action": "remove", "account": new})
            self.assertEqual([a["id"] for a in tgaccount.accounts()], ["tg"])
            with self.assertRaises(ApiError):   # 첫 계정은 못 뺌
                api_post("/api/tgup/account", {"action": "remove", "account": "tg"})
            with self.assertRaises(ApiError):   # 없는 계정
                api_post("/api/tgup/account", {"action": "send_code", "account": "tg9"})
            with self.assertRaises(tgaccount.TgError):   # 지운 계정을 쓰는 규칙이 올리려 하면
                self.service.RUNNER.get_account("tg7")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_discord_notify(self):
        import time
        from aiohttp import web
        from tgup import notify, plex_to_tg
        got = []

        async def hook(request):
            got.append(await request.json())
            return web.Response(status=204)

        async def serve():
            app = web.Application()
            app.router.add_post("/hook", hook)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "127.0.0.1", 0)
            await site.start()
            return runner, site._server.sockets[0].getsockname()[1]
        runner, port = self.service.RUNNER.call(serve())
        try:
            with self.assertRaises(ValueError):   # 디스코드 웹훅 주소가 아님
                notify.clean({"webhook": "http://example.com/x"}, {})
            data = self.compat.load()
            data["notify"] = {"webhook": f"http://127.0.0.1:{port}/hook", "ok": True, "fail": True, "skip": False}
            self.compat.save(data)
            st = plex_to_tg.load_state()
            st["history"] = [{"title": "건너뛴 것", "ok": False, "note": "건너뜀: 이미 올린 파일", "at": int(time.time()), "key": "s"},
                             {"title": "영화 (2026)", "ok": True, "note": "720p로 줄임", "at": int(time.time()), "key": "a",
                              "subs": "자막 입혀 인코딩", "channel": "채널"},
                             *st.get("history", [])]
            plex_to_tg.save_state(st)
            for _ in range(50):
                if got:
                    break
                time.sleep(0.1)
            time.sleep(0.5)
            self.assertEqual(len(got), 1)   # 건너뜀은 끔
            emb = got[0]["embeds"][0]
            self.assertEqual(emb["description"], "영화 (2026)")
            self.assertIn("올림", emb["title"])
            # 시험 알림 (화면의 [시험 알림 보내기]) - 디스코드 주소가 아니면 저장·시험 모두 400
            with self.assertRaises(self.service.ApiError):
                self.service.api_post("/api/tgup/notify", {"action": "test", "webhook": f"http://127.0.0.1:{port}/hook"})
        finally:
            self.service.RUNNER.call(runner.cleanup())

    def test_queue_kept_after_restart(self):
        """올릴 차례 목록은 data/tgup/plex_to_tg_queue.json에 남아 다시 켜도 이어 간다 (지운 규칙의 것은 버림)"""
        from tgup import plex_to_tg
        folder = tempfile.mkdtemp(prefix="tgup-folder-")
        try:
            res = self.service.api_post("/api/tgup/settings", {"rules": [{"kind": "folder", "folder": folder, "tg": "tg", "channel": "-100123"}]})
            rid = res["settings"]["rules"][0]["id"]
            plex_to_tg.save_queue([{"rule": rid, "key": folder + "/a.mkv", "title": "a"}, {"rule": "gone", "key": "x", "title": "x"}])
            self.assertTrue(os.path.exists(os.path.join(self.data, "plex_to_tg_queue.json")))
            self.assertEqual([j["title"] for j in plex_to_tg.load_queue()], ["a"])
        finally:
            plex_to_tg.save_queue([])
            shutil.rmtree(folder, ignore_errors=True)

    def test_folder_list(self):
        res = self.service.api_get("/api/tgup/folders", {"path": ROOT})
        self.assertIn("tgup", res["dirs"])
        with self.assertRaises(self.service.ApiError):
            self.service.api_get("/api/tgup/없는주소", {})


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class SourceOfflineTest(unittest.TestCase):
    """원본 드라이브가 끊긴 오류(Windows WinError 1005 등)는 실패로 세지 않는다"""

    @unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
    def test_detect(self):
        import errno as E
        from tgup import plex_to_tg as m
        e = OSError(None, "볼륨에 인식된 파일 시스템이 없습니다", "M:\\GDRIVE\\VIDEO\\방송중\\라프텔 애니메이션")
        e.winerror = 1005
        self.assertEqual(m.drive_of(m.source_offline(e)), "M:")
        self.assertEqual(m.source_offline(OSError(E.ENOTCONN, "Transport endpoint is not connected", "/mnt/gdrive/a.mkv")), "/mnt/gdrive/a.mkv")
        self.assertEqual(m.drive_of("/mnt/gdrive/VIDEO/a.mkv"), "/mnt/gdrive")
        wrapped = RuntimeError("복사 실패: [WinError 1005] 볼륨에 인식된 파일 시스템이 없습니다: 'M:\\A\\b'")
        self.assertEqual(m.drive_of(m.source_offline(wrapped)), "M:")
        try:
            try:
                raise e
            except OSError as inner:
                raise ValueError("감쌈") from inner
        except ValueError as outer:
            self.assertIsNotNone(m.source_offline(outer))
        self.assertIsNone(m.source_offline(FileNotFoundError(E.ENOENT, "없음", "/x/a.mkv")))   # 파일 하나 없는 건 끊김이 아님
        self.assertIsNone(m.source_offline(ValueError("ffmpeg 오류")))


class WinFspPathTest(unittest.TestCase):
    """Windows rclone/WinFsp 드라이브: realpath가 WinError 1005로 실패해도 파일 경로를 만들고, FUSE-rclone은 네트워크 드라이브로"""

    @unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
    def test_realpath_fallback_keeps_escape_check(self):
        from tgup import folder_watch as fw
        folder = tempfile.mkdtemp(prefix="tgup-winfsp-")
        orig = os.path.realpath

        def broken(p, *a, **k):
            e = OSError(None, "볼륨에 인식된 파일 시스템이 없습니다", p)
            e.winerror = 1005
            raise e
        os.path.realpath = broken
        try:
            got = fw.local_path(folder, os.path.join("방송중", "라프텔 애니메이션", "a.mp4"))
            self.assertEqual(got, os.path.join(folder, "방송중", "라프텔 애니메이션", "a.mp4"))
            for bad in ("../x.mp4", os.path.join("a", "..", "..", "x.mp4"), "/etc/passwd"):
                with self.assertRaises(fw.FolderError):
                    fw.local_path(folder, bad)
            with self.assertRaises(fw.FolderError):   # 이름이 겹치는 옆 폴더 (folder + "x")
                fw.local_path(folder, "../" + os.path.basename(folder) + "x/a.mp4")
        finally:
            os.path.realpath = orig
            shutil.rmtree(folder, ignore_errors=True)

    @unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
    def test_fuse_rclone_is_network(self):
        import ctypes
        from tgup import folder_watch as fw

        class K32:
            def __init__(self, kind, fs):
                self.kind, self.fs = kind, fs

            def GetDriveTypeW(self, root):
                return self.kind

            def GetVolumeInformationW(self, root, a, b, c, d, e, buf, n):
                buf.value = self.fs
                return 1

        class WinDLL:
            kernel32 = None
        had = hasattr(ctypes, "windll")
        old = getattr(ctypes, "windll", None)
        try:
            for kind, fs, want in ((3, "FUSE-rclone", True), (4, "NTFS", True), (3, "NTFS", False)):
                WinDLL.kernel32 = K32(kind, fs)
                ctypes.windll = WinDLL
                self.assertEqual(fw._windows_network("M:\\GDRIVE\\VIDEO\\a.mp4"), want, (kind, fs))
        finally:
            if had:
                ctypes.windll = old
            else:
                del ctypes.windll


class ResumePartsTest(unittest.TestCase):
    """나눠 올리다 서버를 다시 켜면 다 올린 조각 다음부터 이어 올린다 (영상만 올라가고 자막 전에 멈춘 조각은 지우고 그 조각부터)"""

    @unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
    def test_resume(self):
        import asyncio
        import types
        from tgup import compat, plex_to_tg as m
        if "telethon.tl.types" not in sys.modules:
            try:
                import telethon.tl.types  # noqa: F401
            except ImportError:
                ty = types.ModuleType("telethon.tl.types")
                ty.DocumentAttributeFilename = ty.DocumentAttributeVideo = lambda *a, **k: None
                sys.modules.update({"telethon": types.ModuleType("telethon"), "telethon.tl": types.ModuleType("telethon.tl"),
                                    "telethon.tl.types": ty})
        data = tempfile.mkdtemp(prefix="tgup-resume-")
        old_dir, compat.DATA_DIR = compat.DATA_DIR, data
        self.addCleanup(setattr, compat, "DATA_DIR", old_dir)

        class Client:
            def __init__(self, base, fail_at=None):
                self.n, self.sent, self.deleted, self.fail_at = base, [], [], fail_at

            async def send_file(self, peer, path, **kw):
                if os.path.basename(path) == self.fail_at:
                    raise asyncio.CancelledError()   # 서버 다시 켜기
                self.n += 1
                self.sent.append(os.path.basename(path))
                return types.SimpleNamespace(id=self.n)

            async def delete_messages(self, peer, ids):
                self.deleted += list(ids)

        async def run():
            mir = m.Mirror(None, None, lambda *a: None, None)
            lane = m.Lane("tg")
            m._LANE.set(lane)
            pieces = []
            for i in range(3):
                p = os.path.join(data, f"v_{i}.mp4")
                with open(p, "wb") as f:
                    f.write(b"x")
                pieces.append((p, i * 10, 10))
            sub = os.path.join(data, "sub.srt")
            with open(sub, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:29,000\nhi\n")
            lane.current_job = {"rule": "r1", "key": "K", "tg": "tg"}
            c1 = Client(100, fail_at="cut2_sub.srt")   # 2번째 조각의 영상은 올라갔고 자막 전에 멈춤
            with self.assertRaises(asyncio.CancelledError):
                await mir._send_pieces(c1, None, pieces, "v.mp4", "제목", 1, 1, None, [(sub, "ko", "srt")], "t", data, [])
            lane.resume = mir._resumable({"id": "r1"}, "K")
            self.assertEqual((lane.resume["n"], lane.resume["done"], lane.resume["cur"]), (3, 1, [103]))
            c2, msgs = Client(200), []
            await mir._send_pieces(c2, None, pieces, "v.mp4", "제목", 1, 1, None, [(sub, "ko", "srt")], "t", data, msgs)
            self.assertEqual(c2.sent, ["v_1.mp4", "cut2_sub.srt", "v_2.mp4", "cut3_sub.srt"])   # 1번 조각은 다시 안 올림
            self.assertEqual(c2.deleted, [103])                                                 # 반쪽 조각만 지움
            self.assertEqual(msgs, [101, 201, 203])
            # 다르게 나뉘면(조각 수가 다름) 올려 둔 것을 지우고 처음부터
            lane.resume = {"n": 4, "done": 2, "vids": [1, 2], "cur": []}
            st = m.load_state()
            st["rules"]["r1"]["sending"]["K"] = [1, 2]
            m.save_state(st)
            c3 = Client(300)
            await mir._send_pieces(c3, None, pieces, "v.mp4", "제목", 1, 1, None, [], "t", data, [])
            self.assertEqual((c3.sent, c3.deleted), (["v_0.mp4", "v_1.mp4", "v_2.mp4"], [1, 2]))
        asyncio.run(run())
        shutil.rmtree(data, ignore_errors=True)


class ChannelIndexTest(unittest.TestCase):
    """채널 중복 확인: 채널의 영상 메시지를 읽어 두고 같은 파일 이름·같은 회차를 찾는다 (처음엔 전부, 그 뒤엔 새 것만)"""

    def test_refresh_and_lookup(self):
        import asyncio
        from types import SimpleNamespace as NS
        from tgup import compat, plex_to_tg, tgaccount
        compat.DATA_DIR = tempfile.mkdtemp(prefix="tgup-idx-")
        tgaccount._INDEX.clear()

        def video(mid, name, cap=""):
            return NS(id=mid, message=cap, document=NS(mime_type="video/mp4", attributes=[NS(file_name=name)]))
        msgs = [video(3, "무빙.S01E02.1080p-ST_0000.mp4", "무빙 S01E02"), NS(id=2, message="글", document=None),
                video(1, "Some.Movie.2024.mkv", "Some Movie (2024)")]
        calls = []

        class Client:
            async def iter_messages(self, peer, min_id=0, limit=None):
                calls.append(min_id)
                for m in msgs:
                    if m.id > min_id:
                        yield m

        class Acc:
            async def authorized_client(self):
                return Client()

            async def peer(self, ch):
                return ch

        asyncio.run(tgaccount.refresh_channel(Acc(), -100))
        self.assertEqual(tgaccount.channel_file("tg", -100, "Some.Movie.2024.mp4"), "Some Movie (2024)")
        self.assertEqual(tgaccount.channel_file("tg", -100, "Other.mp4"), "")
        key = plex_to_tg.episode_key({"show": "무빙", "season": 1, "episode": 2, "name": "무빙 S01E02", "filename": ""})
        self.assertEqual(tgaccount.channel_episode("tg", -100, *key), "무빙 S01E02")
        # 새 메시지만 읽는다 (5분 안이면 다시 읽지 않음)
        msgs.insert(0, video(4, "무빙.S01E03.mp4"))
        tgaccount._INDEX[100]["at"] = 0
        asyncio.run(tgaccount.refresh_channel(Acc(), -100))
        self.assertEqual(calls, [0, 3])
        self.assertTrue(tgaccount.channel_file("tg2", -100, "무빙.S01E03.mkv"))
        # 다른 사람이 나눠 올린 것(.part1 / CD2 / (1 of 2))도 같은 파일 이름으로, 이름 가운데의 Part 1(작품 이름)은 그대로
        msgs.insert(0, video(5, "Hope.2026.1080p-KyoGo.part1.mkv"))
        msgs.insert(0, video(6, "file_6.mp4", "인셉션 (2010) (1/2)"))
        tgaccount._INDEX[100]["at"] = 0
        asyncio.run(tgaccount.refresh_channel(Acc(), -100))
        self.assertTrue(tgaccount.channel_file("tg", -100, "Hope.2026.1080p-KyoGo.mkv"))
        self.assertTrue(tgaccount.channel_file("tg", -100, "Hope.2026.1080p-KyoGo_0001.mp4"))
        self.assertNotEqual(tgaccount.file_stem_key("Harry.Potter.Deathly.Hallows.Part.1.2010.mkv"),
                            tgaccount.file_stem_key("Harry.Potter.Deathly.Hallows.Part.2.2011.mkv"))
        # 영화: 작품 이름 + 연도 (파일 이름이 달라도 캡션 첫 줄로), 연도가 다르면 다른 영화
        nk = plex_to_tg._name_key
        self.assertEqual(tgaccount.channel_movie("tg", -100, nk("인셉션"), "2010"), "인셉션 (2010) (1/2)")
        self.assertEqual(tgaccount.channel_movie("tg", -100, nk("Some Movie"), "2024"), "Some Movie (2024)")
        self.assertEqual(tgaccount.channel_movie("tg", -100, nk("Some Movie"), "1999"), "")
        self.assertEqual(tgaccount.channel_movie("tg", -100, nk("무빙"), ""), "")


class TmdbFieldsTest(unittest.TestCase):
    def test_item_fields_tmdb(self):
        from tgup import plex_to_tg
        m = {"type": "movie", "title": "Inception", "year": 2010, "Guid": [{"id": "imdb://tt1375666"}, {"id": "tmdb://27205"}]}
        self.assertEqual(plex_to_tg.item_fields(m)["tmdb"], "movie:27205")
        self.assertEqual(plex_to_tg.item_fields({"type": "movie", "title": "X"})["tmdb"], "")


class SoftSubsTest(unittest.TestCase):
    def test_classify(self):
        from tgup import folder_watch as fw
        c = fw.classify_subs
        self.assertTrue(c([{"codec": "ass", "lang": "kor"}])["usable"])
        self.assertTrue(c([{"codec": "subrip", "lang": ""}])["usable"])              # 언어 표시 없는 글자 자막 (자막 팀 MKV)
        self.assertTrue(c([{"codec": "ass", "lang": "und", "title": "한국어"}])["usable"])
        self.assertTrue(c([{"codec": "ass", "lang": "eng", "title": "Korean"}])["usable"])   # 제목에 한국어
        r = c([{"codec": "subrip", "lang": "eng"}, {"codec": "ass", "lang": "jpn"}])
        self.assertFalse(r["usable"])
        self.assertEqual(r["why"], "영어·일본어 자막만")
        r = c([{"codec": "hdmv_pgs_subtitle", "lang": "kor"}])
        self.assertFalse(r["usable"])
        self.assertEqual(r["why"], "그림 자막(PGS)만")                              # 그림 자막은 텔레그램 자막 파일로 못 옮김
        r = c([{"codec": "ass", "lang": "kor", "forced": True}, {"codec": "ass", "lang": "", "title": "Signs & Songs"}])
        self.assertFalse(r["usable"])
        self.assertEqual(r["why"], "간판·노래 자막만")
        self.assertEqual(c([])["why"], "")
        info = {"streams": [{"codec_type": "video"}, {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "kor"},
                                                      "disposition": {"forced": 0}}]}
        self.assertTrue(c(fw.stream_tracks(info))["usable"])

    def test_fetch_head_sparse_with_tail(self):
        """원격 파일 앞부분 + 끝부분을 원래 자리에 (트랙 정보가 끝에 있는 mp4도 ffprobe가 읽게)"""
        import asyncio
        from tgup import folder_watch as fw
        data = bytes(range(256)) * 400   # 102400바이트
        calls = []

        async def run(*args, timeout=0):
            calls.append(args)
            a = list(args)
            off = int(a[a.index("--offset") + 1]) if "--offset" in a else 0
            cnt = int(a[a.index("--count") + 1])
            return 0, data[off:off + cnt], b""
        orig_run, orig_rc = fw._run, fw.rclone_path
        fw._run, fw.rclone_path = run, (lambda: "/usr/bin/rclone")
        try:
            dest = os.path.join(tempfile.mkdtemp(), "h.mp4")
            self.assertTrue(asyncio.run(fw.fetch_head("r:", "a/b.mp4", dest, count=1000, size=len(data))))
            with open(dest, "rb") as f:
                got = f.read()
            self.assertEqual(len(got), len(data))
            self.assertEqual(got[:1000], data[:1000])
            self.assertEqual(got[-1000:], data[-1000:])
            self.assertEqual(got[5000:6000], b"\0" * 1000)   # 가운데는 비움
        finally:
            fw._run, fw.rclone_path = orig_run, orig_rc
