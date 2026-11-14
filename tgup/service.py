# -*- coding: utf-8 -*-
"""텔레그램 자동 올리기를 이 프로그램에서 돌린다.

관리 화면 서버는 스레드 방식(표준 라이브러리)이고 자동 올리기(plex_to_tg.Mirror)는 asyncio로 짜여 있어서,
따로 도는 스레드 하나에 asyncio 이벤트 루프를 띄우고 Mirror를 거기서 돌린다. 화면의 요청(api())은 그 루프에
일을 맡기고 결과를 기다린다.

  GET  /api/tgup              설정 + 진행 상태 + 텔레그램 계정 + Plex 연결 여부
  GET  /api/tgup/options      규칙 고르기용: Plex 영화·TV 라이브러리, rclone 드라이브, 쓸 수 있는 그래픽 인코더
  GET  /api/tgup/channels     로그인한 계정이 들어가 있는 채널·그룹
  GET  /api/tgup/folders?path= 폴더 고르기 (비우면 rclone mount 폴더·원격 목록)
  GET  /api/tgup/shot?rule=&key=  자막 기다리는 항목의 10분 지점 장면 (JPEG)
  POST /api/tgup/settings     설정 저장 (규칙들)
  POST /api/tgup/check        지금 확인
  POST /api/tgup/test         {rule} 가장 최근 것 하나 올려 보기
  POST /api/tgup/item         {rule, key, action: upload|drop|cancel|cancel_all}
  POST /api/tgup/notify       {action: save|test, webhook, bot_token, channel_id, ok, fail, skip} 디스코드 알림
  POST /api/tgup/account      {action: save_api|send_code|sign_in|logout, api_id, api_hash, phone, code, password}
"""
import asyncio
import logging
import threading
import time

from . import compat, folder_watch, notify, plex_to_tg, tgaccount

log = logging.getLogger("tgup")
CALL_TIMEOUT = 120
_ACC_FAIL = {}   # 텔레그램에 닿지 않았던 때와 그때 돌려준 상태


class _Runner:
    def __init__(self):
        self.loop = None
        self.mirror = None
        self.account = None
        self.http = None
        self.thread = None
        self._ready = threading.Event()
        self._task = None

    def start(self, stop_event=None):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="tgup", daemon=True)
        self.thread.start()
        self._ready.wait(10)
        if stop_event is not None:
            threading.Thread(target=lambda: (stop_event.wait(), self.stop()), name="tgup-stop", daemon=True).start()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._setup())
        self._ready.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self._teardown())
            self.loop.close()

    async def _setup(self):
        from aiohttp import ClientSession
        self.http = ClientSession()
        self.account = tgaccount.TelegramAccount()
        cfg = {"client_id": "bookoasis_assistant"}

        def plex_src(_sid):
            src = compat.plex_conf()
            return cfg, (src if src["url"] else None)

        def tg_for(_sid):
            return self.account

        async def plex_json(_cfg, src, path, params=None):
            if not src:
                raise RuntimeError("Plex 주소가 없습니다 (.env의 PLEX_URL / PLEX_TOKEN).")
            from aiohttp import ClientTimeout
            hdrs = {**compat.plex_headers(cfg, src.get("token")), "Accept": "application/json"}
            async with self.http.get(f"{src['url']}{path}", params=params or {}, headers=hdrs,
                                     ssl=None if src.get("verify_ssl", True) else False, timeout=ClientTimeout(total=15)) as r:
                if r.status >= 400:
                    raise RuntimeError(f"Plex HTTP {r.status}")
                return await r.json(content_type=None)

        self.plex_json = plex_json
        self.mirror = plex_to_tg.Mirror(plex_json, plex_src, tg_for, lambda: self.http)
        self._task = asyncio.ensure_future(self.mirror.loop())
        self._notify_task = asyncio.ensure_future(notify.watch(self.http, plex_to_tg.load_state))   # 디스코드 알림

    async def _teardown(self):
        for task in (self._task, getattr(self, "_notify_task", None)):
            if task:
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa: BLE001 - 끝내는 중
                    pass
        try:
            await self.account.close()
        except Exception:  # noqa: BLE001
            pass
        await self.http.close()

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    def call(self, coro, timeout=CALL_TIMEOUT):
        """다른 스레드에서: 루프에서 coro를 돌려 결과를 받는다"""
        if not self.loop:
            coro.close()
            raise RuntimeError("자동 올리기가 시작되지 않았습니다.")
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def run(self, fn, *args):
        """다른 스레드에서: 루프에서 보통 함수를 돌린다 (Mirror의 상태를 루프 밖에서 건드리지 않게)"""
        async def wrap():
            return fn(*args)
        return self.call(wrap())


