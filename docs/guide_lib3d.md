# BookOasis 3D 서재 가이드

BookOasis 서재를 모던 서점 건물로 지어 걸어 다니며 둘러보는 화면입니다(사이드바 **BookOasis 3D 서재**, 주소 `/library3d`).
세션(일반·성인·오디오북·비디오)마다 한 층, 보관함마다 서가 구역, 작품마다 책장의 책(표지)으로 진열하고, 그 자리에서 읽거나 BookOasis 화면으로 넘어갈 수 있습니다.

## 1. 켜기

`.env`에 아래를 넣고 다시 시작합니다. 기본값은 꺼짐(`false`)입니다.

```env
LIB3D_ENABLED=true

# BookOasis DB (3D 서재가 보관함·작품 목록을 여기서 읽는다) - {db_type}은 세션 이름으로 바뀐다
BOOKOASIS_DB_URL=mysql://bookoasis:비밀번호@192.168.0.31:3306/bookoasis_{db_type}
#  SQLite면: BOOKOASIS_DB_URL=sqlite:////BookOasis경로/db/{db_type}.db
BOOKOASIS_DB_TYPES=general,adult,audiobook,video

# BookOasis 주소 (표지 /covers/… 와 작품 상세·BookOasis 뷰어 링크)
BOOKOASIS_URL=http://127.0.0.1:5930
# 위 주소가 서버 안에서만 통하면, 브라우저가 여는 주소를 따로
LIB3D_PUBLIC_URL=http://192.168.0.10:5930
```

```bash
cd /mnt/bookoasis_assistant && git pull && systemctl restart bookoasis_assistant
# 도커: cd /opt/bookoasis_assistant && git pull && docker compose up -d --build
```

사이드바에 **BookOasis 3D 서재**가 생기고, 그 아래 **둘러보기 · 설정 · 인물 수 · 창밖 풍경 · 3D 모형 · AI 설정** 메뉴가 나옵니다.

### 요구 사항
- **BookOasis DB에 읽기 접근**이 필요합니다. MariaDB/MySQL은 `PyMySQL` 패키지(`requirements.txt`에 포함), SQLite는 같은 서버에서 파일을 읽을 수 있어야 합니다.
- **서재 안에서 읽기**(자체 뷰어)는 BookOasis DB의 `books.file_path` 경로 그대로 파일을 엽니다. 이 프로그램이 BookOasis와 **같은 경로로 책 파일을 볼 수 있어야** 합니다(같은 서버·같은 마운트, 도커면 같은 경로로 볼륨 연결). 경로가 다르면 "BookOasis 뷰어로 읽기"를 쓰세요.
- 브라우저는 WebGL이 되는 최신 브라우저(크롬·엣지·사파리·파이어폭스). 3D 라이브러리(three.js)와 사람·가구 모형은 인터넷(cdnjs·jsdelivr)에서 받습니다.

### 그 밖의 `.env` (보통 비워 둠)

| 키 | 기본 | 설명 |
|---|---|---|
| `LIB3D_PER_LIBRARY` | `120` | 보관함마다 책장에 놓을 최근 작품 수 (10~400) |
| `LIB3D_BOOK_URL` | (비움) | 작품 상세 주소를 다른 형식으로 (`{id}` `{library_id}` `{db_type}` `{series}` `{bookoasis}`) |
| `LIB3D_COVER_URL` | (비움) | BookOasis에 표지가 없을 때 쓸 표지 주소 형식 |

## 2. 둘러보기

- **이동**: W A S D · 방향키 (휴대폰은 화면 왼쪽 아래 조이스틱), **둘러보기**: 마우스 끌기 / 화면 밀기
- **층 이동**: 아래 [층] 버튼 또는 로비 왼쪽 벽의 엘리베이터를 누름. 1층 일반 · 2층 성인 · 3층 오디오북 · 4층 비디오 (고른 보관함이 있는 세션만)
- **지도**: 구역(보관함) 목록에서 눌러 바로 그 앞으로 이동. **입구로**: 처음 자리로
- **책 누르기** → 작품 카드: **여기서 읽기**(만화·웹툰 zip/cbz·그림 폴더, epub, pdf - 펼친 책 모양에 책장 넘김, 만화는 오른쪽→왼쪽도, 읽던 곳은 이 브라우저에 기억) · **BookOasis 뷰어로 읽기**(키오스크 모드로 열었다가 돌아옴) · **작품 상세(BookOasis)**
- 입구 벽·안쪽 벽의 **표지 포스터**도 누르면 같은 작품 카드가 열립니다.
- 표지는 가까이 간 책부터 BookOasis에서 받아 옵니다(작게 줄여 `DATA_DIR/lib3d_covers`에 저장).

## 3. 설정 (모두 `DATA_DIR/lib3d.json`에 저장, 저장하면 바로 반영)

| 메뉴 | 고르는 것 | lib3d.json 키 |
|---|---|---|
| **설정** | 보여 줄 보관함 (세션별 묶음 체크, [전부 보기]) - 고른 것이 없는 세션은 층이 없어짐 | `libraries` |
| **인물 수** | 층(열) × 인물 종류(행)마다 0~20명, 비우면 자동. 걷는·책 고르는·서서 읽는·벤치·대화(쌍) 손님, 안내 직원, 스톰트루퍼, 엘프, 숨은 인물 | `people` |
| **창밖 풍경** | 시간(자동·낮·노을·밤) · 계절(자동·봄·여름·가을·겨울) · 날씨(맑음·흐림·비·눈·자동). 자동은 브라우저 시계·지금 달·날마다 바뀌는 날씨 | `outside` |
| **3D 모형** | 라운지 소파·의자, 화분, 바깥 차를 **지금 그대로**(코드로 그린 것, 가벼움) 또는 **3D 모형 파일**(처음 한 번 약 14MB, 그래픽 부담 큼) | `models` |
| **AI 설정** | 손님 대화·질문하기 (아래 4장) | `.env`의 `LIB3D_AI_*` |

