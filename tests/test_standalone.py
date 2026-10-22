# -*- coding: utf-8 -*-
"""python3 -m unittest discover -s tests"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="gdw-test-")
os.environ["GDW_ENV_FILE"] = os.path.join(TMP, ".env")
os.environ["DATA_DIR"] = os.path.join(TMP, "data")

from gdw import bookoasis_db, config  # noqa: E402

config.ENV_PATH = os.environ["GDW_ENV_FILE"]
from gdw import service  # noqa: E402


class EnvFileTest(unittest.TestCase):
    def setUp(self):
        with open(config.ENV_PATH, "w", encoding="utf-8") as handle:
            handle.write('# 주석\nRCLONE_PATH=rclone\nWEBHOOK_TOKEN="a b#c"\nBOOKOASIS_URL=http://x:1 # 뒤 주석\n')

    def test_read_quotes_and_comments(self):
        data = config.read_env_file()
        self.assertEqual(data["WEBHOOK_TOKEN"], "a b#c")
        self.assertEqual(data["BOOKOASIS_URL"], "http://x:1")

    def test_save_keeps_other_lines(self):
        config.save_env({"RCLONE_PATH": "/usr/bin/rclone", "AUTO_START": "false", "WEBHOOK_TOKEN": 'q"t'})
        with open(config.ENV_PATH, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("# 주석\n", text)
        self.assertIn("RCLONE_PATH=/usr/bin/rclone\n", text)
        self.assertTrue(text.rstrip().endswith("AUTO_START=false"))
        self.assertEqual(config.read_env_file()["WEBHOOK_TOKEN"], 'q"t')
        self.assertEqual(os.environ["RCLONE_PATH"], "/usr/bin/rclone")

    def test_db_url_template(self):
        os.environ["BOOKOASIS_DB_URL"] = "mysql://u:p%40ss@h:3306/bo_{db_type}"
        os.environ["BOOKOASIS_DB_URL_VIDEO"] = "sqlite:////v.db"
        try:
            self.assertEqual(config.db_url("adult"), "mysql://u:p%40ss@h:3306/bo_adult")
            self.assertEqual(config.db_url("video"), "sqlite:////v.db")
            self.assertEqual(bookoasis_db.describe(config.db_url("adult")), "mysql://u:***@h:3306/bo_adult")
        finally:
            del os.environ["BOOKOASIS_DB_URL"], os.environ["BOOKOASIS_DB_URL_VIDEO"]


class LibrariesTest(unittest.TestCase):
    def test_sqlite_libraries_and_placeholder(self):
        path = os.path.join(TMP, "general.db")
        db = sqlite3.connect(path)
        db.executescript("DROP TABLE IF EXISTS libraries; CREATE TABLE libraries(id INTEGER PRIMARY KEY, name TEXT, "
                         "physical_path TEXT, rclone_rc_url TEXT, cron_schedule TEXT);"
                         "INSERT INTO libraries VALUES(7, '만화', '/mnt/a\n/mnt/b', 'http://rc:5572', '0 4 * * *');")
        db.commit()
        db.close()
        os.environ["BOOKOASIS_DB_URL"] = "sqlite:///" + os.path.join(TMP, "{db_type}.db")
        os.environ["BOOKOASIS_DB_TYPES"] = "general"
        try:
            libs = service.Service()._libraries(force=True)
            self.assertEqual(libs, [{"db_type": "general", "id": 7, "name": "만화", "roots": ["/mnt/a", "/mnt/b"],
                                     "rclone_rc_url": "http://rc:5572", "cron_schedule": "0 4 * * *"}])
            row = bookoasis_db.gateway("general").fetch_one("SELECT name FROM libraries WHERE id = %s", (7,))
            self.assertEqual(row["name"], "만화")
        finally:
            del os.environ["BOOKOASIS_DB_URL"], os.environ["BOOKOASIS_DB_TYPES"]

    def test_manual_file(self):
        os.makedirs(service.DATA_DIR, exist_ok=True)
        with open(config.libraries_file(), "w", encoding="utf-8") as handle:
            json.dump([{"name": "오디오", "db_type": "audiobook", "roots": "/mnt/audio"}], handle)
        libs = service.Service()._libraries(force=True)
        self.assertEqual(libs[0]["roots"], ["/mnt/audio"])
        self.assertEqual((libs[0]["db_type"], libs[0]["id"]), ("audiobook", 1))


class EnvEscapeTest(unittest.TestCase):
    def test_multiline_roundtrip(self):
        value = '[{"name":"NID_AUT","value":"a\\b"},\n{"x":"y\"z"}]'
        config.save_env({"WTM_NAVER_COOKIE_JSON": value})
        self.assertEqual(config.read_env_file()["WTM_NAVER_COOKIE_JSON"], value)
        with open(config.ENV_PATH, encoding="utf-8") as handle:
            self.assertEqual(sum(1 for line in handle if line.startswith("WTM_NAVER_COOKIE_JSON=")), 1)


class WebtoonHostTest(unittest.TestCase):
    def test_settings_split_env_and_json(self):
        from wtm import host
        host.save_settings({"PARALLEL_TITLES": 4, "DOWNLOAD_ROOT": "/mnt/webtoon", "KAKAO_COOKIE": "a=b; c=d"})
        with open(host.SETTINGS_PATH, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"PARALLEL_TITLES": 4})
        env = config.read_env_file()
        self.assertEqual(env["WTM_DOWNLOAD_ROOT"], "/mnt/webtoon")
        self.assertNotIn("WTM_KAKAO_COOKIE", env)  # 쿠키는 .env가 아니라 cookies/ 파일로
        with open(host.cookie_path("KAKAO_COOKIE"), encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), "a=b; c=d")
        cfg = host.load_settings()
        self.assertEqual((cfg["PARALLEL_TITLES"], cfg["DOWNLOAD_ROOT"], cfg["KAKAO_COOKIE"]), (4, "/mnt/webtoon", "a=b; c=d"))

    def test_question_mark_placeholder(self):
        path = os.path.join(TMP, "q.db")
        db = sqlite3.connect(path)
        db.executescript("DROP TABLE IF EXISTS books; CREATE TABLE books(library_id INT, series_name TEXT);"
                         "INSERT INTO books VALUES(1, 'A'), (2, 'B');")
        db.commit()
        db.close()
        gw = bookoasis_db.Gateway("general", "sqlite:///" + path)
        self.assertEqual(gw.fetch_all("SELECT series_name FROM books WHERE library_id = ?", (2,)), [{"series_name": "B"}])
        self.assertEqual(gw._sql.__func__(type("G", (), {"scheme": "mysql"})(), "x = ?"), "x = %s")


class HandoffTest(unittest.TestCase):
    def test_enqueue_inside_library_only(self):
        from gdw import handoff
        service._db().close()  # state.db 스키마
        service._write_json("runtime.json", {"buffer_seconds": 5, "libraries": [
            {"db_type": "general", "id": 1, "roots": ["/mnt/lib"]}]})
        self.assertTrue(handoff.enqueue("/mnt/lib/작품/1화.zip"))
        self.assertFalse(handoff.enqueue("/mnt/lib/작품/1화.zip"))  # 대기 중 중복
        self.assertFalse(handoff.enqueue("/mnt/other/1화.zip"))
        db = service._db()
        row = db.execute("SELECT root, action, item_type, status FROM event WHERE path=?", ("/mnt/lib/작품/1화.zip",)).fetchone()
        db.close()
        self.assertEqual(tuple(row), ("웹툰 다운로더", "create", "file", "pending"))


class TelegramUploadTest(unittest.TestCase):
    def test_only_selected_titles_in_episode_order(self):
        from wtm import host, state_store as ss, telegram_upload as tu
        root = os.path.join(TMP, "naver_dl")
        a, b = os.path.join(root, "작품A (111)"), os.path.join(root, "작품B (222)")
        for d in (a, b):
            os.makedirs(d, exist_ok=True)
        for n in ("작품A 0010화.zip", "작품A 0002화.zip", "kavita.yaml"):
            open(os.path.join(a, n), "w").close()
        open(os.path.join(b, "작품B 0001화.zip"), "w").close()
        host.save_settings({"DOWNLOAD_ROOT": root, "TELEGRAM_UPLOAD_CHAT_ID": "-1001", "NOTIFY_TELEGRAM_BOT_TOKEN": "tok",
                            "TELEGRAM_UPLOAD_BOT_TOKEN": "", "TELEGRAM_UPLOAD_MAX_MB": 9999})
        s = tu.settings()
        self.assertEqual((s["token"], s["api"], s["max_bytes"]), ("tok", tu.DEFAULT_API, 2000 * 1024 * 1024))
        ss.upsert_title({"111": {"title": "작품A"}, "222": {"title": "작품B"}})
        ss.flush_titles()
        self.assertFalse(tu.enqueue(os.path.join(b, "작품B 0002화.zip")))       # 📤를 켜지 않은 작품
        ss.upsert_title({"111": {"telegram_upload": True}})
        added, total, _ = tu.add_title("naver", "111", ss.get_title("111"))
        self.assertEqual((added, total), (2, 2))                                   # 회차 수 (작품 정보 yaml은 따로)
        self.assertTrue(tu.enqueue(os.path.join(a, "작품A 0011화.zip")))          # 켠 작품의 새 회차
        self.assertEqual(tu.add_title("naver", "111", ss.get_title("111"))[0], 0)  # 이미 대기열에 있는 것은 다시 안 넣음
        db = tu._db()
        order = [os.path.basename(r[0]) for r in db.execute("SELECT path FROM upload ORDER BY id")]
        db.close()
        self.assertEqual(order, ["kavita.yaml", "작품A 0002화.zip", "작품A 0010화.zip", "작품A 0011화.zip"])  # 작품 정보 먼저
        self.assertEqual(tu.upload_name(os.path.join(a, "kavita.yaml")), "작품A.yaml")   # 채널에는 '작품명.yaml'로
        self.assertEqual(tu.remove_title("naver", "111", ss.get_title("111")), 4)  # 끄면 대기 중인 것 취소
        self.assertEqual(tu.caption_for("/mnt/w/작품 이름 (1부)/작품 0001화.zip"), "#작품_이름_1부\n작품 0001화")


class MiniGameTest(unittest.TestCase):
    def test_bundle_and_covers(self):
        from mini import bundle
        games = bundle.menu()
        self.assertGreaterEqual(len(games), 12)
        self.assertTrue(all(g["id"] and g["name"] and not g["name"].startswith("🕹") for g in games))
        page = bundle.page()
        self.assertIn('data-module="mini"', page)
        self.assertIn("YmMiniGameHub", page)
        self.assertNotIn("/plugins/metadata/ym_mini_game/", page)  # 표지 경로는 이 서버의 games/covers/
        self.assertEqual(page.lower().count("</script>"), page.lower().count("<script"))
        self.assertIsNone(bundle.cover_path("../bundle.py"))
        covers = bundle.list_covers()
        if covers:
            self.assertTrue(os.path.isfile(bundle.cover_path(covers[0])))


class DispatchTest(unittest.TestCase):
    def test_unknown_and_bad_names(self):
        svc = service.Service()
        self.assertFalse(svc.dispatch("nope", {})["success"])
        self.assertFalse(svc.dispatch("__init__", {})["success"])


class AuthTest(unittest.TestCase):
    def test_session_cookie(self):
        from gdw import auth
        auth.save_users([])
        os.environ["WEB_PASSWORD"] = "old"
        try:
            self.assertTrue(auth.bootstrap_from_env())  # 예전 Basic 인증 비밀번호로 첫 관리자
        finally:
            os.environ.pop("WEB_PASSWORD")
        user = auth.verify_password("ADMIN", "old")
        self.assertTrue(user)
        self.assertIsNone(auth.verify_password("admin", "nope"))
        token = auth.make_token(user, remember=True)
        self.assertEqual(auth.user_from_token(token)["username"], "admin")
        self.assertIsNone(auth.user_from_token(token[:-2] + "xx"))
        auth.set_password("admin", "newpass1")  # 비밀번호를 바꾸면 기존 쿠키는 무효
        self.assertIsNone(auth.user_from_token(token))
        with self.assertRaises(auth.AuthError):
            auth.delete_user("admin")  # 마지막 사용자


class McpTest(unittest.TestCase):
    def test_protocol(self):
        from gdw import mcp
        os.environ["MCP_TOKEN"] = "gdw_test"
        try:
            self.assertTrue(mcp.authorized("Bearer gdw_test"))
            self.assertFalse(mcp.authorized("Bearer nope"))
        finally:
            os.environ.pop("MCP_TOKEN")
        mods = {"gdw": False, "wtm": False}
        code, reply = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-03-26"}}, mods, None)
        self.assertEqual((code, reply["result"]["protocolVersion"]), (200, "2025-03-26"))
        self.assertEqual(mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, mods, None), (202, None))
        self.assertEqual(mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, mods, None)[1]["result"]["tools"], [])
        names = [t["name"] for t in mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, {"gdw": True}, object())[1]["result"]["tools"]]
        self.assertIn("gdw_status", names)
        self.assertEqual(mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "gdw_status"}},
                                    mods, None)[1]["error"]["code"], -32602)  # 꺼진 모듈의 도구
        self.assertEqual(mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "nope"}, mods, None)[1]["error"]["code"], -32601)


class KakaoAccountsTest(unittest.TestCase):
    def test_accounts_and_blocks(self):
        os.environ.setdefault("WTM_HOST", "1")
        from wtm import kakao_api, kakao_pipeline as kp
        cfg = {"KAKAO_COOKIE": "a=1", "KAKAO_COOKIE_2": "b=2", "KAKAO_COOKIE_3": "a=1", "KAKAO_COOKIE_5": " "}
        self.assertEqual(kp.accounts(cfg), [(1, "a=1"), (2, "b=2")])  # 같은 쿠키·빈 칸은 빠짐
        t = {"last_ticket_at": 100, "ticket_at_acc": {"2": 200}}
        self.assertEqual((kp._ticket_at(t, 1), kp._ticket_at(t, 2), kp._ticket_at(t, 3)), (100, 200, 0))
        adult = {"adult": True, "adult_block_hashes": [kakao_api._cookie_hash("a=1")]}
        self.assertTrue(kp.adult_block_reason(cfg, adult))
        self.assertIsNone(kp.adult_block_reason_any(cfg, adult))  # 계정 2는 아직 시도 가능
        adult["adult_block_hash"] = kakao_api._cookie_hash("b=2")  # 예전 형식 필드도 읽음
        self.assertTrue(kp.adult_block_reason_any(cfg, adult))


class CookieFileTest(unittest.TestCase):
    def test_cookie_files(self):
        os.environ.setdefault("WTM_HOST", "1")
        from wtm import host
        config.save_env({"WTM_KAKAO_COOKIE_2": "old=1"})
        self.assertEqual(host.load_settings().get("KAKAO_COOKIE_2"), "old=1")  # 파일이 없으면 .env
        host.save_settings(dict(host.load_settings(), KAKAO_COOKIE_2='[{"name": "_kau", "value": "1"}]'))
        self.assertTrue(os.path.exists(host.cookie_path("KAKAO_COOKIE_2")))
        self.assertEqual(host.load_settings()["KAKAO_COOKIE_2"], '[{"name": "_kau", "value": "1"}]')
        self.assertEqual(config.read_env_file().get("WTM_KAKAO_COOKIE_2"), "")  # .env의 예전 값은 비움
        host.save_settings(dict(host.load_settings(), KAKAO_COOKIE_2=""))
        self.assertFalse(os.path.exists(host.cookie_path("KAKAO_COOKIE_2")))


if __name__ == "__main__":
    unittest.main()
