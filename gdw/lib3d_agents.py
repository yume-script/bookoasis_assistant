"""BookOasis 3D 서재 AI 직원 (1단계: 사서·도슨트) + AI 손님 (책을 찾고 직원에게 묻는 방문객 3명)

에이전트마다 직업(job)·목표(goal)·성격(personality)·기억(memory)·행동(actions)·근무 위치(post)를 가진다.
- 대화: 채팅에서 '@사서 …', '@도슨트 …'로 부른다. 답은 부른 사람에게만, 말하기(say)는 그 층 모두에게.
- 행동: LLM이 '월드 도구'(move_to·say·point_at_book·set_board·remember)를 부르면 서버는 상태만 바꾸고,
  각자의 3D 화면이 그 상태대로 직원을 걷게 하고 말풍선·안내판을 그린다 (서버가 3D를 직접 만지지 않는다).
- 자율 업무: 이용자가 없어도 정해진 주기마다 업무(오늘의 추천 도서·구역 순찰 등)를 하고 활동 기록에 남긴다.
  LLM 호출은 lib3d_ai의 하루 한도(LIB3D_AI_DAILY, 기본 1000)를 같이 쓴다.
- 손님(kind=guest): 정해진 주기마다 입구로 들어와 관심 구역을 둘러보고, 직원에게 묻고(ask_staff), 책을 살펴본 뒤 나간다.
  하루 한도의 GUEST_BUDGET_SHARE를 넘게 썼으면 손님은 오지 않는다 (진짜 이용자 몫을 남김).
저장: DATA_DIR/lib3d_agents.json (정의·설정), DATA_DIR/lib3d_agents_state.json (위치·안내판·기억·기록)
"""
import copy
import json
import logging
import os
import random
import re
import threading
import time

from . import config, lib3d, lib3d_ai, lib3d_presence

log = logging.getLogger("gdw.lib3d_agents")

LOG_KEEP = 200
NOTES_KEEP = 40
PLACES = ("desk", "lobby", "entrance", "lounge", "elevator", "office", "gallery", "jazz")
PLACE_KO = {"desk": "안내 데스크", "lobby": "로비 한가운데", "entrance": "입구", "lounge": "라운지(소파)", "elevator": "엘리베이터 앞",
            "office": "길 건너 사무실", "gallery": "길 건너 갤러리", "jazz": "길 건너 재즈 청음실"}
ROOM_POSTS = ("office", "gallery", "jazz")   # 1층 밖 길 건너 건물 1층 ([창밖 풍경 > 거리]의 건물)

DEFAULT_AGENTS = [
    {"id": "librarian", "name": "한서윤", "job": "사서 (Chief Librarian)", "call": ["@사서", "@안내", "@ai", "@봇"], "post": "desk", "look": 3,
     "goal": "이용자가 원하는 책을 빠르고 정확하게 찾아 주고, 취향에 맞는 책을 권하며, 도서관이 늘 잘 정리돼 있게 한다.",
     "personality": "차분하고 다정하다. 책 이야기를 할 때 눈이 반짝인다. 짧고 분명하게 말하고, 모르는 것은 솔직히 모른다고 한다.",
     "actions": ["move_to", "say", "point_at_book", "set_board", "remember"], "enabled": True,
     "tasks": [
         {"id": "pick", "title": "오늘의 추천 도서", "every_min": 1440, "enabled": True,
          "prompt": "오늘의 추천 도서를 고르는 시간이다. search_books나 get_random_book으로 서재(일반)에서 한 권을 고르고, "
                    "왜 권하는지 두세 문장으로 정리해 set_board로 로비 안내판에 '오늘의 추천 도서'를 걸어라. 끝나면 한 일을 한 문장으로 답하라."},
         {"id": "check", "title": "서재 점검", "every_min": 360, "enabled": True,
          "prompt": "서재 상태를 점검하는 시간이다. get_library_stats로 서재 규모를 확인하고, 특이한 점이 있으면 remember로 기억해 두어라. "
                    "끝나면 점검 결과를 한두 문장으로 답하라."}]},
    {"id": "docent", "name": "이도윤", "job": "도슨트 (Library Guide)", "call": ["@도슨트", "@가이드"], "post": "lobby", "look": 17,
     "goal": "처음 온 사람도 도서관을 즐겁게 둘러볼 수 있게, 구역(서가)마다 어떤 책이 있는지 직접 데려가며 소개한다.",
     "personality": "밝고 수다스럽지만 핵심을 놓치지 않는다. '여기 보세요!' 하며 앞장서는 걸 좋아한다.",
     "actions": ["move_to", "say", "point_at_book", "set_board", "remember"], "enabled": True,
     "tasks": [
         {"id": "patrol", "title": "구역 순찰", "every_min": 120, "enabled": True,
          "prompt": "구역을 순찰하는 시간이다. 이 층의 구역 하나를 골라 move_to로 가서, search_books로 그 구역에 어떤 책이 있는지 살펴보고 "
                    "say로 한두 문장 소개 멘트를 연습하라. 기억해 둘 만한 것은 remember. 끝나면 한 일을 한 문장으로 답하라."}]},
]

