# -*- coding: utf-8 -*-
"""자동 올리기의 "유튜브" 규칙: 유튜브 링크를 주면 yt-dlp로 받아 그 규칙의 텔레그램 채널에 올린다.
X(트위터) 게시물 링크도 같은 규칙으로 받는다 (x.com · twitter.com · fxtwitter 등 -> key "x-<게시물 id>",
여러 영상이 있는 게시물은 '/video/2'처럼 번호를 붙이면 그 영상, 없으면 첫 영상). 로그인이 있어야 보이는 게시물은 받지 못한다.

- 규칙 폴더: DATA_DIR/tgup_youtube/<규칙 id> (이 서버). 링크마다 요청 파일 <key>.request.json {"url", "title"}을 두고
  진행 목록에는 key("yt-<영상 id>")로 넣는다 - 서버를 다시 켜도, 실패해 다시 시도할 때도 링크를 잃지 않는다.
- 받기: 규칙의 높이(720p 등) 이하에서 mp4(H.264/AAC) 우선 -> 없으면 다른 형식(올릴 때 mp4로 인코딩). 한국어 자막이 있으면 같이.
- 올리기: 받은 파일을 폴더 규칙과 같은 과정(인코딩·나누기·자막·썸네일)으로. 캡션 칸: {name}(영상 제목) {uploader} {date} {url} {summary}(설명)
- 다 올리면(또는 중복으로 건너뛰면) 받은 파일을 지운다. 실패하면 남겨 두고 다시 시도할 때 그대로 쓴다.
- 쿠키 (선택): 유튜브가 "봇이 아닌지 로그인으로 확인"을 요구하면 쿠키 없이는 받지 못한다. [유튜브·X 보내기] 탭에서 넣은
  cookies.txt(Netscape 형식, DATA_DIR/tgup/youtube_cookies.txt, 이 서버만 읽게 600) 또는 .env의 YTDLP_COOKIES(파일 경로)를
  yt-dlp에 --cookies로 넘긴다. 내용은 화면에 다시 보여 주지 않는다. 로그인 요구로 실패하면 다시 시도하지 않고 알린다 (LoginRequired).
"""
import asyncio
import glob
import json
import logging
import os
import re
import shutil
import sys
import urllib.parse

from . import compat

log = logging.getLogger("tgup")
YT_CAPTION = "{name}\n\n📺 {uploader} · {date}\n🔗 {url}\n\n{summary}"
MAX_URLS = 50
PLAYLIST_MAX = 200
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_X_HOSTS = ("x.com", "twitter.com", "fxtwitter.com", "vxtwitter.com", "fixupx.com", "fixvx.com", "twittpr.com")
_X_PATH = re.compile(r"^/(?:[A-Za-z0-9_]{1,30}|i(?:/web)?)/status(?:es)?/(\d{5,25})(?:/(?:video|photo)/([1-4]))?/?$")


def root():
    return os.path.join(compat.DATA_DIR, "tgup_youtube")


def rule_folder(rule_id):
    return os.path.join(root(), re.sub(r"[^A-Za-z0-9_-]", "_", str(rule_id))[:16])


def video_id(url):
    """유튜브 주소 -> 영상 id (11자리), 영상 주소가 아니면 "" (watch?v= · youtu.be/ · shorts/ · live/ · embed/)"""
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    host = (p.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _HOSTS):
        return ""
    if host.endswith("youtu.be"):
        cand = p.path.strip("/").split("/")[0]
    else:
        cand = (urllib.parse.parse_qs(p.query).get("v") or [""])[0]
        if not cand:
            m = re.match(r"^/(?:shorts|live|embed|v)/([^/?#]+)", p.path)
            cand = m.group(1) if m else ""
    return cand if _ID_RE.match(cand) else ""


def x_post(url):
    """X(트위터) 게시물 주소 -> (게시물 id, 영상 번호 1~4 또는 0), 아니면 ("", 0)"""
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return "", 0
    host = (p.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _X_HOSTS):
        return "", 0
    m = _X_PATH.match(p.path)
    return (m.group(1), int(m.group(2) or 0)) if m else ("", 0)


