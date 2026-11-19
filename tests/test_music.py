# -*- coding: utf-8 -*-
"""텔레그램 자동 올리기 - 음악 규칙 (tgup/music.py, Mirror.upload_music). 텔레그램에는 붙지 않는다 (가짜 클라이언트)."""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="music-test-")
os.environ.setdefault("GDW_ENV_FILE", os.path.join(TMP, ".env"))
os.environ.setdefault("DATA_DIR", os.path.join(TMP, "data"))

try:
    import aiohttp  # noqa: F401
    HAVE_AIOHTTP = True
except ImportError:
    HAVE_AIOHTTP = False
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

from tgup import music  # noqa: E402


def _info(tags, stream_tags=None, duration="215.4", pic=False):
    streams = [{"codec_type": "audio", "tags": stream_tags or {}}]
    if pic:
        streams.append({"codec_type": "video", "disposition": {"attached_pic": 1}})
    return {"format": {"duration": duration, "tags": tags}, "streams": streams}


class MusicMetaTest(unittest.TestCase):
    def test_tags_first_then_path(self):
        info = _info({"TITLE": "밤편지", "ARTIST": "아이유", "ALBUM": "Palette", "album_artist": "아이유", "track": "3/10",
                      "disc": "1/1", "DATE": "2017-04-21", "GENRE": "발라드", "composer": "김제휘", "LYRICIST": "아이유",
                      "ARRANGER": "김제휘"})
        m = music.track_meta(info, "아이유/Palette (2017)/03 밤편지.flac")
        self.assertEqual((m["title"], m["artist"], m["album"], m["track"], m["track_total"], m["disc"], m["year"], m["duration"]),
                         ("밤편지", "아이유", "Palette", 3, 10, 1, "2017", 215))
        self.assertEqual((m["composer"], m["lyricist"], m["arranger"], m["genre"]), ("김제휘", "아이유", "김제휘", "발라드"))
        cap = music.caption(m)
        self.assertEqual(cap.splitlines()[0], "🎵 밤편지")
        self.assertIn("앨범: Palette (2017)", cap)
        self.assertIn("트랙: 3/10", cap)
        self.assertNotIn("디스크", cap)            # 한 장짜리 앨범은 디스크를 쓰지 않음
        self.assertNotIn("앨범 아티스트", cap)     # 아티스트와 같으면 생략
        back = music.parse_caption(cap)
        self.assertEqual((back["title"], back["artist"], back["composer"], back["lyricist"], back["album_id"]),
                         ("밤편지", "아이유", "김제휘", "아이유", m["album_id"]))

    def test_ogg_stream_tags_and_id3_names(self):
        m = music.track_meta(_info({}, {"title": "곡", "artist": "가수", "album": "앨범", "TRACKNUMBER": "7", "TRACKTOTAL": "12"}),
                             "x/y/z.opus")
        self.assertEqual((m["title"], m["artist"], m["track"], m["track_total"]), ("곡", "가수", 7, 12))
        m = music.track_meta(_info({"TIT2": "노래", "TPE1": "A", "TCOM": "작곡가", "TEXT": "작사가"}), "a.mp3")
        self.assertEqual((m["title"], m["artist"], m["composer"], m["lyricist"]), ("노래", "A", "작곡가", "작사가"))

    def test_path_fallback(self):
        g = music.from_path("Artist/Album Name (2019)/CD2/05. Song Title.flac")
        self.assertEqual((g["artist"], g["album"], g["year"], g["disc"], g["track"], g["title"]),
                         ("Artist", "Album Name", "2019", 2, 5, "Song Title"))
        g = music.from_path("아티스트 - 앨범/1-03 곡.mp3")   # 디스크-트랙
        self.assertEqual((g["artist"], g["album"], g["disc"], g["track"], g["title"]), ("아티스트", "앨범", 1, 3, "곡"))
        g = music.from_path("가수 - 노래.mp3")
        self.assertEqual((g["artist"], g["title"]), ("가수", "노래"))
        m = music.track_meta({}, "Artist/Album (2019)/02 Two.flac")   # 태그 없음 -> 폴더 이름
        self.assertEqual((m["artist"], m["album"], m["track"], m["title"]), ("Artist", "Album", 2, "Two"))

    def test_album_id(self):
        a = music.track_meta(_info({"ALBUM": "Same", "ARTIST": "X", "DATE": "2000"}), "1.flac")
        b = music.track_meta(_info({"ALBUM": "same", "ARTIST": "x", "DATE": "2000", "TITLE": "다른 곡"}), "2.flac")
        c = music.track_meta(_info({"ALBUM": "Same", "ARTIST": "Y", "DATE": "2000"}), "3.flac")
        self.assertEqual(a["album_id"], b["album_id"])            # 같은 앨범의 다른 곡
        self.assertNotEqual(a["album_id"], c["album_id"])         # 이름이 같은 다른 가수의 앨범
        va = music.track_meta(_info({"ALBUM": "OST", "ARTIST": "A", "album_artist": "Various"}), "1.flac")
        vb = music.track_meta(_info({"ALBUM": "OST", "ARTIST": "B", "album_artist": "Various"}), "2.flac")
        self.assertEqual(va["album_id"], vb["album_id"])          # 컴필레이션: 앨범 아티스트로 묶음
        mb = music.track_meta(_info({"ALBUM": "x", "MUSICBRAINZ_ALBUMID": "0F8D0B4A-1E2B-4C9D-8E7F-112233445566"}), "1.flac")
        self.assertEqual(mb["album_id"], "mb-0f8d0b4a-1e2b-4c9d-8e7f-112233445566")
        self.assertEqual(music.track_meta(_info({"TITLE": "낱곡"}), "a.mp3")["album_id"], "")

    def test_long_caption_trimmed_keeps_album_id(self):
        m = music.track_meta(_info({"TITLE": "t", "ALBUM": "a", "ARTIST": "b", "composer": "작" * 300, "LYRICIST": "사" * 300,
                                    "ARRANGER": "편" * 300, "GENRE": "g" * 300}), "1.flac")
        cap = music.caption(m)
        self.assertLessEqual(len(cap), 1024)
        self.assertIn("앨범ID: " + m["album_id"], cap)

    def test_cover_pick_and_order(self):
        self.assertEqual(music.cover_pick(["01.flac", "back.jpg", "Cover.JPG", "folder.png"]), "Cover.JPG")
        self.assertEqual(music.cover_pick(["01.flac", "scan.jpg"]), "scan.jpg")
        self.assertEqual(music.cover_pick(["01.flac", "a.jpg", "b.jpg"]), "")
        keys = ["B/02 b.flac", "A/10 j.flac", "A/02 b.flac", "B/01 a.flac"]
        self.assertEqual(sorted(keys, key=music.sort_key), ["A/02 b.flac", "A/10 j.flac", "B/01 a.flac", "B/02 b.flac"])
        self.assertTrue(music.has_picture(_info({}, pic=True)) and not music.has_picture(_info({})))


