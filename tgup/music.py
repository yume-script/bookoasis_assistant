# -*- coding: utf-8 -*-
"""자동 올리기의 "음악" 규칙: rclone 드라이브(또는 이 컴퓨터의 폴더)의 음악 파일(mp3·flac·m4a…)을 텔레그램에 올린다.

- 곡 정보: 파일 안의 태그(MP3 ID3 · FLAC/OGG Vorbis 주석 · m4a)를 ffprobe로 읽는다 -> 없는 칸은 폴더 이름
  ("아티스트/앨범 (연도)/01 곡.flac")으로 채운다.
- 캡션: 사람이 읽기 좋고 YMPlayer 텔레그램 소스(음악 채널)가 그대로 읽는 "이름: 값" 줄 (caption()).
  YMPlayer는 '앨범ID'로 같은 앨범 곡을 묶고 '트랙'·'디스크' 순서로 이어 재생한다.
- 텔레그램 오디오 속성(제목·아티스트·길이)도 붙여 텔레그램 앱에서도 음악으로 보이게, 앨범 아트는 곡 썸네일로.
- 파일은 바꾸지 않고(인코딩 없음) 원본 그대로 올린다.
"""
import hashlib
import os
import re

AUDIO_EXT = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".ape", ".alac", ".aiff", ".aif", ".dsf"}
COVER_NAMES = ("cover", "folder", "front", "album", "albumart", "artwork")
COVER_EXT = (".jpg", ".jpeg", ".png", ".webp")
CAPTION_MAX = 1024

# ffprobe 태그 이름(소문자) -> 칸. 형식마다 이름이 달라 여러 개를 본다 (앞쪽 우선)
_TAGS = {
    "title": ("title", "tit2"),
    "artist": ("artist", "tpe1", "performer"),
    "album": ("album", "talb"),
    "album_artist": ("album_artist", "albumartist", "album artist", "tpe2"),
    "track": ("track", "tracknumber", "trck"),
    "disc": ("disc", "discnumber", "disk", "tpos"),
    "year": ("date", "year", "originaldate", "tdrc", "tyer"),
    "genre": ("genre", "tcon"),
    "composer": ("composer", "tcom"),
    "lyricist": ("lyricist", "text", "writer", "lyrics_by", "lyricist(s)", "toly", "tlyr"),
    "arranger": ("arranger",),
    "mb_album": ("musicbrainz_albumid", "musicbrainz album id"),
    "track_total": ("tracktotal", "totaltracks"),
    "disc_total": ("disctotal", "totaldiscs"),
}
LABELS = (("artist", "아티스트"), ("album", "앨범"), ("album_artist", "앨범 아티스트"), ("track", "트랙"), ("disc", "디스크"),
          ("genre", "장르"), ("composer", "작곡"), ("lyricist", "작사"), ("arranger", "편곡"), ("album_id", "앨범ID"))
_NUM_RE = re.compile(r"^\s*(\d{1,3})(?:\s*/\s*(\d{1,3}))?")
_YEAR_RE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
_LEAD_NO = re.compile(r"^\s*(?:(\d{1,2})[-.](?=\d))?(\d{1,3})\s*(?:[.)\]_-]+\s*|\s+)(?=\S)")


def is_audio(name):
    return os.path.splitext(str(name or ""))[1].lower() in AUDIO_EXT


def _all_tags(info):
    """ffprobe 결과의 태그 (format 태그 + 오디오 스트림 태그 - OGG/OPUS는 스트림 쪽에 있다). 이름은 소문자"""
    out = {}
    for src in [*(s.get("tags") or {} for s in info.get("streams") or [] if s.get("codec_type") == "audio"),
                (info.get("format") or {}).get("tags") or {}]:
        for k, v in src.items():
            if v not in (None, ""):
                out[str(k).lower()] = str(v).strip()
    return out


def _num(v):
    """'3/12' -> (3, 12), '03' -> (3, None)"""
    m = _NUM_RE.match(str(v or ""))
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def _split_names(v):
    """여러 사람: 'A; B', 'A/B', 'A, B' 그대로 두되 줄바꿈·널 문자는 ' · '로"""
    return re.sub(r"\s*[\x00\r\n]+\s*", " · ", str(v or "")).strip(" ·")


def from_path(key):
    """폴더 이름으로 짐작: '아티스트/앨범 (2017)/CD1/03 곡.flac' -> {artist, album, year, disc, track, title}"""
    parts = [p for p in str(key).replace("\\", "/").split("/") if p]
    stem = os.path.splitext(parts[-1])[0] if parts else ""
    out = {}
    m = _LEAD_NO.match(stem)
    if m:
        if m.group(1):
            out["disc"] = int(m.group(1))
        out["track"] = int(m.group(2))
        stem = stem[m.end():]
    if " - " in stem and not out.get("track"):   # "아티스트 - 곡"
        a, _, t = stem.partition(" - ")
        out["artist"], stem = a.strip(), t
    out["title"] = re.sub(r"[_]+", " ", stem).strip()
    dirs = parts[:-1]
    if dirs and re.fullmatch(r"(?i)(cd|disc|disk)\s*(\d{1,2})", dirs[-1].strip()):
        out.setdefault("disc", int(re.sub(r"\D", "", dirs[-1])))
        dirs = dirs[:-1]
    if dirs:
        album = dirs[-1]
        y = _YEAR_RE.search(album)
        if y:
            out["year"] = y.group(1)
            album = re.sub(r"\s*[\[(]?\s*" + y.group(1) + r"\s*[\])]?\s*", " ", album).strip(" -_")
        if " - " in album and len(dirs) < 2:   # "아티스트 - 앨범"
            a, _, album = album.partition(" - ")
            out.setdefault("artist", a.strip())
        out["album"] = album.strip()
    if len(dirs) >= 2:
        out.setdefault("artist", dirs[-2].strip())
    return out