GUEST_BUDGET_SHARE = 0.7   # 하루 한도의 이 비율을 넘게 썼으면 손님 방문은 쉰다
GUEST_SHOW_SEC = 1800      # 방문이 이보다 길어지면 화면에서 뺀다
GUEST_LEAVE_SEC = 40       # 나가는 걸음 (입구까지 걸어간 뒤 사라짐)
STAFF_RETURN_SEC = 150     # 직원이 마지막 행동 뒤 그 자리에 머무는 시간
GUEST_WALK_SEC = 12        # 손님이 이동·책 살펴보기 뒤에 머무는 시간

_VISIT_PROMPT = ("도서관에 놀러 온 시간이다. 네 관심사에 맞는 책을 찾고 싶다. 순서: "
                 "1) move_to로 관심 있어 보이는 구역으로 간다. "
                 "2) search_books로 직접 찾아보거나 ask_staff로 사서·도슨트에게 묻는다 (한 번은 꼭 직원에게 묻는다). "
                 "3) 마음에 드는 책이 있으면 browse_book으로 그 책 앞에 가서 살펴보고, say로 짧은 혼잣말이나 감상을 한다. "
                 "4) 다음에 기억할 것(찾은 책, 직원 추천 등)은 remember. "
                 "끝나면 오늘 방문을 한 문장으로 답하라.")
# 길 건너 건물에서 일하는 사람들 (공개 기본값은 중립 이름 - [AI 직원]에서 이름·성격을 바꾼다)
# 대표: 사무실, 사서·도슨트의 상사 (직원들이 report로 보고). 큐레이터·청음실 주인: 자기 공간에서 일하다 가끔 서재에 손님으로 온다.
_STAFF_VISIT = ("일터를 잠시 비우고 서재에 손님으로 들르는 시간이다. 순서: "
                "1) move_to로 관심 있는 구역으로 간다. 2) search_books로 찾아보거나 ask_staff로 사서·도슨트에게 묻는다. "
                "3) 마음에 드는 책을 browse_book으로 살펴보고 say로 짧게 감상을 말한다. 4) 일에 쓸 만한 것은 remember. "
                "끝나면 오늘 들른 일을 한 문장으로 답하라 (그 뒤 일터로 돌아간다).")
DEFAULT_STREET = [
    {"id": "boss", "name": "오세진", "job": "대표 (사무실)", "call": ["@대표", "@사장"], "post": "office", "look": 41,
     "goal": "서재와 길 건너 공간들이 잘 돌아가게 살핀다. 직원 보고를 듣고, 필요한 것을 정해 알려 준다.",
     "personality": "침착하고 짧게 말한다. 직원을 믿고 맡기되 숫자와 사실을 챙긴다. 손님에게는 정중하다.",
     "actions": ["move_to", "say", "remember"], "enabled": True,
     "tasks": [{"id": "brief", "title": "하루 정리", "every_min": 1440, "enabled": True,
                "prompt": "대표로서 하루를 정리하는 시간이다. 네가 기억하는 직원 보고와 get_library_stats로 서재 사정을 살피고, "
                          "내일 직원들에게 바라는 점을 remember로 남긴 뒤 사무실에서 say로 한마디 하라. 끝나면 한두 문장으로 답하라."}]},
    {"id": "curator", "name": "윤가람", "job": "큐레이터 (갤러리)", "call": ["@큐레이터"], "post": "gallery", "look": 47,
     "goal": "갤러리에 걸린 표지 그림을 손님에게 소개하고, 서재에서 전시할 만한 작품을 찾는다.",
     "personality": "섬세하고 말에 색이 있다. 표지 그림의 분위기를 잘 짚는다.",
     "actions": ["move_to", "say", "ask_staff", "browse_book", "remember"], "enabled": True,
     "tasks": [{"id": "visit", "title": "서재 나들이", "every_min": 300, "enabled": True, "visit": True, "prompt": _STAFF_VISIT}]},
    {"id": "dj", "name": "배준", "job": "청음실 주인 (재즈 청음실)", "call": ["@DJ", "@디제이"], "post": "jazz", "look": 53,
     "goal": "재즈 청음실을 편안하게 지키고, 음악과 어울리는 책을 찾아 손님에게 권한다.",
     "personality": "느긋하고 유머가 있다. 재즈 이야기를 좋아한다.",
     "actions": ["move_to", "say", "ask_staff", "browse_book", "remember"], "enabled": True,
     "tasks": [{"id": "visit", "title": "서재 나들이", "every_min": 360, "enabled": True, "visit": True, "prompt": _STAFF_VISIT}]},
]
_REPORT_TASK = {"id": "report", "title": "대표에게 보고", "every_min": 1440, "enabled": True,
                "prompt": "하루 일을 대표에게 보고하는 시간이다. 네가 기억하는 일과 get_library_stats로 서재 사정을 보고, "
                          "report로 두세 문장 보고하라. 끝나면 보고한 내용을 한 문장으로 답하라."}
