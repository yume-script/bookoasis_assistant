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


class DispatchTest(unittest.TestCase):
    def test_unknown_and_bad_names(self):
        svc = service.Service()
        self.assertFalse(svc.dispatch("nope", {})["success"])
        self.assertFalse(svc.dispatch("__init__", {})["success"])


if __name__ == "__main__":
    unittest.main()
