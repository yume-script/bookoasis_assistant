# -*- coding: utf-8 -*-
"""BookOasis DB 직접 연결 (예전 플러그인의 get_db_gateway 자리)

플러그인일 때는 BookOasis 프로세스 안에서만 DB를 볼 수 있어서 중복 확인 스레드를 Flask 앱 문맥에
얹는 등 무리가 있었다. 독립형은 .env의 연결 주소로 직접 붙는다.

  BOOKOASIS_DB_URL=mysql://user:pass@host:3306/{db_type}   ({db_type} → general, adult, …)
  BOOKOASIS_DB_URL_ADULT=mysql://…                         (세션별로 따로 지정할 때)
  sqlite:////abs/path/{db_type}.db                          (SQLite 파일)

MySQL/MariaDB는 PyMySQL(requirements.txt)이 필요하다. 쿼리는 %s 자리표시자로 쓰고,
SQLite에서는 ?로 바꿔 실행한다.
"""
import sqlite3
import threading
from urllib.parse import parse_qs, unquote, urlparse

from . import config


class DBError(RuntimeError):
    pass


class Gateway:
    """한 세션(db_type)의 DB. 요청마다 연결하고 닫는다 (호출 빈도가 낮고, 오래 열어 두면 끊김 처리가 번거롭다)."""

    def __init__(self, db_type, url):
        self.db_type = db_type
        self.url = url
        parsed = urlparse(url)
        self.scheme = parsed.scheme.split("+")[0].lower()
        if self.scheme not in ("mysql", "mariadb", "sqlite"):
            raise DBError(f"지원하지 않는 DB 주소 형식입니다 ({db_type}): {parsed.scheme}:// (mysql:// 또는 sqlite:///)")
        self.parsed = parsed

    def _connect(self):
        if self.scheme == "sqlite":
            path = unquote(self.parsed.path or "")
            if self.parsed.netloc:  # sqlite://relative/path 형태
                path = self.parsed.netloc + path
            conn = sqlite3.connect(path, timeout=30)
            conn.row_factory = sqlite3.Row
            return conn
        try:
            import pymysql
            import pymysql.cursors
        except ImportError as error:
            raise DBError("MySQL/MariaDB 연결에 PyMySQL이 필요합니다: pip install -r requirements.txt") from error
        query = {k: v[-1] for k, v in parse_qs(self.parsed.query).items()}
        return pymysql.connect(host=self.parsed.hostname or "127.0.0.1", port=self.parsed.port or 3306,
                               user=unquote(self.parsed.username or ""), password=unquote(self.parsed.password or ""),
                               database=unquote((self.parsed.path or "/").lstrip("/")) or None,
                               charset=query.get("charset", "utf8mb4"), connect_timeout=10, read_timeout=30,
                               write_timeout=30, autocommit=True, cursorclass=pymysql.cursors.DictCursor)

    def _sql(self, sql):
        return sql.replace("%s", "?") if self.scheme == "sqlite" else sql

    def _run(self, sql, params, fetch):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(self._sql(sql), tuple(params or ()))
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row is not None else None
            if fetch == "all":
                return [dict(r) for r in cur.fetchall()]
            if self.scheme == "sqlite":
                conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def fetch_all(self, sql, params=()):
        return self._run(sql, params, "all")

    def fetch_one(self, sql, params=()):
        return self._run(sql, params, "one")

    def execute(self, sql, params=()):
        return self._run(sql, params, None)


_CACHE = {}
_LOCK = threading.Lock()


def configured():
    return any(config.db_url(t) for t in config.db_types())


def gateway(db_type):
    url = config.db_url(db_type)
    if not url:
        raise DBError(f"BookOasis DB 주소가 없습니다 ({db_type}). .env의 BOOKOASIS_DB_URL을 확인하세요.")
    with _LOCK:
        cached = _CACHE.get(db_type)
        if cached is None or cached.url != url:
            cached = _CACHE[db_type] = Gateway(db_type, url)
        return cached


def describe(url):
    """화면·로그용: 비밀번호를 가린 주소."""
    parsed = urlparse(url or "")
    if parsed.password:
        netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
        return parsed._replace(netloc=netloc).geturl()
    return url or ""