DEFAULT_GUESTS = [
    {"id": "guest_jiho", "kind": "guest", "name": "박지호", "job": "손님 (대학생)", "post": "entrance", "look": 9,
     "goal": "판타지·무협 웹소설과 만화 중에 밤새 읽을 완결작을 찾는다.",
     "personality": "호기심 많고 말이 빠르다. 재밌어 보이면 바로 '오 이거!' 하고 집어 든다.",
     "actions": ["move_to", "say", "ask_staff", "browse_book", "remember"], "enabled": True,
     "tasks": [{"id": "visit", "title": "도서관 방문", "every_min": 180, "enabled": True, "prompt": _VISIT_PROMPT}]},
    {"id": "guest_minseo", "kind": "guest", "name": "최민서", "job": "손님 (회사원)", "post": "entrance", "look": 23,
     "goal": "출퇴근길에 들을 오디오북이나 짧게 끊어 읽기 좋은 추리·스릴러를 찾는다.",
     "personality": "차분하고 꼼꼼하다. 직원에게 정중하게 묻고, 고르기 전에 비교해 본다.",
     "actions": ["move_to", "say", "ask_staff", "browse_book", "remember"], "enabled": True,
     "tasks": [{"id": "visit", "title": "도서관 방문", "every_min": 200, "enabled": True, "prompt": _VISIT_PROMPT}]},
    {"id": "guest_youngsu", "kind": "guest", "name": "김영수", "job": "손님 (은퇴한 교사)", "post": "entrance", "look": 31,
     "goal": "역사·고전을 좋아한다. 요즘 만화도 궁금해서 처음 읽기 좋은 작품을 추천받고 싶다.",
     "personality": "느긋하고 다정하다. 직원에게 '요즘은 뭐가 좋아요?' 하고 묻는 걸 좋아한다.",
     "actions": ["move_to", "say", "ask_staff", "browse_book", "remember"], "enabled": True,
     "tasks": [{"id": "visit", "title": "도서관 방문", "every_min": 240, "enabled": True, "prompt": _VISIT_PROMPT}]},
]

_LOCK = threading.RLock()
_CFG = {"v": None}
_STATE = {"v": None}
_BUSY = set()


# ── 저장 ──
def _p(name):
    return os.path.join(config.data_dir(), name)


def _write(name, data):
    os.makedirs(config.data_dir(), exist_ok=True)
    tmp = _p(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _p(name))


def config_get():
    with _LOCK:
        if _CFG["v"] is None:
            try:
                with open(_p("lib3d_agents.json"), encoding="utf-8") as f:
                    v = json.load(f)
            except (OSError, ValueError):
                v = {}
            v.setdefault("autonomous", True)
            if not isinstance(v.get("agents"), list) or not v["agents"]:
                v["agents"] = copy.deepcopy(DEFAULT_AGENTS)
            if not v.get("guests_v1"):   # 손님이 생기기 전에 저장한 설정에도 손님을 붙인다
                have = {a.get("id") for a in v["agents"]}
                v["agents"] += [copy.deepcopy(g) for g in DEFAULT_GUESTS if g["id"] not in have]
                v["guests_v1"] = True
            if not v.get("street_v1"):   # 길 건너 사람들(대표·큐레이터·청음실 주인)과 대표 보고를 예전 설정에도
                have = {a.get("id") for a in v["agents"]}
                v["agents"] += [copy.deepcopy(g) for g in DEFAULT_STREET if g["id"] not in have]
                for a in v["agents"]:
                    if a.get("id") in ("librarian", "docent"):
                        a.setdefault("boss", "boss")
                    if a.get("id") == "librarian":
                        if "report" not in (a.get("actions") or []):
                            a["actions"] = list(a.get("actions") or []) + ["report"]
                        if not any(t.get("id") == "report" for t in a.get("tasks") or []):
                            a["tasks"] = list(a.get("tasks") or []) + [copy.deepcopy(_REPORT_TASK)]
                v["street_v1"] = True
            _CFG["v"] = v
        return _CFG["v"]


def state():
    with _LOCK:
        if _STATE["v"] is None:
            try:
                with open(_p("lib3d_agents_state.json"), encoding="utf-8") as f:
                    v = json.load(f)
            except (OSError, ValueError):
                v = {}
            for k, d in (("agents", {}), ("log", []), ("board", {}), ("last_run", {}), ("users", {})):
                v.setdefault(k, d)
            _STATE["v"] = v
        return _STATE["v"]


def _save_state():
    with _LOCK:
        _write("lib3d_agents_state.json", state())


def agents(enabled_only=True):
    return [a for a in config_get()["agents"] if a.get("enabled", True) or not enabled_only]


def is_guest(a):
    return (a or {}).get("kind") == "guest"


def staff(enabled_only=True):
    return [a for a in agents(enabled_only) if not is_guest(a)]


def guests(enabled_only=True):
    return [a for a in agents(enabled_only) if is_guest(a)]


def agent(aid):
    return next((a for a in config_get()["agents"] if a["id"] == aid), None)


