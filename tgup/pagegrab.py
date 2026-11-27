# -*- coding: utf-8 -*-
"""[유튜브·X 보내기] > 페이지에서 X 영상 찾기: 웹 페이지 주소를 주면 그 HTML에서 video.twimg.com의 mp4 주소를 뽑아 저장한다.
고른 주소는 유튜브·X 규칙의 진행 목록에 넣어(Mirror.add_youtube) 그 채널에 올린다.

- 뽑기: HTML·스크립트 안의 'https://video.twimg.com/....mp4(?…)' (\\/ 이스케이프·&amp; 정리). 같은 영상(미디어 id)이 화질별로
  여러 개 있으면 가장 큰 화질(경로의 가로x세로) 하나만.
- 받기: http/https만, 사설·내부 주소(127.0.0.1, 192.168.x, 10.x, ::1 등)는 막는다 (리다이렉트도 하나씩 확인, 5번까지).
  15초, 8MB까지.
- 저장: DATA_DIR/tgup_pages.json - 최근 PAGES_MAX개 페이지 {url, title, at, urls, sent}. 같은 페이지는 새로 찾은 것으로 바꾼다.
"""
import html
import ipaddress
import json
import os
import re
import socket
import threading
import time
import urllib.parse

from . import compat, youtube

# 스크립트 안의 JSON은 '/'를 '\/'로 적는다 - 주소 전체(경로 포함)에서 '\/'를 받는다
PATTERN = re.compile(r'https?:(?:\\?/){2}video\.twimg\.com\\?/(?:[^\s"\'<>\\]|\\/)+?\.mp4(?:\?[^\s"\'<>\\]*)?')
_RES = re.compile(r"/(\d{2,5})x(\d{2,5})/")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
PAGES_MAX = 30
URLS_MAX = 300
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = 15
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_lock = threading.Lock()


class GrabError(ValueError):
    pass


def _area(url):
    m = _RES.search(urllib.parse.urlsplit(url).path)
    return int(m.group(1)) * int(m.group(2)) if m else 0


def extract(text):
    """HTML -> X 영상 mp4 주소들 (나온 순서, 같은 영상은 가장 큰 화질 하나)"""
    best, order = {}, []
    for m in PATTERN.findall(text or ""):
        url = html.unescape(m.replace("\\/", "/"))
        if url.startswith("http://"):
            url = "https://" + url[7:]
        key = youtube.twimg_key(url)
        if not key:
            continue
        if key not in best:
            order.append(key)
            best[key] = url
        elif _area(url) > _area(best[key]):
            best[key] = url
    return [best[k] for k in order][:URLS_MAX]


def page_title(text):
    m = _TITLE.search(text or "")
    t = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""
    return t[:120]


def _check_host(url):
    """http/https이고 공인 주소로만 가는지 (사설·내부·루프백 주소는 막음)"""
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise GrabError("http:// 또는 https:// 페이지 주소를 넣어 주세요.")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise GrabError(f"주소를 찾지 못했습니다: {p.hostname}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise GrabError("내부(사설) 주소의 페이지는 열지 않습니다.")


def fetch(url, session=None):
    """페이지 HTML (리다이렉트를 하나씩 확인하며 따라감)"""
    import requests
    s = session or requests.Session()
    cur = str(url or "").strip()
    for _ in range(6):
        _check_host(cur)
        try:
            r = s.get(cur, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}, timeout=TIMEOUT,
                      allow_redirects=False, stream=True)
        except requests.RequestException as e:
            raise GrabError(f"페이지를 열지 못했습니다: {str(e)[:200]}") from None
        if r.is_redirect and r.headers.get("location"):
            cur = urllib.parse.urljoin(cur, r.headers["location"])
            r.close()
            continue
        if r.status_code >= 400:
            r.close()
            raise GrabError(f"페이지가 응답하지 않습니다 (HTTP {r.status_code}).")
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                break
        r.close()
        return body.decode(r.encoding or "utf-8", "replace"), cur
    raise GrabError("리다이렉트가 너무 많습니다.")


def _path():
    return os.path.join(compat.DATA_DIR, "tgup_pages.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _save(pages):
    os.makedirs(compat.DATA_DIR, exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pages[:PAGES_MAX], f, ensure_ascii=False)
    os.replace(tmp, _path())


def grab(url, fetcher=None):
    """페이지에서 뽑아 저장 -> 그 페이지 기록 {url, title, at, urls, sent}. 하나도 없으면 GrabError (저장하지 않음)"""
    url = str(url or "").strip()
    text, final = (fetcher or fetch)(url)
    urls = extract(text)
    if not urls:
        raise GrabError("이 페이지에서 X 영상(video.twimg.com의 mp4) 주소를 찾지 못했습니다 - 영상을 스크립트로 나중에 불러오는 페이지일 수 있습니다.")
    with _lock:
        pages = load()
        old = next((p for p in pages if p.get("url") == url), {})
        entry = {"url": url, "final": final if final != url else "", "title": page_title(text), "at": int(time.time()),
                 "urls": urls, "sent": [u for u in old.get("sent") or [] if u in urls]}
        _save([entry] + [p for p in pages if p.get("url") != url])
    return entry


def mark_sent(url, urls):
    with _lock:
        pages = load()
        for p in pages:
            if p.get("url") == url:
                p["sent"] = list(dict.fromkeys((p.get("sent") or []) + [u for u in urls if u in p.get("urls", [])]))
        _save(pages)


def delete(url):
    with _lock:
        pages = load()
        _save([p for p in pages if p.get("url") != url])