RUNNER = _Runner()


def start(stop_event=None):
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        log.warning("aiohttp가 없어 텔레그램 자동 올리기를 켜지 못했습니다: pip install -r requirements.txt")
        return False
    RUNNER.start(stop_event)
    log.info("텔레그램 자동 올리기: 규칙 %d개 (data/tgup)", len(plex_to_tg.load_settings()["rules"]))
    return True


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


async def _account_status():
    """계정 상태 - 텔레그램에 닿지 않아도 화면이 오래 기다리지 않게 8초까지만"""
    last = _ACC_FAIL.get("at", 0)
    if time.time() - last < 60:   # 방금 닿지 않았으면 1분 동안은 다시 기다리지 않는다 (진행 상태가 15초마다 묻는다)
        return _ACC_FAIL["status"]
    try:
        return await asyncio.wait_for(RUNNER.account.status(), 8)
    except asyncio.TimeoutError:
        base = tgaccount.api_conf()
        _ACC_FAIL["at"] = time.time()
        _ACC_FAIL["status"] = {"authorized": False, "api_id": base["api_id"], "has_hash": bool(base["api_hash"]), "from_env": base["from_env"],
                "phone": base["phone"], "telethon": tgaccount.available(), "fast_crypto": tgaccount.fast_crypto(),
                "error": "텔레그램에 연결하지 못했습니다 (시간 초과) - 서버의 인터넷 연결을 확인하세요."}
        return _ACC_FAIL["status"]


def _state():
    return {"success": True, "settings": plex_to_tg.load_settings(), "status": RUNNER.run(RUNNER.mirror.status),
            "plex": bool(compat.plex_conf()["url"]), "ffmpeg": compat.available(),
            "rclone": bool(folder_watch.rclone_path()), "notify": notify.public(notify.settings())}


def api_get(path, query):
    """(상태 코드, JSON 또는 (bytes, content-type))"""
    if not RUNNER.loop:
        raise ApiError(503, "자동 올리기가 꺼져 있습니다 (aiohttp·telethon 설치 후 다시 시작).")
    if path == "/api/tgup":
        RUNNER.run(RUNNER.mirror.prepare_shots)
        return {**_state(), "account": RUNNER.call(_account_status(), 30)}
    if path == "/api/tgup/options":
        return RUNNER.call(_options(), 60)
    if path == "/api/tgup/channels":
        try:
            return {"success": True, "channels": RUNNER.call(RUNNER.account.list_channels(), 60)}
        except tgaccount.TgError as e:
            raise ApiError(400, str(e))
    if path == "/api/tgup/folders":
        return RUNNER.call(_folders(query.get("path", "").strip()), 60)
    if path == "/api/tgup/shot":
        shot = RUNNER.mirror.shot_file(query.get("rule", ""), query.get("key", ""))
        if not shot:
            raise ApiError(404, "장면을 아직 만들지 않았습니다.")
        with open(shot, "rb") as f:
            return f.read(), "image/jpeg"
    raise ApiError(404, "없는 주소입니다.")


async def _options():
    plex = []
    src = compat.plex_conf()
    if src["url"]:
        item = {"id": "plex", "name": "Plex", "sections": [], "error": ""}
        try:
            data = await RUNNER.plex_json(None, src, "/library/sections")
            item["sections"] = [{"key": str(d.get("key")), "title": d.get("title", ""), "type": d.get("type")}
                                for d in (data.get("MediaContainer") or {}).get("Directory") or [] if d.get("type") in ("movie", "show")]
        except Exception as e:  # noqa: BLE001
            item["error"] = f"Plex에 연결하지 못했습니다: {e}"
        plex.append(item)
    acc = await _account_status()
    tgs = [{"id": tgaccount.ACCOUNT_ID, "name": acc.get("name") or "내 텔레그램 계정"}] if acc.get("authorized") else []
    remotes, note = await folder_watch.list_remotes()
    mounts = folder_watch.rclone_mounts()
    encoders = {n: await folder_watch.hw_works(n) for n in ("nvenc", "qsv", "vaapi")}
    return {"success": True, "plex": plex, "telegram": tgs, "rclone": bool(folder_watch.rclone_path()), "encoders": encoders,
            "remotes": remotes, "mounts": mounts, "rclone_note": "" if remotes or mounts else note}