def save_config(body):
    """설정 화면: {autonomous, agents:[{id, name, job, goal, personality, call, enabled, tasks:[{id,title,every_min,enabled,prompt}]}]}"""
    cfg = copy.deepcopy(config_get())
    if "autonomous" in body:
        cfg["autonomous"] = bool(body["autonomous"])
    for upd in body.get("agents") or []:
        a = next((x for x in cfg["agents"] if x["id"] == upd.get("id")), None)
        if not a:
            continue
        for k in ("name", "job", "goal", "personality"):
            if k in upd:
                a[k] = str(upd[k] or "").strip()[:600] or a[k]
        if "enabled" in upd:
            a["enabled"] = bool(upd["enabled"])
        if "call" in upd:
            calls = [c.strip() for c in re.split(r"[,\s]+", " ".join(upd["call"]) if isinstance(upd["call"], list) else str(upd["call"])) if c.strip()]
            a["call"] = [c if c.startswith("@") else "@" + c for c in calls][:6] or a.get("call", [])
        for tu in upd.get("tasks") or []:
            t = next((x for x in a.get("tasks", []) if x["id"] == tu.get("id")), None)
            if not t:
                continue
            if "enabled" in tu:
                t["enabled"] = bool(tu["enabled"])
            if "every_min" in tu:
                try:
                    t["every_min"] = max(10, min(10080, int(tu["every_min"])))
                except (TypeError, ValueError):
                    raise ValueError("업무 주기는 분 단위 숫자로 적어 주세요.")
            if "prompt" in tu and str(tu["prompt"]).strip():
                t["prompt"] = str(tu["prompt"]).strip()[:2000]
    with _LOCK:
        _write("lib3d_agents.json", cfg)
        _CFG["v"] = cfg
    return cfg


def reset_config():
    with _LOCK:
        try:
            os.remove(_p("lib3d_agents.json"))
        except OSError:
            pass
        _CFG["v"] = None
    cfg = config_get()
    with _LOCK:
        _write("lib3d_agents.json", cfg)
    return cfg


# ── 활동 기록 ──
def add_log(aid, title, text, books=None, private=False):
    a = agent(aid) or {"name": aid}
    entry = {"t": time.time(), "agent": aid, "name": a.get("name"), "job": a.get("job", ""), "title": title, "text": str(text)[:1000]}
    if private:   # 이용자와의 귓속말 문답 - 관리자 화면에만 내용, 로비 안내판에는 '응대'만
        entry["private"] = True
    if books:
        entry["books"] = books[:6]
    with _LOCK:
        state()["log"].append(entry)
        del state()["log"][:-LOG_KEEP]
        _save_state()
    return entry


# ── 월드 도구 (에이전트가 실제로 하는 행동) ──
def _floor_places(floor):
    libs = [l["name"] for l in lib3d.data().get("libraries", []) if l.get("db_type") == floor]
    return list(PLACES) + libs