def x_key(tid, n=0):
    return f"x-{tid}" + (f"-{n}" if n else "")


def x_url(tid, n=0):
    return f"https://x.com/i/status/{tid}" + (f"/video/{n}" if n else "")


def is_x(key):
    return str(key).startswith("x-")


def site_of(key):
    return "X" if is_x(key) else "유튜브"


def playlist_id(url):
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if not any((p.hostname or "").lower().endswith(h) for h in _HOSTS):
        return ""
    lid = (urllib.parse.parse_qs(p.query).get("list") or [""])[0]
    return lid if re.fullmatch(r"[A-Za-z0-9_-]{10,64}", lid) else ""


def split_urls(text):
    """붙여 넣은 글 -> 주소 목록 (줄·빈칸·쉼표로 나뉨, 같은 것은 한 번)"""
    items = text if isinstance(text, list) else re.split(r"[\s,]+", str(text or ""))
    return list(dict.fromkeys(u.strip() for u in items if str(u).strip().startswith(("http://", "https://"))))


def key_of(vid):
    return f"yt-{vid}"


def vid_of(key):
    return str(key)[3:] if str(key).startswith("yt-") else ""


def watch_url(vid):
    return f"https://www.youtube.com/watch?v={vid}"


def _req_path(folder, key):
    return os.path.join(folder, f"{key}.request.json")


def save_request(folder, key, url, title=""):
    os.makedirs(folder, exist_ok=True)
    with open(_req_path(folder, key), "w", encoding="utf-8") as f:
        json.dump({"url": url, "title": title}, f, ensure_ascii=False)


def load_request(folder, key):
    try:
        with open(_req_path(folder, key), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        vid = vid_of(key)
        if vid:
            return {"url": watch_url(vid)}
        m = re.fullmatch(r"x-(\d+)(?:-([1-4]))?", str(key))
        return {"url": x_url(m.group(1), int(m.group(2) or 0))} if m else {}


def ytdlp_cmd():
    """yt-dlp 실행 명령 (설치한 파이썬 패키지 > PATH의 yt-dlp). 없으면 None"""
    import importlib.util
    if not os.environ.get("YTDLP_PATH") and importlib.util.find_spec("yt_dlp"):
        return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which(os.environ.get("YTDLP_PATH") or "yt-dlp")
    return [exe] if exe else None


def available():
    return bool(ytdlp_cmd())


def fmt_select(height):
    """받을 형식: height 이하에서 mp4(H.264)+m4a 우선 -> 같은 높이의 다른 형식 -> 아무거나 (높이 0이면 제한 없음)"""
    h = f"[height<={int(height)}]" if height else ""
    return (f"bv*{h}[vcodec^=avc1]+ba[ext=m4a]/b{h}[ext=mp4][vcodec^=avc1]/"
            f"bv*{h}+ba/b{h}/bv*+ba/b")


def _safe(name):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(name or "")).strip(" .")
    return name[:90].rstrip(" .") or "video"


def find_file(folder, key):
    """이미 받아 둔 영상 (다시 시도할 때) - 요청 파일에 적어 둔 '<제목> [<id>].mp4', 없으면 받다 만 '<key>.<확장자>'"""
    req = load_request(folder, key)
    if req.get("file") and os.path.isfile(os.path.join(folder, req["file"])):
        return os.path.join(folder, req["file"])
    for p in sorted(glob.glob(os.path.join(glob.escape(folder), glob.escape(key) + ".*"))):
        rest = os.path.basename(p)[len(key) + 1:]
        if "." in rest or rest in ("json", "part", "ytdl", "srt", "vtt"):   # 정보·자막·받는 중(.f137.mp4·.temp.mp4·.mp4.part)
            continue
        return p
    return ""


