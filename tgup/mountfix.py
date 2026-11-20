# -*- coding: utf-8 -*-
"""rclone mount에서 파일 하나만 못 읽을 때 되살리기 (자동 올리기).

rclone mount의 캐시(VFS)가 어떤 파일만 낡은 상태로 남으면 구글 드라이브 원본은 멀쩡한데 마운트로는 읽기가 실패하거나
ffprobe가 영상 정보를 못 읽는다. 마운트 전체를 다시 붙이지 않고 그 파일만:
  1) vfs/forget (그 파일) + vfs/refresh (그 폴더) -> 다시 읽기
  2) 그래도 안 되면 마운트를 거치지 않고 원격에서 직접 받기 (rclone copyto)

RC 주소 찾는 순서 (마운트마다):
  1) 보관함 설정의 rclone_rc_url (그 마운트 안의 보관함), Plex RC 주소(PLEX_RC_URL)
  2) 이 컴퓨터에서 돌고 있는 'rclone mount ... --rc' 프로세스의 --rc-addr (/proc/*/cmdline)
  3) .env의 RCLONE_RC_MAP=/mnt/gds2=http://127.0.0.1:5572;/mnt/b=http://user:pass@127.0.0.1:5573
RC 주소마다 vfs/list로 그 마운트의 VFS가 맞는지 확인하고 쓴다 (다른 마운트의 RC면 건너뜀).
"""
import asyncio
import base64
import glob
import json
import logging
import os
import posixpath
import re
import urllib.parse
import urllib.request

from . import folder_watch

log = logging.getLogger("tgup")
TIMEOUT = 30
MOUNT_CMDS = ("mount", "cmount", "nfsmount")


def mount_of(path, mounts_file="/proc/mounts"):
    """rclone mount 안의 파일이면 {"path": 마운트 위치, "remote": "gds2:", "rel": "폴더/파일.mkv"}, 아니면 None"""
    try:
        real = os.path.realpath(path)
    except OSError:
        real = path
    best = None
    for m in folder_watch.rclone_mounts(mounts_file):
        mnt = m["path"].rstrip("/") or "/"
        if (real == mnt or real.startswith(mnt + "/")) and (best is None or len(mnt) > len(best["path"])):
            best = {"path": mnt, "remote": m["remote"], "rel": real[len(mnt):].lstrip("/")}
    return best


def _split_auth(url):
    """'http://u:p@host:5572' -> ('http://host:5572', 'Basic ...')"""
    url = str(url or "").strip().rstrip("/")
    if not url:
        return "", ""
    if "://" not in url:
        url = "http://" + url
    p = urllib.parse.urlsplit(url)
    auth = ""
    if p.username is not None:
        auth = "Basic " + base64.b64encode(
            f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}".encode()).decode()
        netloc = p.hostname + (f":{p.port}" if p.port else "")
        url = urllib.parse.urlunsplit((p.scheme, netloc, p.path, "", "")).rstrip("/")
    return url, auth


def _flag(argv, name):
    """--name=값 / --name 값 -> 값 (없으면 None)"""
    for i, a in enumerate(argv):
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
    return None


def proc_rc(mount, proc="/proc"):
    """그 마운트를 붙인 rclone 프로세스의 RC 주소 [(url, auth)] (--rc 없이 돌면 [])"""
    out = []
    for f in glob.glob(os.path.join(proc, "[0-9]*", "cmdline")):
        try:
            with open(f, "rb") as fh:
                argv = [a.decode("utf-8", "replace") for a in fh.read().split(b"\0") if a]
        except OSError:
            continue
        if not argv or "rclone" not in os.path.basename(argv[0]) or not any(c in argv[1:] for c in MOUNT_CMDS):
            continue
        if not any(a.rstrip("/") == mount["path"] for a in argv) or not any(a == mount["remote"] for a in argv):
            continue
        if "--rc" not in argv and _flag(argv, "--rc-addr") is None:
            continue
        addr = _flag(argv, "--rc-addr") or "localhost:5572"
        host, _, port = addr.rpartition(":")
        host = host.strip("[]") or "127.0.0.1"
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        url = f"{'https' if _flag(argv, '--rc-cert') else 'http'}://{host}:{port or 5572}"
        user, pw = _flag(argv, "--rc-user"), _flag(argv, "--rc-pass")
        auth = "Basic " + base64.b64encode(f"{user}:{pw or ''}".encode()).decode() if user else ""
        out.append((url, auth))
    return out