async def _folders(path):
    if not path:
        remotes, note = await folder_watch.list_remotes()
        mounts = folder_watch.rclone_mounts()
        return {"success": True, "path": "", "mounts": mounts, "remotes": remotes, "note": "" if remotes or mounts else note}
    try:
        path = folder_watch.clean_folder(path)
        dirs = await folder_watch.list_dirs(path)
    except (ValueError, folder_watch.FolderError) as e:
        raise ApiError(400, str(e))
    return {"success": True, "path": path, "dirs": dirs}


def api_post(path, body):
    if not RUNNER.loop:
        raise ApiError(503, "자동 올리기가 꺼져 있습니다 (aiohttp·telethon 설치 후 다시 시작).")
    m = RUNNER.mirror
    if path == "/api/tgup/settings":
        data = compat.load()
        try:
            data["plex_to_tg"] = plex_to_tg.clean_settings(body)
        except ValueError as e:
            raise ApiError(400, str(e))
        compat.save(data)
        RUNNER.run(m.wake)
        return _state()
    if path == "/api/tgup/notify":   # 디스코드 알림: {action: save|test, webhook, bot_token, channel_id, ok, fail, skip}
        data = compat.load()
        try:
            new = notify.clean(body, data.get("notify"))
        except ValueError as e:
            raise ApiError(400, str(e))
        if body.get("action") == "test":
            s = notify.settings({"notify": new})   # 화면에 넣은 값으로 (저장 전에도 시험할 수 있게)
            ok, msg = RUNNER.call(notify.send(RUNNER.http, s, {
                "title": "텔레그램 자동 올리기 · 알림 시험", "description": "이 채널로 자동 올리기 알림(올림·실패·건너뜀)이 옵니다.",
                "color": notify.COLOR["ok"], "footer": {"text": "bookoasis_assistant"}}), 30)
            if not ok:
                raise ApiError(400, f"디스코드로 보내지 못했습니다: {msg}")
            return {"success": True}
        data["notify"] = new
        compat.save(data)
        return {"success": True, "notify": notify.public(notify.settings())}
    if path == "/api/tgup/check":
        RUNNER.run(m.wake)
        return {"success": True}
    if path == "/api/tgup/test":
        try:
            return {"success": True, "title": RUNNER.call(m.test_latest(str(body.get("rule") or "")))}
        except Exception as e:  # noqa: BLE001
            raise ApiError(400, str(e))
    if path == "/api/tgup/item":
        rule, key, action = str(body.get("rule") or ""), str(body.get("key") or ""), body.get("action")
        fns = {"upload": m.force_item, "drop": m.drop_item, "cancel": m.cancel_item}
        try:
            if action == "cancel_all":
                return {"success": True, "count": RUNNER.run(m.cancel_all, rule or None)}
            if action not in fns:
                raise ApiError(400, "action은 upload, drop, cancel, cancel_all 중 하나입니다.")
            return {"success": True, "title": RUNNER.run(fns[action], rule, key)}
        except ValueError as e:
            raise ApiError(400, str(e))
    if path == "/api/tgup/account":
        return _account(body)
    raise ApiError(404, "없는 주소입니다.")


def _account(body):
    acc, action = RUNNER.account, body.get("action")
    try:
        if action == "save_api":
            api_id, api_hash = str(body.get("api_id") or "").strip(), str(body.get("api_hash") or "").strip()
            if not api_id.isdigit():
                raise ApiError(400, "API ID는 숫자입니다 (my.telegram.org > API development tools).")
            data = compat.load()
            tg = data.setdefault("telegram", {})
            tg["api_id"] = api_id
            if api_hash:   # 비워 두면 저장된 값 그대로
                tg["api_hash"] = api_hash
            if not tg.get("api_hash"):
                raise ApiError(400, "API Hash를 넣어 주세요.")
            compat.save(data)
            _ACC_FAIL.clear()
            return {"success": True, "account": RUNNER.call(_account_status(), 30)}
        if action == "send_code":
            return {"success": True, **RUNNER.call(acc.send_code(str(body.get("phone") or "")), 60)}
        if action == "sign_in":
            return {"success": True, **RUNNER.call(acc.sign_in(str(body.get("code") or ""), str(body.get("password") or "")), 60)}
        if action == "logout":
            RUNNER.call(acc.logout(), 30)
            return {"success": True, "account": RUNNER.call(_account_status(), 30)}
    except tgaccount.TgError as e:
        raise ApiError(400, str(e))
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001 - 텔레그램 쪽 오류 (번호 형식, 너무 잦은 요청 등)
        raise ApiError(400, f"텔레그램: {e}")
    raise ApiError(400, "action은 save_api, send_code, sign_in, logout 중 하나입니다.")