class WorldTools:
    """에이전트 한 명이 한 번 일하는 동안 쓰는 행동 도구 (상태만 바꾸고, 그리기는 각 화면이)"""
    name = "월드"

    def __init__(self, aid, floor, found=None, user=None, pace=False):
        self.aid, self.floor, self.user = aid, floor or "general", user
        self.found = found if found is not None else []
        self.pace = pace   # 손님: 행동 사이에 걸어갈·둘러볼 시간을 둔다 (LLM이 빨라도 화면에서 보이게)

    def _wait(self, sec):
        if self.pace:
            time.sleep(sec)

    def list_tools(self):
        places = _floor_places(self.floor)
        allowed = set((agent(self.aid) or {}).get("actions") or [])
        tools = [
            {"name": "move_to", "description": "도서관 안에서 걸어서 이동한다. 갈 수 있는 곳: " + ", ".join(places) +
             " (desk=안내 데스크, lobby=로비, entrance=입구, lounge=소파 라운지, elevator=엘리베이터, 나머지는 서가 구역 이름)",
             "inputSchema": {"type": "object", "properties": {"place": {"type": "string", "description": "장소 이름"}}, "required": ["place"]}},
            {"name": "say", "description": "그 자리에서 소리 내어 말한다. 같은 층 모두에게 말풍선과 채팅으로 보인다. 짧게(80자 안).",
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
            {"name": "point_at_book", "description": "책 한 권을 가리킨다(그 책이 있는 서가로 가서 화살표 표시). search_books로 찾은 책 제목을 넣는다.",
             "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
            {"name": "set_board", "description": "로비의 안내판 내용을 바꾼다 (제목 + 줄 여러 개, 줄마다 40자 안, 8줄까지).",
             "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}}},
                             "required": ["title", "lines"]}},
            {"name": "ask_staff", "description": "도서관 직원에게 말을 걸어 묻는다. 직원이 찾아보고 답한다(직원이 직접 걸어가 책을 가리키기도 함). 직원: " +
             ", ".join("%s(%s)" % (_short(x["job"]), x["name"]) for x in staff()),
             "inputSchema": {"type": "object", "properties": {"staff": {"type": "string", "description": "직업이나 이름 (예: 사서)"},
                                                             "question": {"type": "string"}}, "required": ["staff", "question"]}},
            {"name": "browse_book", "description": "책 한 권 앞으로 가서 꺼내 살펴본다. search_books나 직원 답에서 나온 책 제목을 넣는다.",
             "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
            {"name": "report", "description": "상사(%s)에게 보고한다. 상사가 기억해 두었다가 판단에 쓴다. 두세 문장." % _boss_label(self.aid),
             "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
            {"name": "remember", "description": "나중을 위해 기억해 둔다 (도서관에 대한 사실, 이용자 취향 등). 짧은 한 문장.",
             "inputSchema": {"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}},
        ]
        if not _boss_of(self.aid):
            allowed.discard("report")
        return [t for t in tools if t["name"] in allowed]

    def stop(self):
        pass

    def _set(self, **kw):
        with _LOCK:
            st = state()["agents"].setdefault(self.aid, {})
            st.update(kw, floor=self.floor, t=time.time())
            _save_state()

    def call(self, name, args):
        a = agent(self.aid) or {}
        if name == "move_to":
            place = str(args.get("place") or "").strip()
            places = _floor_places(self.floor)
            hit = next((p for p in places if p == place), None) or next((p for p in places if place and (place in p or p in place)), None)
            if not hit:
                return "그런 곳이 없습니다. 갈 수 있는 곳: " + ", ".join(places), True
            self._set(target=hit, book="")
            self._wait(GUEST_WALK_SEC)
            return "%s(으)로 걸어갔습니다." % PLACE_KO.get(hit, hit + " 구역"), False
        if name == "say":
            text = " ".join(str(args.get("text") or "").split())[:160]
            if not text:
                return "할 말이 비었습니다.", True
            self._set(say=text, say_t=time.time())
            lib3d_presence.post("%s (%s)" % (a.get("name", self.aid), _short(a.get("job"))), text, self.floor)
            self._wait(4)
            return "말했습니다.", False
        if name == "ask_staff":
            return self._ask_staff(a, args)
        if name == "report":
            boss = _boss_of(self.aid)
            text = " ".join(str(args.get("text") or "").split())[:400]
            if not boss or not text:
                return "보고할 상사가 없거나 내용이 비었습니다.", True
            with _LOCK:
                notes = state()["agents"].setdefault(boss["id"], {}).setdefault("notes", [])
                notes.append("[%s의 보고] %s" % (a.get("name", self.aid), text))
                del notes[:-NOTES_KEEP]
                _save_state()
            add_log(self.aid, "%s에게 보고" % _short(boss.get("job")), text)
            return "%s에게 보고했습니다." % boss["name"], False
        if name in ("point_at_book", "browse_book"):
            title = str(args.get("title") or "").strip()
            bk = next((b for b in self.found if title and (title in b["title"] or b["title"] in title)), None)
            if not bk:
                return "먼저 search_books로 그 책을 찾아야 가리킬 수 있습니다.", True
            self._set(book=bk["key"], book_title=bk["title"], target="book")
            self._wait(GUEST_WALK_SEC)
            return "'%s'을(를) %s." % (bk["title"], "살펴봤습니다" if name == "browse_book" else "가리켰습니다"), False
        if name == "set_board":
            lines = [str(x)[:60] for x in (args.get("lines") or []) if str(x).strip()][:8]
            title = str(args.get("title") or "").strip()[:40] or "안내"
            with _LOCK:
                state()["board"] = {"title": title, "lines": lines, "by": a.get("name"), "t": time.time()}
                _save_state()
            return "안내판을 바꿨습니다.", False
        if name == "remember":
            note = str(args.get("note") or "").strip()[:200]
            if not note:
                return "기억할 내용이 비었습니다.", True
            with _LOCK:
                notes = state()["agents"].setdefault(self.aid, {}).setdefault("notes", [])
                notes.append(note)
                del notes[:-NOTES_KEEP]
                if self.user:   # 이용자와 이야기하다 기억한 것은 그 이용자 기억에도
                    likes = state()["users"].setdefault(self.user, {}).setdefault("likes", [])
                    likes.append(note)
                    del likes[:-12]
                _save_state()
            return "기억했습니다.", False
        return "없는 행동입니다: " + name, True

    def _ask_staff(self, me, args):
        """손님 → 직원: 질문과 답 모두 그 층 채팅에 공개 (손님은 AI라 귓속말이 필요 없다)"""
        want = str(args.get("staff") or "").strip().lstrip("@")
        question = " ".join(str(args.get("question") or "").split())[:300]
        if not question:
            return "물어볼 것이 비었습니다.", True
        pool = [x for x in staff() if x["id"] != self.aid]   # 자기 자신에게는 묻지 않는다
        st = next((x for x in pool if want and (want in x["job"] or want in x["name"] or any(want == c.lstrip("@") for c in x.get("call", [])))), None) \
            or next(iter(pool), None)
        if not st:
            return "지금 일하는 직원이 없습니다.", True
        key = (st["id"], self.aid)
        with _LOCK:
            if key in _BUSY:
                return "그 직원이 아직 앞 질문에 답하는 중입니다.", True
            _BUSY.add(key)
        me_name = "%s (%s)" % (me.get("name", self.aid), _short(me.get("job")))
        who = "%s (%s)" % (st["name"], _short(st["job"]))
        lib3d_presence.post(me_name, (st.get("call") or ["@"])[0] + " " + question, self.floor)
        self._set(say=question[:80], say_t=time.time())
        found = []
        try:
            out = lib3d_ai.ask(question, [], system=_system(st, self.floor, me.get("name"), True, guest=True),
                               extra=[WorldTools(st["id"], self.floor, found, None)], allow=_allow(True), check=_check(False),
                               need_flag=False, found=found)
        except Exception as error:  # noqa: BLE001 - 손님에게 그대로 알려 준다
            return "직원이 답하지 못했습니다: %s" % error, True
        finally:
            with _LOCK:
                _BUSY.discard(key)
        answer = out.get("answer") or "(답이 없었습니다)"
        lib3d_presence.post(who, answer, self.floor, books=found or None)
        for b in found:   # 직원이 찾은 책은 손님도 살펴볼 수 있게
            if not any(b["key"] == x["key"] for x in self.found):
                self.found.append(b)
        titles = ", ".join(b["title"] for b in found[:8])
        return "%s의 답: %s%s" % (st["name"], answer, ("\n직원이 찾은 책: " + titles) if titles else ""), False


def _boss_of(aid):
    """이 직원의 상사 (설정의 boss, 켜져 있을 때만)"""
    a = agent(aid) or {}
    b = agent(a.get("boss")) if a.get("boss") else None
    return b if b and b.get("enabled", True) and b["id"] != aid else None


def _boss_label(aid):
    b = _boss_of(aid)
    return "%s %s" % (b["name"], _short(b.get("job"))) if b else "상사"


def _short(job):
    return re.sub(r"\s*\(.*\)\s*$", "", str(job or "")) or "직원"


def _system(a, floor, user=None, viewer=False, guest=False):
    st = state()["agents"].get(a["id"], {})
    notes = st.get("notes") or []
    places = _floor_places(floor)
    others = ", ".join("%s(%s, %s)" % (x["name"], _short(x["job"]), " ".join(x.get("call", [])[:1])) for x in staff() if x["id"] != a["id"])
    lines = [
        "너는 BookOasis 3D 도서관(개인 서재를 3D 서점 건물로 만든 메타버스)에서 일하는 AI 직원 '%s'이다. 직업: %s." % (a["name"], a["job"]),
        "목표: " + a.get("goal", ""),
        "성격: " + a.get("personality", ""),
        "지금 있는 층: %s층(%s). 이 층의 장소·구역: %s." % (floor, {"general": "일반", "adult": "성인", "audiobook": "오디오북", "video": "비디오"}.get(floor, floor), ", ".join(places)),
        "동료: " + (others or "없음") + ". 동료가 더 잘하는 일이면 이용자에게 그 동료를 불러 보라고 권한다.",
        "일하는 곳: %s." % PLACE_KO.get(a.get("post"), "서재 안") + (" (서재 1층 밖, 길 건너 건물 1층)" if a.get("post") in ROOM_POSTS else ""),
        "너는 말만 하는 캐릭터가 아니다. 도서관 안에서 실제로 움직이고 행동하려면 월드 도구(move_to·say·point_at_book·set_board·remember)를 쓴다. "
        "책·서재 정보는 BookOasis 도구(search_books 등)로 확인하고, 확인 못 한 것은 추측이라고 밝힌다. db_type은 general·adult·audiobook·video.",
        "답은 한국어로, 네 성격대로 짧게. 찾은 책 목록은 화면이 답 아래 따로 붙이므로 답에서는 요약만.",
    ]
    boss = _boss_of(a["id"])
    if boss:
        lines.append("상사: %s(%s). 중요한 일·하루 일은 report로 보고하고, 이용자에게는 '대표님'처럼 부른다." % (boss["name"], _short(boss.get("job"))))
    team = [x for x in staff() if x.get("boss") == a["id"]]
    if team:
        lines.append("너에게 보고하는 직원: " + ", ".join("%s(%s)" % (x["name"], _short(x["job"])) for x in team) + ".")
    if notes:
        lines.append("네가 기억하고 있는 것: " + " / ".join(notes[-12:]))
    if user:
        u = state()["users"].get(user, {})
        if u.get("likes"):
            lines.append("이 이용자(%s)에 대해 기억하는 것: %s" % (user, " / ".join(u["likes"][-6:])))
        lines.append("지금 말을 건 %s: %s%s." % ("손님" if guest else "이용자", user, " (관람자 계정)" if viewer and not guest else ""))
        if guest:
            lines.append("이 대화는 그 층 모두가 채팅으로 본다. 답은 두세 문장으로.")
    return "\n".join(lines)


VIEWER_TOOLS = {"search_books", "get_random_book", "now", "weather", "move_to", "say", "point_at_book", "remember"}


def _allow(viewer):
    def ok(shown, real, client):
        if client.name == "월드":
            return True
        if not viewer:
            return True
        return client.name in ("bookoasis", "기본 도구") and real in VIEWER_TOOLS
    return ok


def _check(adult):
    def chk(name, args):
        if not adult and str(args.get("db_type") or "") == "adult":
            return "성인 서재는 이 이용자에게 보여 줄 수 없습니다."
        return None
    return chk


def _guest_system(a, floor):
    st = state()["agents"].get(a["id"], {})
    notes = st.get("notes") or []
    lines = [
        "너는 BookOasis 3D 도서관(개인 서재를 3D 서점 건물로 만든 메타버스)에 놀러 온 손님 '%s'이다. %s." % (a["name"], a["job"]),
        "찾는 것: " + a.get("goal", ""),
        "성격: " + a.get("personality", ""),
        "지금 있는 층: %s층. 장소·구역: %s." % (floor, ", ".join(_floor_places(floor))),
        "직원: " + ", ".join("%s(%s)" % (x["name"], _short(x["job"])) for x in staff()) + ".",
        "너는 실제로 도서관 안을 걸어 다닌다. 행동은 월드 도구(move_to·say·ask_staff·browse_book·remember)로 한다. "
        "책은 search_books(db_type은 general·audiobook·video, 성인 서재는 보지 않는다)로 찾거나 직원에게 묻는다. "
        "say는 짧게(40자 안), 네 성격대로. 손님답게 행동하고 직원 흉내는 내지 않는다.",
    ]
    if notes:
        lines.append("지난 방문에서 기억하는 것: " + " / ".join(notes[-8:]))
    return "\n".join(lines)


GUEST_TOOLS = {"search_books", "get_random_book", "now", "weather"}


def _guest_allow(shown, real, client):
    if client.name == "월드":
        return True
    return client.name in ("bookoasis", "기본 도구") and real in GUEST_TOOLS


def guest_budget_ok():
    b = lib3d_ai.budget()
    return not b["limit"] or b["used"] < b["limit"] * GUEST_BUDGET_SHARE


def match_call(text):
    """'@사서 질문' → (에이전트, 질문) 또는 (None, None)"""
    text = " ".join(str(text or "").split())
    for a in staff():
        for c in sorted(a.get("call", []), key=len, reverse=True):
            if text == c or text.startswith(c + " "):
                return a, text[len(c):].strip()
    return None, None


def talk(a, username, question, floor, admin, adult, display=None):
    """이용자가 부름: 질문·답은 부른 사람에게만(채팅 귓속말), 직원의 say는 그 층 모두에게"""
    if not lib3d_ai.configured():
        raise ValueError("AI 설정(연결 방식·주소·모델)을 먼저 해 주세요 - 3D 서재 설정 > AI 설정.")
    if not question:
        raise ValueError("'%s 질문'처럼 할 말을 적어 주세요." % a["call"][0])
    key = (a["id"], username)
    with _LOCK:
        if key in _BUSY:
            raise ValueError("%s이(가) 앞 이야기에 답하는 중입니다. 잠시만요." % a["name"])
        _BUSY.add(key)
    who = "%s (%s)" % (a["name"], _short(a["job"]))
    lib3d_presence.post(display or username, a["call"][0] + " " + question, floor, to=username)
    lib3d_presence.post(who, "…", floor, to=username)

    def run():
        found = []
        books = None
        try:
            hist = state()["users"].get(username, {}).get("hist", {}).get(a["id"], [])
            out = lib3d_ai.ask(question, hist, system=_system(a, floor, display or username, not admin),
                               extra=[WorldTools(a["id"], floor, found, username)], allow=_allow(not admin), check=_check(adult), need_flag=False, found=found)
            answer = out.get("answer") or "(답이 비어 있습니다)"
            books = out.get("books") or None
            with _LOCK:
                u = state()["users"].setdefault(username, {})
                h = u.setdefault("hist", {}).setdefault(a["id"], [])
                h.append({"q": question, "a": out.get("answer") or ""})
                del h[:-6]
                _save_state()
            acts = [t for t in out.get("tools", []) if t in ("move_to", "say", "point_at_book", "set_board")]
            if acts:
                add_log(a["id"], "%s님 응대" % (display or username), question[:60] + " → " + answer[:160], books, private=True)
        except Exception as error:  # noqa: BLE001
            answer = "죄송해요, 지금은 답하지 못했어요: %s" % error
        finally:
            with _LOCK:
                _BUSY.discard(key)
        lib3d_presence.post(who, answer, floor, to=username, books=books)
    threading.Thread(target=run, daemon=True).start()


# ── 자율 업무 ──
def run_task(a, task):
    """업무 하나 (이용자 없이). 층은 일반 층을 우선"""
    floors = sorted({l["db_type"] for l in lib3d.data().get("libraries", []) if l.get("db_type") != "adult"}, key=lambda k: (k != "general", k))
    floor = "general" if "general" in floors or not floors else floors[0]
    found = []
    world = WorldTools(a["id"], floor, found, pace=is_guest(a))
    if is_guest(a):   # 손님: 입구로 들어와서 → 둘러보고 → 입구로 나간다
        with _LOCK:
            st = state()["agents"].setdefault(a["id"], {})
            st.pop("left_t", None)
            st["visit_t"] = time.time()
        world._set(target="entrance", book="", say="")
        world._wait(5)   # 입구에 들어서는 모습
        try:
            out = lib3d_ai.ask("[%s] %s" % (task["title"], task["prompt"]), [], system=_guest_system(a, floor), extra=[world],
                               allow=_guest_allow, check=_check(False), need_flag=False, found=found)
        finally:
            world._wait(4)
            world._set(target="entrance", book="", left_t=time.time())
        add_log(a["id"], task["title"], out.get("answer") or "", out.get("books"))
        return out
    if task.get("visit"):   # 길 건너 사람의 서재 나들이: 입구로 들어와 손님처럼 둘러보고 → 일터로 돌아간다
        world.pace = True
        world._set(target="entrance", book="", say="")
        world._wait(5)
        sysm = _system(a, floor) + "\n지금은 네 일터를 잠시 나와 서재에 손님으로 들렀다. 직원 흉내는 내지 말고 손님답게 둘러본다. 성인 서재는 보지 않는다."
        try:
            out = lib3d_ai.ask("[%s] %s" % (task["title"], task["prompt"]), [], system=sysm, extra=[world],
                               allow=_guest_allow, check=_check(False), need_flag=False, found=found)
        finally:
            world._wait(4)
            world._set(target=a.get("post") or "entrance", book="", say="")
        add_log(a["id"], task["title"], out.get("answer") or "", out.get("books"))
        return out
    prompt = "[업무 시간: %s] %s" % (task["title"], task["prompt"])
    out = lib3d_ai.ask(prompt, [], system=_system(a, floor), extra=[world], allow=lambda s, r, c: True,
                       check=_check(False), need_flag=False, found=found)
    add_log(a["id"], task["title"], out.get("answer") or "", out.get("books"))
    return out


def run_now(aid, tid):
    a = agent(aid)
    t = next((x for x in (a or {}).get("tasks", []) if x["id"] == tid), None)
    if not a or not t:
        raise ValueError("없는 업무입니다.")
    if not lib3d_ai.configured():
        raise ValueError("AI 설정(연결 방식·주소·모델)을 먼저 해 주세요.")

    def go():
        try:
            run_task(a, t)
        except Exception as error:  # noqa: BLE001
            add_log(aid, t["title"], "하지 못했습니다: %s" % error)
        with _LOCK:
            state()["last_run"]["%s/%s" % (aid, tid)] = time.time()
            _save_state()
    threading.Thread(target=go, daemon=True).start()


def _loop():
    time.sleep(20)
    while True:
        try:
            cfg = config_get()
            nobody = lib3d_presence.active_count() == 0   # 서재에 아무도 없으면 직원·손님 모두 쉰다 (AI 호출도 없음)
            if nobody != _IDLE["v"]:
                _IDLE["v"] = nobody
                log.info("3D 서재 AI 직원: %s", "아무도 없어 쉽니다" if nobody else "사람이 들어와 다시 일합니다")
            if cfg.get("autonomous") and lib3d_ai.configured() and not nobody:
                due = []
                for a in agents():
                    for t in a.get("tasks", []):
                        if not t.get("enabled", True):
                            continue
                        k = "%s/%s" % (a["id"], t["id"])
                        if is_guest(a) and not guest_budget_ok():
                            continue
                        if time.time() - state()["last_run"].get(k, 0) >= t.get("every_min", 60) * 60:
                            due.append((a, t, k))
                if due:
                    a, t, k = random.choice(due)   # 한 번에 하나씩
                    with _LOCK:
                        state()["last_run"][k] = time.time()
                        _save_state()
                    b = lib3d_ai.budget()
                    if b["limit"] and b["used"] >= b["limit"]:
                        add_log(a["id"], t["title"], "오늘 AI 호출 한도를 다 써서 다음으로 미뤘습니다.")
                    else:
                        try:
                            run_task(a, t)
                        except Exception as error:  # noqa: BLE001
                            log.warning("AI 직원 %s/%s 실패: %s", a["id"], t["id"], error)
                            add_log(a["id"], t["title"], "하지 못했습니다: %s" % error)
        except Exception:  # noqa: BLE001
            log.exception("AI 직원 자율 업무 루프")
        time.sleep(30)


_STARTED = {"v": False}
_IDLE = {"v": False}


def start():
    if _STARTED["v"]:
        return
    _STARTED["v"] = True
    threading.Thread(target=_loop, name="lib3d-agents", daemon=True).start()


# ── 화면에 보낼 것 ──
def public(floor):
    """3D 화면용: 직원들(위치·말·가리키는 책), 안내판, 최근 활동"""
    st = state()
    out = []
    now = time.time()
    for a in agents():
        s = st["agents"].get(a["id"], {})
        here = s.get("floor") == floor
        if is_guest(a):   # 손님은 방문 중에만, 그 층에만
            if not here or now - s.get("visit_t", 0) > GUEST_SHOW_SEC or (s.get("left_t") and now - s["left_t"] > GUEST_LEAVE_SEC):
                continue
        keep = GUEST_SHOW_SEC if is_guest(a) else STAFF_RETURN_SEC   # 직원은 일을 마치고 잠시 뒤 제자리로
        out.append({"id": a["id"], "kind": a.get("kind", "staff"), "name": a["name"], "job": _short(a["job"]), "call": (a.get("call") or [""])[0], "post": a.get("post", "lobby"),
                    "look": a.get("look", 1), "target": s.get("target") if here and now - s.get("t", 0) < keep else "",
                    "say": s.get("say") if here and now - s.get("say_t", 0) < 12 else "",
                    "book": s.get("book") if here and now - s.get("t", 0) < keep else "", "book_title": s.get("book_title", "")})
    logs = []
    for e in st["log"][-8:][::-1]:
        e = dict(e)
        e.pop("books", None)
        if e.pop("private", False):
            e["title"], e["text"] = "이용자 응대", "이용자를 도와 책을 찾아 드렸어요." if e.get("agent") == "librarian" else "이용자를 안내했어요."
        logs.append(e)
    return {"agents": out, "board": st.get("board") or {}, "log": logs}


def admin_info():
    cfg = config_get()
    st = state()
    return {"config": cfg, "last_run": st["last_run"], "present": lib3d_presence.active_count(), "log": st["log"][-40:][::-1], "budget": lib3d_ai.budget(),
            "notes": {k: v.get("notes", []) for k, v in st["agents"].items()}, "configured": lib3d_ai.configured()}