def _env(key):
    v = os.environ.get(key)
    if v is None:
        try:
            from gdw import config
            v = config.env(key)
        except Exception:  # noqa: BLE001 - 설정을 못 읽으면 다른 곳에서 찾는다
            v = ""
    return str(v or "")


def _library_rc(mount):
    """보관함 설정(libraries.manual.json)에서 그 마운트 안 폴더의 rclone_rc_url"""
    try:
        from gdw import config
        with open(config.libraries_file(), encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for lib in raw if isinstance(raw, list) else raw.get("libraries") or []:
        roots = lib.get("roots") or lib.get("physical_path") or []
        roots = roots.splitlines() if isinstance(roots, str) else roots
        if lib.get("rclone_rc_url") and any(str(r).strip().rstrip("/") == mount["path"]
                                            or str(r).strip().startswith(mount["path"] + "/") for r in roots):
            out.append(lib["rclone_rc_url"])
    return out


def rc_candidates(mount, proc="/proc"):
    """그 마운트에 쓸 RC 주소 후보 [(url, auth)] (중복 없이, 위 순서)"""
    urls = [_split_auth(u) for u in _library_rc(mount)]
    if _env("PLEX_RC_URL"):
        urls.append(_split_auth(_env("PLEX_RC_URL")))
    urls += proc_rc(mount, proc)
    for part in re.split(r"[;\n]", _env("RCLONE_RC_MAP")):
        path, sep, url = part.strip().partition("=")
        if sep and path.strip().rstrip("/") == mount["path"]:
            urls.append(_split_auth(url))
    seen, out = set(), []
    for u in urls:
        if u[0] and u[0] not in seen:
            seen.add(u[0])
            out.append(u)
    return out


def _call(url, auth, command, params, timeout=TIMEOUT):
    req = urllib.request.Request(f"{url}/{command}", data=urllib.parse.urlencode(params).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    if auth:
        req.add_header("Authorization", auth)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _pick_fs(vfses, remote):
    """vfs/list 결과 중 그 마운트의 것: 하나뿐이면 그것 (fs를 안 보내도 됨 -> ""), 여럿이면 이름이 같은 것, 없으면 None"""
    if len(vfses) <= 1:
        return ""
    want = remote.rstrip("/")
    for v in vfses:
        if v.rstrip("/") == want or v.rstrip("/") == want.rstrip(":"):
            return v
    return None


def forget_sync(path, mounts_file="/proc/mounts", proc="/proc"):
    """그 파일의 VFS 캐시를 잊게 한다. 돌려주는 값 (성공?, 설명)"""
    mount = mount_of(path, mounts_file)
    if not mount:
        return False, "rclone mount가 아님"
    cands = rc_candidates(mount, proc)
    if not cands:
        return False, f"{mount['path']}의 rclone RC 주소를 찾지 못함 (mount에 --rc를 켜거나 RCLONE_RC_MAP)"
    errs = []
    for url, auth in cands:
        try:
            vfses = (_call(url, auth, "vfs/list", {}) or {}).get("vfses") or []
            fs = _pick_fs(vfses, mount["remote"])
            if fs is None:
                errs.append(f"{url}: 다른 마운트의 RC")
                continue
            extra = {"fs": fs} if fs else {}
            _call(url, auth, "vfs/forget", {"file": mount["rel"], **extra})
            try:
                _call(url, auth, "vfs/refresh", {"dir": posixpath.dirname(mount["rel"]), "recursive": "false", **extra})
            except Exception as e:  # noqa: BLE001 - forget만 돼도 다시 읽어 본다
                log.info("자동 올리기: vfs/refresh 실패 (%s): %s", url, e)
            return True, f"vfs/forget ({url})"
        except Exception as e:  # noqa: BLE001
            errs.append(f"{url}: {e}")
    return False, "; ".join(errs)[:300]


async def forget(path):
    return await asyncio.to_thread(forget_sync, path)


async def remote_copy(path, dest, progress=None):
    """마운트를 거치지 않고 원격에서 dest로 받는다 (rclone copyto). rclone mount 파일이 아니면 FolderError"""
    mount = mount_of(path)
    if not mount:
        raise folder_watch.FolderError("rclone mount가 아니라 원격에서 받을 수 없습니다.")
    await folder_watch.fetch(mount["remote"], mount["rel"], dest, progress)
    return dest