async def expand(urls, timeout=120):
    """주소들 -> [(진행 목록 key, 주소)] (재생목록 주소는 안의 영상들로, 최대 PLAYLIST_MAX). X 게시물은 key "x-<id>".
    유튜브·X 영상이 아닌 주소는 ValueError"""
    out, bad = [], []
    for u in split_urls(urls)[:MAX_URLS]:
        vid = video_id(u)
        if vid:
            out.append((key_of(vid), watch_url(vid)))
            continue
        tid, n = x_post(u)
        if tid:
            out.append((x_key(tid, n), x_url(tid, n)))
            continue
        lid = playlist_id(u)
        if not lid:
            bad.append(u)
            continue
        cmd = ytdlp_cmd()
        if not cmd:
            raise RuntimeError("서버에 yt-dlp가 없습니다 (pip install yt-dlp).")
        proc = await asyncio.create_subprocess_exec(*cmd, *cookie_args(), "--flat-playlist", "--print", "id", "--playlist-end", str(PLAYLIST_MAX),
                                                    f"https://www.youtube.com/playlist?list={lid}",
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            so, se = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("재생목록을 읽는 데 너무 오래 걸립니다.") from None
        ids = [x.strip() for x in so.decode("utf-8", "replace").splitlines() if _ID_RE.match(x.strip())]
        if not ids:
            lines = se.decode("utf-8", "replace").strip().splitlines()
            if any(_LOGIN_RE.search(t) for t in lines):
                raise _fail(lines, proc.returncode)
            raise RuntimeError(f"재생목록을 읽지 못했습니다: {(lines[-1] if lines else '')[:200]}")
        out += [(key_of(v), watch_url(v)) for v in ids]
    if bad:
        raise ValueError("유튜브 영상·재생목록이나 X 게시물 주소가 아닙니다: " + ", ".join(bad[:5]))
    seen, uniq = set(), []
    for vid, u in out:
        if vid not in seen:
            seen.add(vid)
            uniq.append((vid, u))
    return uniq


_PROG = re.compile(r"^yp:(\d+|NA)/(\d+|NA)")
COOKIE_NAME = "youtube_cookies.txt"
COOKIE_MAX = 512 * 1024
_LOGIN_RE = re.compile(r"Sign in to confirm|cookies-from-browser|--cookies|confirm you.re not a bot|login required|Sign in to view"
                       r"|requires authentication|NSFW tweet|log in to", re.I)


class LoginRequired(RuntimeError):
    """유튜브가 로그인(쿠키)을 요구함 - 바로 다시 해도 안 되므로 다시 시도하지 않는다"""


def _upload_cookie_path():
    return os.path.join(compat.DATA_DIR, COOKIE_NAME)


def cookies_path():
    """yt-dlp에 줄 쿠키 파일 (.env YTDLP_COOKIES > 화면에서 넣은 것), 없으면 None"""
    env = os.environ.get("YTDLP_COOKIES", "").strip()
    if env and os.path.isfile(env):
        return env
    p = _upload_cookie_path()
    return p if os.path.isfile(p) and os.path.getsize(p) > 0 else None


def cookie_args():
    p = cookies_path()
    return ["--cookies", p] if p else []


def cookies_status():
    """화면에 보일 쿠키 상태 (내용은 보여 주지 않음)"""
    env = os.environ.get("YTDLP_COOKIES", "").strip()
    if env:
        ok = os.path.isfile(env)
        return {"set": ok, "source": "env", "path": env, "missing": not ok,
                "updated": int(os.path.getmtime(env)) if ok else 0}
    p = _upload_cookie_path()
    if os.path.isfile(p) and os.path.getsize(p) > 0:
        return {"set": True, "source": "upload", "updated": int(os.path.getmtime(p)), "size": os.path.getsize(p)}
    return {"set": False}


def save_cookies(text):
    """[유튜브·X 보내기]에서 넣은 cookies.txt 내용을 저장 (Netscape 형식, youtube.com 쿠키가 있어야). 돌려주는 값: 쿠키 줄 수"""
    text = str(text or "")
    if len(text.encode("utf-8")) > COOKIE_MAX:
        raise ValueError("쿠키 파일이 너무 큽니다 (512KB까지).")
    rows = [ln for ln in text.splitlines() if ln.strip() and (not ln.startswith("#") or ln.startswith("#HttpOnly_"))]
    good = [ln for ln in rows if len(ln.split("\t")) >= 7]
    if not good:
        raise ValueError("Netscape 형식(cookies.txt)이 아닙니다 - 브라우저 확장(예: Get cookies.txt LOCALLY)으로 내보낸 파일을 넣어 주세요.")
    if not any("youtube.com" in ln.split("\t")[0] for ln in good):
        raise ValueError("youtube.com 쿠키가 없습니다 - 유튜브에 로그인한 상태에서 내보내 주세요.")
    os.makedirs(compat.DATA_DIR, exist_ok=True)
    p = _upload_cookie_path()
    body = text if text.lstrip().startswith("# ") else "# Netscape HTTP Cookie File\n" + text
    fd = os.open(p + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body if body.endswith("\n") else body + "\n")
    os.replace(p + ".tmp", p)
    os.chmod(p, 0o600)
    return len(good)


def delete_cookies():
    try:
        os.remove(_upload_cookie_path())
        return True
    except OSError:
        return False


def _fail(tail, returncode, site="유튜브"):
    """yt-dlp 오류 -> 예외 (로그인 요구면 LoginRequired). 오류 줄은 앞부분을 남긴다 (예전엔 뒤 300자라 'Sign in to confirm…'이 잘림)"""
    err = next((t for t in tail if "ERROR" in t), tail[-1] if tail else f"종료 코드 {returncode}")
    err = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", err)
    if site == "X":
        if any(_LOGIN_RE.search(t) for t in tail):
            return LoginRequired("X가 로그인을 요구하는 게시물입니다 (민감한 내용·비공개 계정 등) - 받지 못합니다.")
        if re.search(r"No video could be found|no video", err, re.I):
            return RuntimeError("X 게시물에 영상이 없습니다.")
        return RuntimeError(f"X에서 받지 못했습니다: {err[:300]}")
    if any(_LOGIN_RE.search(t) for t in tail):
        if cookies_path():
            return LoginRequired("유튜브가 로그인을 요구합니다 - 넣어 둔 쿠키가 만료됐거나 막혔습니다. [유튜브·X 보내기] 탭에서 쿠키 파일을 새로 넣어 주세요.")
        return LoginRequired("유튜브가 로그인(봇 확인)을 요구합니다 - [유튜브·X 보내기] 탭에서 쿠키 파일(cookies.txt)을 넣어 주세요.")
    return RuntimeError(f"유튜브에서 받지 못했습니다: {err[:300]}")


async def download(url, folder, key, height=720, progress=None, cancelled=None):
    """yt-dlp로 받아 '<제목> [<id>].<확장자>'로 둔다 (한국어 자막이 있으면 같은 이름 + .ko.srt). 돌려주는 값: 영상 경로.
    progress(받은 바이트, 전체)는 받는 동안, cancelled()가 True면 멈춘다"""
    cmd = ytdlp_cmd()
    if not cmd:
        raise RuntimeError("서버에 yt-dlp가 없습니다 (pip install yt-dlp 또는 .env의 YTDLP_PATH).")
    os.makedirs(folder, exist_ok=True)
    args = [*cmd, *([] if is_x(key) else cookie_args()), "--no-playlist", "-q", "--no-warnings", "--newline", "--progress", "--progress-template", "download:yp:%(progress.downloaded_bytes)s/%(progress.total_bytes,progress.total_bytes_estimate)s",
            "-f", fmt_select(height), "--merge-output-format", "mp4", "--write-info-json", "--no-write-playlist-metafiles",
            "--write-subs", "--sub-langs", "ko.*,ko", "--convert-subs", "srt", "--no-mtime",
            "-o", os.path.join(folder, f"{key}.%(ext)s")]
    ff = compat.ffmpeg_path() if hasattr(compat, "ffmpeg_path") else None
    if ff:
        args += ["--ffmpeg-location", ff]
    args += ["--", url]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    tail = []

    async def read_err():
        async for line in proc.stderr:
            tail.append(line.decode("utf-8", "replace").rstrip())
            del tail[:-20]
    err_task = asyncio.ensure_future(read_err())
    try:
        async for line in proc.stdout:
            m = _PROG.match(line.decode("utf-8", "replace").strip())
            if m and progress:
                progress(int(m.group(1)) if m.group(1) != "NA" else 0, int(m.group(2)) if m.group(2) != "NA" else 0)
            if cancelled and cancelled():
                proc.kill()
                raise RuntimeError("직접 취소")
        await proc.wait()
    except asyncio.CancelledError:
        proc.kill()
        raise
    finally:
        await asyncio.gather(err_task, return_exceptions=True)
    if proc.returncode != 0:
        raise _fail(tail, proc.returncode, site_of(key))
    path = find_file(folder, key)
    if not path:
        raise RuntimeError(f"{site_of(key)}에서 받은 파일을 찾지 못했습니다.")
    info = load_info(folder, key)
    # 읽기 좋은 이름으로 (텔레그램에 그 이름으로 올라간다): '<제목> [<id>].mp4' - 자막도 같이
    name = x_text(info) if is_x(key) else info.get("title")
    stem = f"{_safe(name or key)} [{vid_of(key) or key}]"
    new = os.path.join(folder, stem + os.path.splitext(path)[1])
    os.replace(path, new)
    for sub in glob.glob(os.path.join(glob.escape(folder), glob.escape(key) + ".*.srt")):
        lang = sub[len(os.path.join(folder, key)) + 1:-4]
        os.replace(sub, os.path.join(folder, f"{stem}.{lang}.srt"))
    req = load_request(folder, key)
    req.update(file=os.path.basename(new), title=info.get("title") or req.get("title") or "")
    with open(_req_path(folder, key), "w", encoding="utf-8") as f:
        json.dump(req, f, ensure_ascii=False)
    return new


def load_info(folder, key):
    """yt-dlp가 적은 영상 정보 (제목·채널·날짜·설명) - 필요한 칸만"""
    try:
        with open(os.path.join(folder, f"{key}.info.json"), encoding="utf-8") as f:
            d = json.load(f) or {}
    except (OSError, ValueError):
        return {}
    return {k: d.get(k) for k in ("id", "title", "uploader", "uploader_id", "channel", "upload_date", "description", "webpage_url",
                                  "duration", "extractor_key")}


def x_text(info):
    """X 게시물 글의 첫 줄 (t.co 링크·해시태그 줄 빼고, 100자) - yt-dlp 제목은 '작성자 - 글…'이라 그대로 쓰면 이름이 두 번 나온다"""
    for line in str(info.get("description") or "").splitlines():
        line = re.sub(r"https?://t\.co/\S+", "", line).strip()
        if line:
            return line[:100] + ("…" if len(line) > 100 else "")
    return str(info.get("uploader") or "")


def fields(info, req):
    """캡션 칸 ({name} {title} {uploader} {date} {url} {summary}) - 연도는 비워 둔다 (영화 중복 확인에 쓰이지 않게)"""
    d = str(info.get("upload_date") or "")
    date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d) else ""
    x = str(info.get("extractor_key") or "").lower() == "twitter" or "x.com/" in str(req.get("url") or "")
    title = (x_text(info) if x else str(info.get("title") or req.get("title") or "")).strip()
    desc = str(info.get("description") or "").strip()
    if x:
        desc = re.sub(r"\s*https?://t\.co/\S+", "", desc).strip()
    who = str(info.get("uploader") or info.get("channel") or "")
    if x and info.get("uploader_id"):
        who = f"{who} (@{info['uploader_id']})" if who else f"@{info['uploader_id']}"
    return {"name": title, "title": title, "uploader": who,
            "date": date, "url": str(info.get("webpage_url") or req.get("url") or ""),
            "summary": desc[:600] + ("…" if len(desc) > 600 else ""), "year": "", "show": "", "season": "", "episode": "", "code": ""}


def cleanup(folder, key, video_path=""):
    """다 올린 뒤: 받은 영상·자막·정보·요청 파일을 지운다"""
    stem = os.path.splitext(os.path.basename(video_path))[0] if video_path else ""
    pats = [glob.escape(key) + ".*"] + ([glob.escape(stem) + ".*"] if stem else [])
    for pat in pats:
        for p in glob.glob(os.path.join(glob.escape(folder), pat)):
            try:
                os.remove(p)
            except OSError:
                pass