def track_meta(info, key):
    """곡 정보 {title, artist, album, album_artist, track, track_total, disc, disc_total, year, genre, composer, lyricist,
    arranger, duration, album_id} - 태그 우선, 없으면 폴더 이름"""
    tags = _all_tags(info or {})

    def tag(field):
        return next((tags[n] for n in _TAGS[field] if tags.get(n)), "")
    guess = from_path(key)
    m = {f: _split_names(tag(f)) for f in ("title", "artist", "album", "album_artist", "genre", "composer", "lyricist", "arranger")}
    track, ttot = _num(tag("track"))
    disc, dtot = _num(tag("disc"))
    m["track"] = track or guess.get("track")
    m["track_total"] = ttot or _num(tag("track_total"))[0]
    m["disc"] = disc or guess.get("disc")
    m["disc_total"] = dtot or _num(tag("disc_total"))[0]
    y = _YEAR_RE.search(tag("year"))
    m["year"] = y.group(1) if y else guess.get("year", "")
    for f in ("title", "artist", "album"):
        if not m[f]:
            m[f] = guess.get(f, "")
    if not m["title"]:
        m["title"] = os.path.splitext(os.path.basename(key))[0]
    try:
        m["duration"] = int(float((info or {}).get("format", {}).get("duration") or 0))
    except (TypeError, ValueError):
        m["duration"] = 0
    m["album_id"] = album_id(m, tag("mb_album"))
    return m


def album_id(m, mbid=""):
    """같은 앨범 곡을 묶는 고정 값: MusicBrainz 앨범 ID가 있으면 그것, 아니면 (앨범 아티스트 또는 아티스트, 앨범, 연도)의 해시.
    앨범 이름이 없으면 "" (낱곡)"""
    mbid = str(mbid or "").strip().lower()
    if re.fullmatch(r"[0-9a-f-]{36}", mbid):
        return "mb-" + mbid
    if not m.get("album"):
        return ""
    who = (m.get("album_artist") or m.get("artist") or "").casefold()
    base = "|".join([re.sub(r"\s+", " ", who).strip(), re.sub(r"\s+", " ", m["album"].casefold()).strip(), str(m.get("year") or "")])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def _numtext(n, total):
    return f"{n}/{total}" if n and total else (str(n) if n else "")


def caption(m):
    """곡 캡션 - 첫 줄 '🎵 곡 제목', 그 아래 '이름: 값' 줄 (YMPlayer가 읽는다). 빈 칸은 쓰지 않는다. 1024자 안으로"""
    lines = [f"🎵 {m.get('title') or ''}".strip()]
    for field, label in LABELS:
        if field == "track":
            v = _numtext(m.get("track"), m.get("track_total"))
        elif field == "disc":
            v = _numtext(m.get("disc"), m.get("disc_total")) if (m.get("disc_total") or 0) > 1 or (m.get("disc") or 0) > 1 else ""
        elif field == "album" and m.get("album") and m.get("year"):
            v = f"{m['album']} ({m['year']})"
        elif field == "album_artist" and m.get("album_artist") == m.get("artist"):
            v = ""
        else:
            v = m.get(field) or ""
        if v:
            lines.append(f"{label}: {str(v)[:300]}")
    if m.get("year") and not m.get("album"):
        lines.append(f"연도: {m['year']}")
    text = "\n".join(lines)
    while len(text) > CAPTION_MAX and len(lines) > 2:   # 길면 작곡·작사 등 뒤쪽 칸부터 줄인다 (앨범ID는 남김)
        drop = next((i for i in range(len(lines) - 1, 0, -1) if not lines[i].startswith("앨범ID")), None)
        if drop is None:
            break
        lines.pop(drop)
        text = "\n".join(lines)
    return text[:CAPTION_MAX]


def parse_caption(text):
    """caption()의 반대 (시험용·YMPlayer와 같은 규칙): {"title", 라벨 이름 칸...}"""
    out = {}
    rows = str(text or "").splitlines()
    if rows and rows[0].startswith("🎵"):
        out["title"] = rows[0][1:].strip()
    names = {label: field for field, label in LABELS}
    for row in rows[1:]:
        k, sep, v = row.partition(":")
        if sep and k.strip() in names:
            out[names[k.strip()]] = v.strip()
    return out


def cover_pick(names):
    """폴더의 파일 이름들 중 앨범 아트 (cover.jpg > folder.jpg > front… > 아무 그림 하나)"""
    imgs = [n for n in names if os.path.splitext(n)[1].lower() in COVER_EXT]
    for want in COVER_NAMES:
        for n in imgs:
            if os.path.splitext(n)[0].casefold() == want:
                return n
    return sorted(imgs)[0] if len(imgs) == 1 else ""


def has_picture(info):
    """파일 안에 든 앨범 아트 (attached_pic 스트림)가 있는지"""
    return any(s.get("codec_type") == "video" and (s.get("disposition") or {}).get("attached_pic")
               for s in (info or {}).get("streams") or [])


def sort_key(key):
    """올리는 순서: 폴더(앨범)별, 그 안에서 파일 이름 순 (01, 02 …) - 텔레그램에도 트랙 순서대로 올라가게"""
    d, base = os.path.split(str(key))
    return (d.casefold(), base.casefold())