@unittest.skipUnless(HAVE_AIOHTTP, "aiohttp 없음")
class MusicRuleTest(unittest.TestCase):
    def test_settings_music_rule(self):
        from tgup import plex_to_tg as m
        st = m.clean_settings({"rules": [{"kind": "music", "folder": "/mnt/gdrive/음악", "tg": "tg", "channel": "-100123",
                                          "upload_existing": True, "wait_subs": True, "burn_subs": True},
                                         {"kind": "folder", "folder": "/mnt/gdrive/영화", "tg": "tg", "channel": "-100124"}]})
        music_rule, video_rule = st["rules"]
        self.assertEqual((music_rule["kind"], music_rule["media"], music_rule["upload_existing"]), ("folder", "music", True))
        self.assertFalse(music_rule["wait_subs"] or music_rule["burn_subs"])
        self.assertEqual((video_rule["media"], video_rule["upload_existing"]), ("video", False))
        self.assertIs(m.rule_exts(music_rule), music.AUDIO_EXT)
        self.assertEqual(m.music_title("아이유/Palette (2017)/03 밤편지.flac"), "아이유 - 밤편지")

    def test_queue_existing_in_track_order(self):
        from tgup import plex_to_tg as m
        mir = m.Mirror(None, None, lambda *a: None, None)
        rule = {"id": "mu", "kind": "folder", "media": "music"}
        rs = {"done": [], "fails": {}, "baseline": 1, "known": [], "sigs": [], "sizes": {}}
        files = [{"key": f"A/{n:02d} t.flac", "size": 10 + n, "mtime": 100 - n} for n in (3, 1, 2)]
        rs["sizes"] = {f["key"]: f["size"] for f in files}
        mir.queue = []
        mir._queue_files(rule, rs, files, set(), set())
        self.assertEqual([j["key"] for j in mir.queue], ["A/01 t.flac", "A/02 t.flac", "A/03 t.flac"])

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg 없음")
    def test_upload_music_local(self):
        """진짜 flac(태그·커버 폴더)을 만들어 올리기: 캡션·오디오 속성·썸네일·가사 파일"""
        from telethon.tl.types import DocumentAttributeAudio
        from tgup import compat, plex_to_tg as m
        root = tempfile.mkdtemp(prefix="music-src-")
        compat.DATA_DIR = tempfile.mkdtemp(prefix="music-data-")
        album = os.path.join(root, "아이유", "Palette (2017)")
        os.makedirs(album)
        song = os.path.join(album, "03 밤편지.flac")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=2", "-metadata", "title=밤편지",
                        "-metadata", "artist=아이유", "-metadata", "album=Palette", "-metadata", "track=3/10",
                        "-metadata", "date=2017", "-metadata", "composer=김제휘", "-metadata", "lyricist=아이유", song], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=600x600", "-frames:v", "1",
                        os.path.join(album, "cover.jpg")], check=True)
        with open(os.path.join(album, "03 밤편지.lrc"), "w", encoding="utf-8") as f:
            f.write("[00:00.50]가사\n")
        sent = []

        class Client:
            async def send_file(self, peer, path, **kw):
                sent.append((os.path.basename(path), kw))
                return types.SimpleNamespace(id=len(sent))

        class Tg:
            async def authorized_client(self):
                return Client()

            async def peer(self, ch):
                return ch

        async def run():
            mir = m.Mirror(None, None, lambda *a: Tg(), None)
            lane = m.Lane("tg")
            m._LANE.set(lane)
            lane.current_job = {"rule": "mu", "key": "아이유/Palette (2017)/03 밤편지.flac", "tg": "tg"}
            rule = {"id": "mu", "kind": "folder", "media": "music", "folder": root, "tg": "tg", "channel": "-100", "channel_title": "음악"}
            return await mir.upload_music(rule, "아이유/Palette (2017)/03 밤편지.flac", 2, test=True)
        try:
            note = asyncio.run(run())
        finally:
            shutil.rmtree(root, ignore_errors=True)
        self.assertEqual([n for n, _ in sent], ["03 밤편지.flac", "03 밤편지.lrc"])
        kw = sent[0][1]
        cap = music.parse_caption(kw["caption"])
        self.assertEqual((cap["title"], cap["artist"], cap["track"], cap["composer"], cap["lyricist"]), ("밤편지", "아이유", "3/10", "김제휘", "아이유"))
        self.assertIn("앨범: Palette (2017)", kw["caption"])
        audio = next(a for a in kw["attributes"] if isinstance(a, DocumentAttributeAudio))
        self.assertEqual((audio.title, audio.performer, audio.duration), ("밤편지", "아이유", 2))
        self.assertTrue(kw["thumb"])          # cover.jpg -> 썸네일
        self.assertIn("앨범 아트", note)
        self.assertIn("가사(.lrc) 첨부", note)


if __name__ == "__main__":
    unittest.main()