3D 모형 파일 출처: GlamVelvetSofa·ChairDamaskPurplegold (© Wayfair, Eric Chadwick, CC BY 4.0), DiffuseTransmissionPlant (© Darmstadt Graphics Group, CC BY 4.0) - Khronos glTF Sample Assets / Ferrari 458 Italia (vicent091036, three.js 예제). 사람 모형은 three.js 예제의 Xbot·Michelle·readyplayer.me·스톰트루퍼·엘프를 씁니다.

## 4. AI: 손님 대화 · 질문하기 (선택)

[3D 서재 > AI 설정]에서 켭니다. 값은 `.env`에 저장됩니다(파일 권한 0600). 유료 API면 호출마다 요금이 듭니다.

| 항목 | `.env` 키 | 설명 |
|---|---|---|
| 연결 방식 | `LIB3D_AI_PROVIDER` | `openai`(기본) = OpenAI 호환 `/chat/completions` (LiteLLM·Ollama·LM Studio·OpenAI 등, 추가 패키지 없음) / `anthropic` = Claude API (`pip install anthropic` 필요) |
| API 주소 | `LIB3D_AI_BASE_URL` | OpenAI 호환일 때. 예 `http://192.168.0.26:4000/v1` (뒤에 `/chat/completions`를 붙여 부름) |
| API 키 | `LIB3D_AI_API_KEY` | anthropic에서 비우면 `ANTHROPIC_API_KEY` |
| 모델 | `LIB3D_AI_MODEL` | 게이트웨이에 등록된 이름 그대로 (예 `gemini-free3_1`). anthropic은 비우면 `claude-opus-5-5` |
| 손님 대화 | `LIB3D_AI_CHAT`, `LIB3D_AI_CHAT_SEC` | 층마다 두 손님이 무작위 책 한 권(제목·작가·장르·줄거리)을 두고 나누는 말을 말풍선으로. 간격(기본 60초)보다 자주 부르지 않고, 가까이 있고 탭이 보일 때만 부름 |
| 질문하기 | `LIB3D_AI_ASK`, `LIB3D_MCP_COMMAND` | 아래 [질문] 버튼 → LLM이 **BookOasis MCP**의 읽기 전용 도구로 서재 데이터를 찾아 답함 (모델이 도구 호출을 지원해야 함) |

### BookOasis MCP 실행 명령

질문하기는 BookOasis에 들어 있는 MCP 서버(`tools/mcp_server.py`, stdio)를 이 프로그램이 직접 실행해서 씁니다. 쓰기·제안 도구는 붙이지 않습니다.

```text
# BookOasis가 같은 서버에 직접 설치돼 있으면
python3 /BookOasis경로/tools/mcp_server.py

# BookOasis가 도커 컨테이너(bookoasis)로 돌면
docker exec -i bookoasis python3 tools/mcp_server.py
```

- 이 프로그램 자체를 도커로 돌리면 컨테이너 안에서 `docker` 명령을 쓸 수 없는 경우가 많습니다. 그때는 이 프로그램을 서버에 직접 설치하거나, 컨테이너에 도커 소켓(`/var/run/docker.sock`)과 docker CLI를 넣어야 합니다.
- 입력한 뒤 **[MCP 연결 시험]** 을 눌러 "연결됨 - 쓸 수 있는 도구 N개"가 나오는지 확인하세요.

## 5. 자주 막히는 곳

| 증상 | 확인할 것 |
|---|---|
| "BookOasis 3D 서재가 꺼져 있습니다" | `.env`에 `LIB3D_ENABLED=true` 후 다시 시작 |
| "BookOasis 보관함을 읽지 못했습니다" | `BOOKOASIS_DB_URL`·`BOOKOASIS_DB_TYPES`, DB 계정 권한, 이 서버에서 DB 접속 가능한지 |
| 표지가 색 상자·제목 표지로만 나옴 | `BOOKOASIS_URL`이 이 서버에서 열리는지 (`/covers/…`), BookOasis에 표지가 있는지 |
| 작품 상세·BookOasis 뷰어가 안 열림 | 브라우저에서 열리는 주소를 `LIB3D_PUBLIC_URL`에 |
| 여기서 읽기에서 쪽이 안 나옴 | 쪽에 이유가 적힘. 대개 `books.file_path` 경로를 이 서버에서 볼 수 없음 (같은 경로로 마운트) |
| "3D 라이브러리(three.js)를 불러오지 못했습니다" | 브라우저가 cdnjs.cloudflare.com·cdn.jsdelivr.net에 접속 가능한지 |
| 사람이 공·원통 모양으로만 나옴 | 사람 모형(jsdelivr)을 아직 받는 중이거나 못 받음 - 브라우저 콘솔의 `3D 서재 사람 모형` 메시지 |
| 화면이 버벅임 | [3D 모형]을 "지금 그대로"로, [인물 수]를 줄이기, 브라우저 하드웨어 가속 켜기 |
| AI: "API 키가 맞지 않습니다" / "연결하지 못했습니다" | API 주소 끝이 `/v1`까지인지, 키, 게이트웨이에 모델 이름이 있는지 |
| 질문하기가 도구를 안 씀 | 모델이 도구 호출(function calling)을 지원하는지, [MCP 연결 시험] 결과 |
