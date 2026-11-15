# -*- coding: utf-8 -*-
"""브런치 EPUB 옆에 kavita.yaml (BookOasis 메타데이터) 만들기

웹툰 다운로더(wtm/kavita_yaml.py)와 같은 형식(action / files / meta / search)을 같은 방식으로 쓴다.
책 하나 = 폴더 하나라서 kavita.yaml도 책마다 하나 (<저장 폴더>/<작가>/<제목>/kavita.yaml).
- 코드: 브런치북 BRB<주소>, 글 하나 BRA<작가id>_<번호>
- 출판사 "브런치", 작가, 소개(브런치북 소개 또는 글 부제), 연재 상태, 첫 회 발행일, 원문 주소, 표지(가로 300px JPEG)
- 내용이 같으면 파일을 다시 쓰지 않는다 (rclone 마운트에서 쓸데없는 변경 감지를 만들지 않게)
- PyYAML 없이 직접 쓴다. 웹툰 다운로더를 꺼 둬도 동작하도록 wtm을 불러오지 않는다.
"""
import base64
import json
import os
import re
from datetime import datetime

YAML_NAME = "kavita.yaml"
PUBLISHER = "브런치"
COVER_WIDTH = 300
COVER_QUALITY = 82
# Kavita PublicationStatus enum: OnGoing=0, Completed=2 / AgeRating: Everyone=3
_STATUS_ONGOING, _STATUS_COMPLETED = "0", "2"
_AGE_EVERYONE = "3"
_PLAIN_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_ ]*$")


# ── 작은 YAML 직렬화기 (wtm/kavita_yaml.py와 같은 모양) ──
def _scalar(v):
    if v is None:
        return "''"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def _key(k):
    k = str(k)
    return k if _PLAIN_KEY_RE.match(k) else json.dumps(k, ensure_ascii=False)


def _dump(obj, indent=0):
    pad = " " * indent
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                lines.append("%s%s:" % (pad, _key(k)))
                lines.extend(_dump(v, indent + 4))
            elif isinstance(v, list):
                lines.append("%s%s:" % (pad, _key(k)))
                lines.extend(_dump(v, indent))
            else:
                lines.append("%s%s: %s" % (pad, _key(k), _scalar(v)))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and item:
                sub = _dump(item, indent + 4)
                sub[0] = "%s-   %s" % (pad, sub[0].lstrip())
                lines.extend(sub)
            else:
                lines.append("%s-   %s" % (pad, _scalar(item)))
    return lines


def dump_yaml(data):
    return "\n".join(_dump(data)) + "\n"


def shrink_cover(data, width=COVER_WIDTH):
    """표지 bytes -> 가로 width px 이하 JPEG의 base64. Pillow가 없거나 깨진 그림이면 원본 그대로 base64"""
    if not data:
        return ""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.width > width:
            img = img.resize((width, max(1, round(img.height * width / img.width))), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.convert("RGBA").split()[-1])
            img = bg
        out = io.BytesIO()
        img.save(out, "JPEG", quality=COVER_QUALITY, optimize=True, progressive=True)
        small = out.getvalue()
        return base64.b64encode(small if len(small) < len(data) else data).decode("ascii")
    except Exception:  # noqa: BLE001 - Pillow 없음·깨진 그림
        return base64.b64encode(data).decode("ascii")


def word_count(chapters):
    """본문 글자 수 대신 낱말 수 (웹소설 EPUB과 같은 기준: 태그를 뺀 텍스트를 띄어쓰기로 나눔)"""
    n = 0
    for ch in chapters:
        text = re.sub(r"<[^>]+>", " ", ch.get("body") or "")
        n += len(text.split())
    return n


def code_of(key):
    kind, _, rest = str(key).partition(":")
    if kind == "book":
        return "BRB" + rest
    return "BRA" + rest.replace("/", "_")


def build_data(key, meta, file_name, words, cover_b64="", first_publish_ms=0):
    """meta: {title, author, description, url, status}"""
    title = meta.get("title") or ""
    author = meta.get("author") or ""
    summary = meta.get("description") or ""
    link = meta.get("url") or ""
    status = _STATUS_COMPLETED if meta.get("status") == "COMPLETE" else _STATUS_ONGOING
    rd = year = month = day = ""
    if first_publish_ms:
        d = datetime.fromtimestamp(int(first_publish_ms) / 1000)
        rd, year, month, day = d.strftime("%Y%m%d"), d.strftime("%Y"), d.strftime("%m"), d.strftime("%d")
    code = code_of(key)
    tag_str = PUBLISHER
    return {
        "action": {"all_file_is_special": False, "code": code, "first_cover": False},
        "files": {file_name: {"cover": cover_b64 or "FIRST", "page": 1, "wordcount": int(words or 0)}},
        "meta": {
            "Age Rating": _AGE_EVERYONE,
            "Collections": "",
            "Day": day,
            "Genres": "",
            "Language": "ko",
            "Month": month,
            "Name": title,
            "Person Character": "",
            "Person Colorist": "",
            "Person CoverArtist": "",
            "Person Editor": "",
            "Person Imprint": "",
            "Person Inker": "",
            "Person Letterer": "",
            "Person Location": "",
            "Person Penciller": "",
            "Person Publisher": PUBLISHER,
            "Person Team": "",
            "Person Translator": "",
            "Person Writers": author,
            "Publication Status": status,
            "Release Date": rd,
            "Summary": summary,
            "Tags": tag_str,
            "Web Links": link,
            "Writer": "",
            "Year": year,
        },
        "search": [{
            "Day": day,
            "Month": month,
            "Publication Status": status,
            "Release Date": rd,
            "Year": year,
            "author": author,
            "code": code,
            "description": summary,
            "genre": "",
            "illustrator": "",
            "link": link,
            "poster_url": meta.get("cover_url") or "",
            "publisher": PUBLISHER,
            "score": 100,
            "tag": tag_str,
            "title": title,
        }],
    }


def write(folder, data):
    """folder/kavita.yaml을 쓴다 (내용이 같으면 그대로). 반환: 경로 (실패하면 "")"""
    path = os.path.join(folder, YAML_NAME)
    text = dump_yaml(data)
    try:
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == text:
                return path
    except OSError:
        pass
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        return path
    except OSError:
        return ""
