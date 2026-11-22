# -*- coding: utf-8 -*-
"""텔레그램 빠른 업로드 - 파일 조각(512KB)을 여러 연결로 동시에 올린다 (FastTelethon 방식).

Telethon의 기본 upload_file은 연결 하나로 조각을 하나씩 차례로 올려서(요청마다 왕복 시간만큼 쉼) 회선을 다 쓰지 못한다.
여기서는 그 계정의 홈 DC에 같은 인증 키로 연결을 몇 개 더 열고(MTProtoSender), 조각을 나눠 동시에 올린 뒤
InputFile/InputFileBig 핸들을 돌려준다 -> client.send_file(peer, 핸들, ...)로 보낸다.
- 조각 크기는 늘 512KB (텔레그램 최대 - 요청 수가 가장 적다)
- 연결을 더 열지 못하면(Telethon 내부가 바뀜 등) 기존 연결 하나에 요청을 겹쳐 보낸다 (그래도 차례로보다 빠름)
- 텔레그램이 기다리라고 하면(FloodWait) Telethon이 60초 이하는 혼자 기다리고, 넘으면 그대로 올려 보내 계정 줄이 처리한다
"""
import asyncio
import logging
import math
import os
import random

log = logging.getLogger("tgup")
PART = 512 * 1024
BIG = 10 * 1024 * 1024        # 이보다 크면 SaveBigFilePart (텔레그램 규칙)
PART_RETRIES = 3


async def _open_senders(client, n):
    """같은 계정·홈 DC로 연결 n개를 더 연다 (실패하면 연 만큼만)"""
    out = []
    if n <= 0:
        return out
    try:
        from telethon.network import MTProtoSender
        sess = client.session
        for _ in range(n):
            s = MTProtoSender(sess.auth_key, loggers=client._log)
            await s.connect(client._connection(sess.server_address, sess.port, sess.dc_id, loggers=client._log,
                                               proxy=client._proxy, local_addr=getattr(client, "_local_addr", None)))
            out.append(s)
        return out
    except Exception as e:  # noqa: BLE001 - 더 못 열면 기존 연결만
        log.info("빠른 업로드: 연결을 더 열지 못해 기존 연결로 겹쳐 보냅니다: %s", e)
        return out


async def upload(client, path, connections=4, progress=None):
    """path를 조각내어 동시에 올리고 InputFile 핸들을 돌려준다. progress(올린 바이트, 전체)"""
    from telethon.errors import FloodWaitError
    from telethon.tl.functions.upload import SaveBigFilePartRequest, SaveFilePartRequest
    from telethon.tl.types import InputFile, InputFileBig
    size = os.path.getsize(path)
    parts = max(1, math.ceil(size / PART))
    big = size > BIG
    file_id = random.getrandbits(63)
    connections = max(1, int(connections or 1))
    senders = await _open_senders(client, connections - 1)
    calls = [client] + [(lambda req, s=s: client._call(s, req)) for s in senders]
    while len(calls) < connections:   # 더 못 열었으면 기존 연결에 겹쳐 보냄
        calls.append(client)
    state = {"next": 0, "done": 0}

    async def worker(call):
        with open(path, "rb") as f:
            while True:
                i = state["next"]
                if i >= parts:
                    return
                state["next"] = i + 1
                f.seek(i * PART)
                data = f.read(PART)
                req = (SaveBigFilePartRequest(file_id, i, parts, data) if big else SaveFilePartRequest(file_id, i, data))
                for attempt in range(PART_RETRIES):
                    try:
                        if not await call(req):
                            raise RuntimeError(f"조각 {i}을(를) 텔레그램이 받지 않았습니다.")
                        break
                    except FloodWaitError:
                        raise
                    except Exception as e:  # noqa: BLE001 - 끊김 등: 몇 번 다시, 더 연 연결이 안 되면 기본 연결로
                        if attempt == PART_RETRIES - 1:
                            raise
                        log.info("빠른 업로드: 조각 %d 다시 (%s)", i, e)
                        if call is not client:
                            call = client   # 더 연 연결이 말썽이면 이 줄은 기본 연결로 이어서
                        await asyncio.sleep(1 + attempt * 2)
                state["done"] += len(data)
                if progress:
                    progress(min(state["done"], size), size)

    tasks = [asyncio.ensure_future(worker(c)) for c in calls]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        for s in senders:
            try:
                await s.disconnect()
            except Exception:  # noqa: BLE001
                pass
    name = os.path.basename(path)
    return InputFileBig(file_id, parts, name) if big else InputFile(file_id, parts, name, "")
