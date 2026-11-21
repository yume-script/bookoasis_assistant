# -*- coding: utf-8 -*-
"""자막 기다리는 영상이 하드섭(자막을 영상에 입힘)인지 LLM(이미지를 볼 수 있는 모델 - Gemini 등)에게 묻기 - 선택 기능.

LiteLLM(또는 OpenAI 호환 /v1/chat/completions)에 5분 간격 장면 이미지(plex_to_tg._grab_sheet)를 보내
"화면에 한국어 자막이 박혀 있나?"를 JSON으로 받는다. 설정(규칙 탭 > 하드섭 자동 판단):
  enabled  켜기 (기본 끔)
  url      LiteLLM 주소 (예: http://127.0.0.1:4000)
  model    LiteLLM의 model_name (이미지를 볼 수 있는 모델 - 예: gemini-flash)
  auto     판단이 '한국어 하드섭'(확신 MIN_CONF 이상)이면 바로 올리기 (끄면 진행 상태에 판단만 표시)
키: .env의 HARDSUB_LLM_API_KEY (없으면 LITELLM_API_KEY) 또는 화면에서 넣은 값 (data/tgup/settings.json의 hardsub_llm_key)
"""
import base64
import json
import logging
import re

from . import compat

log = logging.getLogger("tgup")
MIN_CONF = 0.7
RETRY_SEC = 6 * 3600
PROMPT = ("이 이미지는 한 동영상의 5분 간격 장면들을 이어 붙인 것입니다. 영상 화면 안에 자막 글자가 박혀 있는지(하드섭) 판단하세요. "
          "방송 로고·간판·제목 글자·화면 속 표지판은 자막이 아닙니다. 대사 자막(보통 화면 아래쪽 가운데)만 봅니다. "
          "다른 말 없이 JSON 하나로만 답하세요: "
          '{"hardsub": true/false, "korean": true/false (박힌 자막이 한국어인지), "confidence": 0~1, "reason": "짧은 근거(한국어)"}')


def settings(raw=None):
    """clean_settings가 부른다 - {"enabled", "url", "model", "auto"}"""
    raw = raw if isinstance(raw, dict) else {}
    url = str(raw.get("url") or "").strip().rstrip("/")
    if url and not re.match(r"^https?://", url):
        url = "http://" + url
    return {"enabled": bool(raw.get("enabled")), "url": url[:300], "model": str(raw.get("model") or "").strip()[:120],
            "auto": bool(raw.get("auto", True))}


def api_key():
    env = compat.config.env("HARDSUB_LLM_API_KEY") or compat.config.env("LITELLM_API_KEY")
    return str(env or (compat.load().get("hardsub_llm_key") or "")).strip()


def key_from_env():
    return bool(compat.config.env("HARDSUB_LLM_API_KEY") or compat.config.env("LITELLM_API_KEY"))


def save_key(key):
    data = compat.load()
    if key:
        data["hardsub_llm_key"] = str(key).strip()
    else:
        data.pop("hardsub_llm_key", None)
    compat.save(data)


def ready(conf):
    """켜져 있고 주소·모델이 있으면 "" - 아니면 까닭"""
    if not conf.get("enabled"):
        return "꺼짐"
    if not conf.get("url") or not conf.get("model"):
        return "LLM 주소·모델을 넣어 주세요"
    return ""


def _endpoint(url):
    return url + ("/chat/completions" if url.endswith("/v1") else "/v1/chat/completions")


def parse(text):
    """모델 답에서 JSON을 꺼내 {"hardsub", "korean", "confidence", "reason"} (못 읽으면 ValueError)"""
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        raise ValueError(f"LLM 답을 읽지 못했습니다: {str(text)[:120]}")
    d = json.loads(m.group(0))
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {"hardsub": bool(d.get("hardsub")), "korean": bool(d.get("korean")), "confidence": round(conf, 2),
            "reason": str(d.get("reason") or "")[:200]}


async def judge(http, conf, image_path, timeout=90):
    """장면 이미지 -> 판단. 실패하면 RuntimeError"""
    from aiohttp import ClientTimeout
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    body = {"model": conf["model"], "temperature": 0, "max_tokens": 300,
            "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                                      {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]}
    headers = {"Content-Type": "application/json"}
    key = api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with http.post(_endpoint(conf["url"]), json=body, headers=headers, timeout=ClientTimeout(total=timeout)) as r:
            raw = await r.text()
            if r.status >= 400:
                raise RuntimeError(f"LLM HTTP {r.status}: {raw[:200]}")
    except RuntimeError:
        raise
    except Exception as e:  # noqa: BLE001 - 연결 실패 등
        raise RuntimeError(f"LLM에 연결하지 못했습니다: {e}") from None
    try:
        msg = (json.loads(raw).get("choices") or [{}])[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):   # 일부 공급자는 조각 목록으로
            content = " ".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
        return parse(content)
    except (ValueError, AttributeError) as e:
        raise RuntimeError(str(e)) from None


def is_go(verdict):
    """바로 올려도 되는 판단: 한국어 하드섭이고 확신 MIN_CONF 이상"""
    return bool(verdict and verdict.get("hardsub") and verdict.get("korean") and verdict.get("confidence", 0) >= MIN_CONF)


def label(verdict):
    if not verdict:
        return ""
    if verdict.get("error"):
        return f"LLM 판단 실패: {verdict['error'][:80]}"
    pct = int(round((verdict.get("confidence") or 0) * 100))
    if verdict.get("hardsub"):
        return f"LLM: {'한국어 ' if verdict.get('korean') else '다른 언어 '}하드섭 ({pct}%)"
    return f"LLM: 화면에 자막 없음 ({pct}%)"

