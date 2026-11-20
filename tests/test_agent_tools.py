# -*- coding: utf-8 -*-
"""MCP 설정 도구 (디스코드봇 다운로드 에이전트가 쓰는 wtm_settings·wtm_set_settings) - 따로 된 프로세스에서 (DATA_DIR이 모듈을 불러올 때 정해져서)"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from gdw import mcp
out = {}
st = mcp.wtm_settings()
keys = {f["key"]: f for f in st["fields"]}
out["has"] = all(k in keys for k in ("SCHEDULE_CRON", "PARALLEL_TITLES", "FAST_MODE", "WAITFREE_DAILY_PLAN"))
out["locked"] = [k for k in ("KAKAO_COOKIE", "DOWNLOAD_ROOT", "DISCORD_WEBHOOK_URL") if keys[k].get("locked")]
out["secret_hidden"] = "value" not in keys["KAKAO_COOKIE"]
out["set"] = mcp.wtm_set_settings({"PARALLEL_TITLES": 3, "SCHEDULE_CRON": "0 */2 * * *"})["changed"]
errs = []
for bad in ({"KAKAO_COOKIE": "x"}, {"NOPE": 1}, {"SCHEDULE_CRON": "아무거나"}):
    try:
        mcp.wtm_set_settings(bad)
    except mcp.ToolError as e:
        errs.append(str(e)[:40])
out["errors"] = len(errs)
print(json.dumps(out, ensure_ascii=False))
"""


class AgentToolsTest(unittest.TestCase):
    def test_wtm_settings_tools(self):
        tmp = tempfile.mkdtemp(prefix="agent-tools-")
        env = dict(os.environ, GDW_ENV_FILE=os.path.join(tmp, ".env"), DATA_DIR=os.path.join(tmp, "data"), WTM_WORKER_MODE="0")
        r = subprocess.run([sys.executable, "-c", SCRIPT, ROOT], env=env, cwd=tmp, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out["has"])
        self.assertEqual(out["locked"], ["KAKAO_COOKIE", "DOWNLOAD_ROOT", "DISCORD_WEBHOOK_URL"])
        self.assertTrue(out["secret_hidden"])
        self.assertEqual(out["set"], {"PARALLEL_TITLES": {"before": 2, "after": 3},
                                      "SCHEDULE_CRON": {"before": "0 */4 * * *", "after": "0 */2 * * *"}})
        self.assertEqual(out["errors"], 3)   # 쿠키(잠김)·없는 칸·잘못된 crontab


if __name__ == "__main__":
    unittest.main()
