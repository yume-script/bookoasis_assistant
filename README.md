# BookOasis 보조 프로그램 · 독립형 (bookoasis_assistant)

BookOasis 플러그인으로 쓰던 세 가지를 **BookOasis 밖에서 따로 도는 프로그램 하나**로 옮겼습니다. 관리 화면·포트·비밀번호·`.env`는 하나이고,
각 모듈의 무거운 일은 모듈마다 따로 도는 작업 프로세스가 합니다. 중심은 웹툰 다운로더이고 관리 화면도 웹툰 다운로더로 열립니다(드라이브 변경 감시는 `/watch`) (한쪽이 느려지거나 죽어도 다른 쪽은 영향 없음).

| 모듈 | 원본 | 하는 일 | 켜기 |
|---|---|---|---|
| **웹툰 다운로더** | [webtoon_manager](https://github.com/yume-script/webtoon_manager) v1.39.3 | 네이버웹툰·카카오웹툰·카카오웹소설 구독/다운로드, kavita.yaml 등 | `WTM_ENABLED=true` (기본 · 첫 화면) |
| **드라이브 변경 감시** | [gdrive_watch](https://github.com/yume-script/gdrive_watch) v1.18.8 | Google Drive·로컬 폴더 변경 감지 → rclone VFS 새로고침 → 바뀐 폴더만 BookOasis 부분 스캔 | `GDW_ENABLED=true` (기본, rclone 마운트를 쓸 때) · **리눅스 전용 - 윈도우에서는 사용 불가** |
| **미니게임** | [ym_mini_game](https://github.com/yume-script/ym_mini_game) v2.0.2 | 테트리스·지뢰찾기·오목·홀덤 등 12종 (브라우저에서만 돔, 서버 부하 없음) | `MINI_ENABLED=true` (기본) |

감지·다운로드 로직과 화면은 플러그인과 같고, 플러그인이라서 생기던 제약만 걷어냈습니다.
두 모듈을 함께 켜면 **웹툰 회차가 라이브러리에 들어가는 즉시 드라이브 변경 감시가 VFS 새로고침 → BookOasis 부분 스캔**을 합니다(Drive 변경 감지를 기다리지 않음).

## 왜 독립형인가 (플러그인과 달라진 점)

| | 플러그인 (gdrive_watch) | 독립형 (이 저장소) |
|---|---|---|
| 실행 | BookOasis가 `fork`로 워커를 떼어 냄 (`ALLOW_PLUGIN_SUBPROCESS=true` 필요, 좀비 방지용 `--daemon`) | `app.py` 하나를 systemd/도커로 실행, 워커는 그 자식 프로세스 |
| 자동 시작 | 모듈 로드·화면 열 때만 확인 | 감독 스레드가 30초마다 확인, **워커가 죽으면 다시 시작** (연달아 죽으면 최대 10분 간격) |
| 보관함 목록 갱신 | 화면을 열 때만 (안 열면 cron·RC 주소 변경이 워커에 반영 안 됨) | 상주 스레드가 계속 갱신 (60초 캐시), DB가 잠깐 끊겨도 이전 목록 유지 |
| 설정 | 플러그인 설정(BookOasis DB) + `watch.json`의 env 두 군데 | **`.env` 한 곳** (화면에서 저장해도 `.env`의 해당 줄만 바뀜) |
| BookOasis DB | 플러그인 게이트웨이로만 접근 → 중복 확인 스레드를 Flask 앱 문맥에 얹고, 여러 BookOasis 프로세스 중 하나만 돌도록 파일 잠금 | `.env`의 주소로 **직접 연결** (MariaDB/MySQL·SQLite). DB 없이 보관함을 JSON으로 적어 쓸 수도 있음 |
| 관리 화면 | BookOasis 카테고리 탭 (BookOasis 관리자 세션) | 자체 웹 서버 (표준 라이브러리), YMPlayer와 같은 로그인 화면·세션 쿠키 |
| BookOasis 재시작·업데이트 | 감시도 같이 멈춤/재시작 | 영향 없음 (스캔 요청만 BookOasis가 받을 때까지 재시도) |

워커와 주고받는 파일(`runtime.json`, `state.db`, `heartbeat.json`, `*.flag`)은 그대로라 **플러그인 데이터 폴더를 복사해 오면 기록·체크포인트가 이어집니다** (아래 "플러그인에서 옮겨 오기").

## 요구 사항
- Python 3.9+ (워커·웹 화면은 표준 라이브러리만 사용)
- BookOasis DB(MariaDB/MySQL)에 직접 붙을 때만 `PyMySQL` (`requirements.txt`)
- rclone 실행 파일과 rclone.conf
- **경로 일치**: 감시하는 마운트가 이 프로그램에서도 **BookOasis 보관함 경로와 같은 경로**로 보여야 합니다.
  변경된 파일 경로를 BookOasis 보관함 경로(`physical_path`)와 그대로 비교해 어느 보관함인지 찾기 때문입니다.
  도커라면 BookOasis 컨테이너와 같은 대상 경로로 마운트하세요.

## 설치 (서버에 직접)
```bash
git clone https://github.com/yume-script/bookoasis_assistant.git /opt/bookoasis_assistant
cd /opt/bookoasis_assistant
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cp env.example .env && chmod 600 .env    # 값 채우기 (아래 표)
venv/bin/python app.py --check           # 설정 점검: rclone, BookOasis DB, WEBHOOK_TOKEN
venv/bin/python app.py                   # 관리 화면 http://127.0.0.1:5931/
```
systemd로 상주시키기:
```bash
sudo cp deploy/bookoasis_assistant.service /etc/systemd/system/   # 경로·User 수정
sudo systemctl daemon-reload && sudo systemctl enable --now bookoasis_assistant
```
종료 신호(SIGTERM)를 받으면 워커가 진행 중인 작업을 마치고 끝날 때까지 최대 40초 기다립니다 (`TimeoutStopSec=60`).

## 이전 이름(gdrive_watch_sa)에서 옮기기
저장소·서비스·설치 폴더 이름이 `gdrive_watch_sa` → `bookoasis_assistant`로 바뀌었습니다. 설정(`.env`)과 기록(`DATA_DIR=data`)은
설치 폴더 안에 있으므로 폴더째 옮기면 그대로 이어집니다.
```bash
systemctl stop gdrive_watch_sa && systemctl disable gdrive_watch_sa
mv /mnt/gdrive_watch_sa /mnt/bookoasis_assistant
cd /mnt/bookoasis_assistant
git remote set-url origin https://github.com/yume-script/bookoasis_assistant.git && git pull
sed 's#gdrive_watch_sa#bookoasis_assistant#g' /etc/systemd/system/gdrive_watch_sa.service \
  > /etc/systemd/system/bookoasis_assistant.service
rm /etc/systemd/system/gdrive_watch_sa.service
systemctl daemon-reload && systemctl enable --now bookoasis_assistant
journalctl -u bookoasis_assistant -n 30 --no-pager
```

## 설치 (도커)
```bash
cp env.example .env                       # WEB_USER/WEB_PASSWORD(첫 관리자), RCLONE_CONFIG=/config/rclone/rclone.conf 등
cp docker-compose.example.yml docker-compose.yml   # 마운트 경로를 BookOasis와 같게
docker compose up -d --build
```
- `.env`는 `env_file`이 아니라 **파일로 마운트**합니다. 화면에서 실행 환경을 저장하면 이 파일에 씁니다(같은 inode에 제자리 쓰기라 파일 단위 마운트여도 됨).
- compose의 `environment:`에 적은 키는 `.env`보다 우선합니다. 화면에서 바꿀 값(RCLONE_*, BOOKOASIS_URL, WEBHOOK_TOKEN, AUTO_START)은 적지 마세요.
- rclone.conf는 파일이 아니라 **디렉터리째** 마운트하세요 (파일 단위 바인드 마운트는 rclone이 토큰을 저장할 때 `device or resource busy`).

## 설치 (윈도우)
웹툰 다운로더와 미니게임은 윈도우에서도 돕니다. **드라이브 변경 감시는 리눅스 전용**이라(리눅스 경로·inotify·/proc 사용)
윈도우에서는 자동으로 꺼집니다.
```bat
git clone https://github.com/yume-script/bookoasis_assistant.git C:\bookoasis_assistant
cd C:\bookoasis_assistant
py -3 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy env.example .env
rem .env: GDW_ENABLED=false, WTM_DOWNLOAD_ROOT=D:\Webtoon\naver 처럼 윈도우 경로로
venv\Scripts\python app.py --check
venv\Scripts\python app.py
```
- 계속 켜 두려면 작업 스케줄러(로그온 시 / 시스템 시작 시, "가장 높은 수준의 권한으로 실행")에
  `C:\bookoasis_assistant\venv\Scripts\python.exe app.py`, 시작 위치 `C:\bookoasis_assistant`로 등록하세요
  (서비스로 돌리려면 NSSM 같은 도구를 씁니다).
- 경로가 260자를 넘을 수 있으면(긴 작품 제목 + 깊은 폴더) 윈도우의 "긴 경로 사용"(LongPathsEnabled)을 켜 두세요.
- 명령 결과를 파일로 저장할 때(`python -m wtm.simulate > out.txt`)도 UTF-8로 써서 한글이 깨지지 않습니다.

## .env
| 변수 | 기본값 | 설명 |
|---|---|---|
| `WEB_HOST` / `WEB_PORT` | `127.0.0.1` / `5931` | 관리 화면 주소. 루프백이 아닌 주소에 열 때 로그인 계정이 하나도 없으면 시작 거부 |
| `WEB_USER` / `WEB_PASSWORD` | `admin` / (없음) | **첫 관리자 계정** (사용자가 없을 때 한 번만 만듦). 비우면 첫 화면에서 관리자 계정 만들기 |
| `WEB_ALLOW_NO_AUTH` | `false` | 리버스 프록시에서 인증할 때만 `true` (비밀번호 없이 외부 주소 허용) |
| `DATA_DIR` | `data` | state.db, 로그, watch.json 등. 상대 경로는 저장소 기준 |
| `LOG_LEVEL` | `INFO` | 서비스 로그(표준 출력) 수준. 워커 로그는 `DATA_DIR/worker.log` |
| `RCLONE_PATH` | `rclone` | rclone 실행 파일 |
| `RCLONE_CONFIG` | (rclone 기본 위치) | rclone.conf 경로 |
| `BOOKOASIS_URL` | `http://127.0.0.1:5930` | 스캔 요청(`/api/webhook/scan`)을 보낼 BookOasis 주소 |
| `WEBHOOK_TOKEN` | (없음) | BookOasis `.env`의 `WEBHOOK_TOKEN`과 같은 값 |
| `AUTO_START` | `true` | 시작 시 워커 자동 시작 + 죽으면 다시 시작. 화면의 [중지]는 다시 [시작]할 때까지 유지 |
| `BOOKOASIS_DB_URL` | (없음) | BookOasis DB 주소. `{db_type}`은 세션 이름으로 바뀜. 예: `mysql://user:pw@host:3306/bookoasis_{db_type}` |
| `BOOKOASIS_DB_TYPES` | `general,adult,audiobook,video` | 읽을 세션 |
| `BOOKOASIS_DB_URL_<TYPE>` | (없음) | 세션별로 따로 지정 (예: `BOOKOASIS_DB_URL_ADULT`) |
| `LIBRARIES_FILE` | `DATA_DIR/libraries.manual.json` | DB 없이 쓸 때 보관함 정의 파일 |
| `GDW_ENABLED` / `WTM_ENABLED` / `MINI_ENABLED` | `true` / `false` / `true` | 모듈 켜기/끄기. 드라이브 변경 감시를 끄면 `/`는 웹툰(또는 미니게임) 화면으로 넘어감 |
| `MINI_COVERS_DIR` | `mini/games/picture-territory/covers` | 그림 땅따먹기 표지 그림 폴더 |
| `WTM_DATA_DIR` | `DATA_DIR/webtoon` | 웹툰 데이터(titles.json, 이력, 로그, settings.json) |
| `WTM_HANDOFF_GDW` | `true` | 받은 회차를 드라이브 변경 감시에 바로 넘김 |
| `WTM_SCAN_IMMEDIATE` | `true` | 넘긴 회차를 모으지 않고 바로 BookOasis 부분 스캔 (회차가 바로 등록·메타데이터 연결. 끄면 폴더가 조용해질 때까지 모아서 한 번에) |
| `WTM_DOWNLOAD_ROOT` 등 `WTM_…` | | 웹툰 저장 경로·임시 폴더·쿠키·알림 주소/토큰 (아래 "웹툰 다운로더" 참고) |

`.env`가 아니라 실제 환경변수(systemd `Environment=`, docker `environment:`)로 준 값이 있으면 그 값이 우선합니다.

### 보관함 목록: BookOasis DB 또는 파일
- **DB 연결(권장)**: 보관함 목록·보관함별 RC 주소·전체 스캔(cron) 일정을 BookOasis에서 읽고, 반영 확인(DB에 도서가 실제로 들어갔는지),
  이미 등록된 파일 건너뛰기, 스캔 일정 탭의 cron 저장까지 플러그인 때와 똑같이 동작합니다. 필요한 권한: `libraries` 읽기/`cron_schedule` 쓰기, `books` 읽기.
  BookOasis가 세션별로 DB를 어떻게 나누는지(DB 이름)에 맞춰 `{db_type}` 템플릿이나 `BOOKOASIS_DB_URL_<TYPE>`을 쓰세요.
  `python3 app.py --check`가 세션마다 보관함 개수를 보여 줍니다.
- **파일**: `libraries.example.json` 형식으로 보관함(`db_type`, `id`=BookOasis 보관함 ID, `roots`, `rclone_rc_url`, `cron_schedule`)을 적습니다.
  이 경우 반영 확인·중복 건너뛰기는 꺼지고, 스캔 일정 탭의 cron은 이 파일에만 저장됩니다(전체 스캔 회피 계산용).

## 플러그인에서 옮겨 오기
1. BookOasis에서 플러그인 감시를 **중지**합니다 (둘이 동시에 돌면 같은 변경을 두 번 처리합니다). 이후 플러그인은 비활성화/삭제하세요.
2. BookOasis의 `plugins/data/gdrive_watch/` 내용을 이 프로그램의 `DATA_DIR`로 복사합니다 (`state.db`, `watch.json`, `fallback.json` 등).
3. `.env`를 채웁니다. 첫 실행 때 `watch.json`에 남아 있던 실행 환경(화면에서 저장했던 RCLONE_*, BOOKOASIS_URL, WEBHOOK_TOKEN, AUTO_START)은
   **`.env`에 없는 값만** `.env`로 옮기고 `watch.json`에서는 지웁니다. 플러그인 설정 화면(BookOasis DB)에만 넣었던 값은 직접 옮겨 적으세요.
4. `BOOKOASIS_URL`은 이제 BookOasis 컨테이너 "안"이 아니라 이 프로그램에서 접속할 주소입니다 (같은 호스트면 포트 매핑된 주소).
5. `python3 app.py --check` 후 실행합니다.

## 웹툰 다운로더
`.env`에 `WTM_ENABLED=true`를 넣고 다시 시작하면 상단 메뉴에 **웹툰 다운로더**가 생깁니다(`/webtoon`). 화면과 기능은 플러그인 v1.39.3과 같습니다.
> ⚠️ 본 프로그램의 사용으로 인해 발생하는 모든 저작권 분쟁 및 법적 문제에 대한 책임은 다운로드를 수행한 이용자에게 있습니다.
> 저작권법 제30조(사적 이용을 위한 복제) 범위 안에서 개인 소장 목적으로만 쓰세요.

**플러그인과 달라진 점**
- 작업 프로세스(`wtm/worker_main.py`, nice 19)는 프로그램이 시작되면 바로 뜹니다. 플러그인 때는 화면을 열거나 BookOasis 요청이 있어야 스케줄러가 떴습니다.
- 설정·BookOasis DB를 작업 프로세스도 직접 읽습니다(플러그인 시절 `worker_cfg.json`·`compare_library_cache.json`으로 넘겨주던 것 불필요, "웹툰 다운로더 화면을 한 번 열어야 라이브러리 목록이 전달됨" 같은 제약 없음).
- 서비스를 멈추면 진행 중인 작업에 취소를 요청하고 작업 프로세스까지 정리하고 끝납니다.
- 업데이트는 이 저장소를 `git pull` 후 다시 시작 (플러그인의 업데이트 배지·plugin_board 연동은 없음).
- 받은 회차(zip·epub)가 라이브러리에 들어가면 드라이브 변경 감시 대기열에 바로 넣고 곧바로 처리합니다(`WTM_HANDOFF_GDW`, `WTM_SCAN_IMMEDIATE`).
  회차마다 VFS 새로고침 → BookOasis 부분 스캔이 돌아 받자마자 BookOasis에 등록되고 메타데이터가 붙습니다(대신 다운로드가 약간 느려질 수 있음).
  `WTM_SCAN_IMMEDIATE=false`면 같은 폴더에 연달아 들어오는 회차를 '폴더가 조용해질 때까지' 묶어 새로고침·스캔을 한 번만 합니다.
  나중에 Drive 쪽에서 같은 파일을 감지해도 이미 등록된 파일로 건너뜁니다. 보관함 밖 경로는 넘기지 않습니다.
- **로그인 쿠키 저장 위치**: 쿠키(네이버, 카카오 계정 1~5)는 `.env`가 아니라 `WTM_DATA_DIR/cookies/`의 파일
  (`naver.json`, `kakao_1.json`~`kakao_5.json`, 권한 600)에 저장됩니다. 화면의 **[파일에서 불러오기]**로 Cookie-Editor에서 내보낸 `.json`을
  고르거나, 서버에 그 이름으로 직접 복사해도 됩니다(다음 확인 때부터 바로 사용). 예전에 `.env`(`WTM_…COOKIE…`)에 넣은 값은 파일이 없으면
  그대로 쓰고, 화면에서 한 번 저장하면 파일로 옮겨집니다. 큰 저장 요청은 화면이 gzip으로 줄여 보내므로 앞단 프록시의 요청 크기 제한
  (nginx/Nginx Proxy Manager 기본 버퍼 8~16KB를 넘으면 500이 나는 경우)에 잘 걸리지 않습니다.
- **카카오 여러 계정**: [설정 > 카카오웹툰 > 추가 계정]에 다른 카카오 계정 쿠키를 4개까지 넣을 수 있습니다. 작품마다 계정 1로 받은 뒤,
  잠긴 회차가 남았거나 성인 인증으로 막혔으면 추가 계정으로 차례로 다시 시도합니다(이미 받은 회차는 건너뜀).
  계정마다 자기 기다무 대여권·보유 대여권·구매 회차를 쓰고, 기다무 사용 시각은 작품×계정별로 기록해 계정마다 충전되면 다시 확인합니다.
  다운로드 이력에는 회차마다 '계정2 · 기다무'처럼 어느 계정으로 무엇(기다무·보유 대여권·대여/소장·무료)으로 열었는지 나오고,
  작품 카드의 기다무 배지에 마우스를 올리면 계정별 다음 대여권 시각이 나옵니다.
  구매 작품 동기화는 모든 계정의 구매 목록을 모으고, 쿠키 자동 갱신·만료 알림도 계정마다 합니다.
  여러 계정으로 무료 혜택을 늘리는 것은 카카오 이용약관에 어긋날 수 있으니 본인·가족 계정으로만 쓰세요.
- **자동 실행에서 확인하는 작품**(실행 주기마다, 기본 '오늘' 범위): 요일 연재작은 그 요일(전날 늦게 올라온 회차 보완으로
  다음 날까지)만, 매일+는 매일, 네이버는 작품당 하루 1번만 봅니다. 카카오는 요일 목록 스캔에서 새 회차가 올라온 게 보인
  작품도 봅니다. 기다무 대여권은 자동 실행에서 보지 않고 아래 '기다무 대여권 바로 쓰기'가 작품별 주기로 따로 받습니다.
- **작품 하나의 자동 다운로드 시각 확인**: `python3 -m wtm.explain "작품 이름"` - 저장된 정보만으로(카카오·네이버에 요청 없음)
  전체 실행에서 그 작품을 보는 다음 시각들, 계정별 다음 기다무 대여권 시각, 최근 이력·로그를 보여 줍니다.
- **기다무 대여권 바로 쓰기**: '기다무 대여권 자동 사용'을 켜면 자동 실행 주기와 별도로, 대여권이 충전된 작품을 찾아
  바로 1화씩 받습니다. 충전 주기는 작품마다 카카오가 알려주는 값(3시간·12시간·1일·2일·3일·7일 기다무)을 쓰고, 계정마다 따로 셉니다.
  완결된 기다무 작품도 대여권으로 열 회차가 남아 있으면 확인합니다. 작품 카드의 배지는 '3시간 기다무'처럼 주기를 보여 주고,
  배지에 마우스를 올리면 다음 대여권 사용 시각이 나옵니다. (예약 실행 사용이 켜져 있어야 합니다)
  - **언제 확인하나**: 저장된 '계정별 마지막 사용 시각 + 충전 주기'로 다음 충전 시각을 계산해 그 시각에 맞춰 깨웁니다(1분 이상,
    [설정 > 카카오 > 대여권]의 '기다무 확인 최대 간격'(기본 5분) 이하). 충전 전인 작품은 카카오에 요청하지 않습니다.
    전체 실행이 도는 중에도 따로 돌고, 같은 작품을 두 작업이 동시에 받지는 않습니다.
  - **순서**: 한 번에 30개씩, 충전된 지 오래된(가장 많이 늦어진) 작품부터. 아직 대여권을 쓴 적이 없어 충전 시각을 모르는 작품은 그 뒤에.
    30개가 넘게 밀려 있으면 1분 뒤 이어서 확인합니다.
  - **지연 표시**: 다운로드 이력에 `계정1 · 3시간 기다무 · 12분 지연`처럼 충전 뒤 얼마나 늦게 썼는지 나옵니다(1분 안이면 `정시`).
  - **대여권으로 열 회차가 없는 작품**(남은 잠긴 회차가 기다무 대상이 아님)은 충전 주기 한 번 쉬었다 다시 봅니다.
    카카오가 대여권을 거절하면(아직 충전 전 등) 최대 1시간 뒤 다시 봅니다.
  - **1일 이상 기다무는 새벽부터 사용**(기본 끔): 켜면 1일·2일·3일·7일 기다무를 설정한 시작 시각(기본 1시)부터 씁니다. 끝 시각은 없고,
    시작 시각에 풀린 것과 이어서 충전되는 것(전날 이 무렵 쓴 것)을 다 쓰면 그날 사용을 끝내며, 그 뒤 낮에 충전되는 것은 다음 시작 시각까지
    기다립니다. 계정들은 모두 충전됐을 때 같이 씁니다.
- **날짜별 받은 용량**: 회차 파일이 라이브러리에 들어갈 때마다 크기를 날짜별·플랫폼별로 기록합니다(`download_stats.json`, 최근 120일).
  진행 줄에 `오늘 N화 X.XXGB`, 다운로드 이력 탭 위에 최근 7일 표가 나옵니다. 터미널에서는 `python3 -m wtm.download_stats [일수]`,
  기록을 시작하기 전 날짜는 `python3 -m wtm.download_stats --scan 7`(저장 경로의 파일을 수정 시각으로 셈)로 봅니다.
  앞으로의 예측은 `python3 -m wtm.download_stats --forecast 30` - 기다무 작품마다 (계정 수 × 하루/충전 주기)장씩, 남은 잠긴
  회차를 다 받으면 빠지는 것으로, 연재작은 연재 요일 수만큼 일주일에 받는 것으로 날짜별 회차 수를 세고, 최근 14일 기록의
  평균 회차 크기를 곱해 용량을 냅니다(추정치).
- **기다무 확인 순서·지연 미리 계산**: `python3 -m wtm.simulate [시간] ["작품 이름"] [--csv 파일]` - 지금 저장된 기록으로 앞으로 대여권을
  언제 쓰게 되는지 따라가 봅니다(카카오에 요청 없음). 대기열이 언제 빠지는지, 시간대별 대기열·대여권 수·지연, 주기별 평소 지연,
  작품 하나의 예상 사용 시각을 보여 줍니다. 한 번 확인에 걸리는 시간은 job.log의 최근 기록으로 잽니다. `--fixed`는 예전의 5분 고정 간격으로 비교.
- **1·2·3일 기다무를 시간대에 고르게 (매일 자동)**: [설정 > 카카오 > 대여권]의 '1·2·3일 기다무를 시간대에 고르게'(기본 끔)를 켜면
  매일 완결 목록 수집(기본 4시) 때, 대여권을 쓰는 1일·2일·3일 기다무 작품의 다음 충전을 정한 시간대(기본 01~10시)에 같은 간격으로
  다시 놓습니다(아래 `--spread`와 같은 계산). 대기 지연이나 새 작품으로 흩어진 것도 매일 다시 맞춰집니다. 받는 중인 작품은 건드리지 않습니다.
  1시간·2시간·3시간·12시간처럼 하루보다 짧은 기다무는 주기마다 다시 충전돼 시간대에 몰 수 없으므로, 주기별로 한 주기 안에
  같은 간격으로 퍼뜨립니다(예: 3시간 기다무 240개면 45초마다 하나씩 충전). 몰려 있던 것만 조금씩(최대 한 주기 미만) 늦어집니다.
- **1일·2일·3일 기다무 충전 시각을 새벽으로 옮기기**: `python3 -m wtm.shift_waitfree` (kakao_titles.json을 직접 고치는 도구, 서비스를 멈추고 실행)
  ```bash
  systemctl stop bookoasis_assistant
  python3 -m wtm.shift_waitfree --spread 1 11            # 미리 보기: 시간대별 분포 (전 → 후)
  python3 -m wtm.shift_waitfree --spread 1 11 --apply    # 적용 (kakao_titles.json.bak-날짜시각 으로 백업한 뒤)
  systemctl start bookoasis_assistant
  ```
  - `--spread 시작시 끝시`: 실제로 대여권을 쓰는 작품(구독·구매 + 잠긴 회차 남음)만 그 시간대(끝 시는 포함 안 함)에 같은 간격으로
    다시 놓습니다. 날짜(2일·3일 기다무는 며칠 뒤)는 그대로 두고 시각만 바꾸며, 한 작품의 계정들은 같은 시각으로 맞춥니다.
  - `--spread` 없이 실행하면 1~3일 기다무 전체의 다음 충전을 13:00~18:59는 +12시간(13:00 → 01:00), 그 밖의 낮 시각은 01:00~06:59로 옮깁니다.
  - 대여권은 '쓴 시각 + 주기'에 다시 충전되므로, 한 번 옮기면 그 뒤로도 그 시간대에 충전·사용됩니다.
  - **앞당기지는 못하고 뒤로만** 옮깁니다(실제 충전보다 이르게 기록하면 카카오가 거절). 낮에 이미 충전돼 기다리는 작품은 다음 날로 넘어가
    대여권 한 장이 한 번 늦어지므로, 시간대가 끝난 뒤(예: 1~11시면 11시 이후)에 실행하는 것이 손해가 가장 적습니다.
  - 대기 지연이나 새로 생긴 기다무 작품으로 시간대가 조금씩 흩어질 수 있으니, 가끔 미리 보기로 확인하고 다시 적용하면 됩니다.
- 네이버 로그인 유지: [설정 > 네이버 > 계정]의 **로그인 유지**(기본 켬)는 30분마다 쿠키로 네이버에 접속해 세션을 살려 둡니다.
  쿠키는 브라우저에서 **'로그인 상태 유지'를 체크하고 로그인**한 뒤 가져오세요. 체크하지 않은 쿠키(NID_AUT가 세션 쿠키)는 브라우저를 닫으면
  끝나는 쿠키라 금방 만료되며, 화면에 경고가 뜹니다. 쿠키를 가져온 브라우저에서 로그아웃하면 쿠키도 같이 무효가 됩니다.

- **kavita.yaml 표지 크기**: yaml에 넣는 표지(base64)를 가로 `KAVITA_YAML_COVER_WIDTH`(기본 300px, 0이면 원본) JPEG로 줄여 넣습니다
  ([설정 > 공통 > 저장 파일], Pillow 필요 - `venv/bin/pip install -r requirements.txt`). yaml이 작아져 회차가 늘 때마다 원격 마운트에서
  읽고·쓰고·업로드하는 양이 줄어듭니다. 이미 만든 yaml은 다음 갱신 때 줄어들고, 한 번에 줄이려면:
  `python3 -m wtm.shrink_yaml_covers` (미리 보기) → `python3 -m wtm.shrink_yaml_covers --apply` (표지 한 줄만 바꿈, 서비스 멈출 필요 없음)

**설정이 저장되는 곳** — 화면의 [설정 저장]이 알아서 나눠 씁니다.
| 어디 | 무엇 |
|---|---|
| `.env`의 `WTM_…` | 저장 경로(`WTM_DOWNLOAD_ROOT`, `WTM_KAKAO_DOWNLOAD_ROOT`, `WTM_KAKAO_NOVEL_DOWNLOAD_ROOT`, `WTM_TEMP_DOWNLOAD_ROOT`), 쿠키(`WTM_NAVER_COOKIE_JSON`, `WTM_KAKAO_COOKIE`, 추가 계정 `WTM_KAKAO_COOKIE_2`~`5`), 알림(디스코드·텔레그램·슬랙·ntfy 주소/토큰) |
| `WTM_DATA_DIR/settings.json` | 자동 실행·주기, 구독 대상, 속도, 플랫폼별 옵션, 중복 확인 폴더/라이브러리 등 운영 옵션 |

쿠키 JSON처럼 여러 줄인 값도 `.env`에는 한 줄로(`\n` 이스케이프) 저장됩니다. 쿠키는 화면에 붙여 넣는 것을 권장합니다.
저장 경로는 BookOasis 보관함 경로와 **같은 경로로 보여야** 받은 회차가 그 보관함 스캔으로 이어집니다(드라이브 변경 감시와 같은 조건).

**플러그인에서 옮겨 오기**
1. BookOasis 웹툰 다운로더 화면에서 자동 실행을 끄고, 진행 중인 작업이 없을 때 플러그인을 비활성화합니다 (둘이 같이 돌면 같은 회차를 두 번 받습니다).
2. BookOasis의 `plugins/data/webtoon_manager/` 내용을 `WTM_DATA_DIR`(기본 `data/webtoon/`)에 복사합니다 — 작품 목록, 이력, 쿠키 갱신 상태, kavita 기록이 이어집니다.
3. 첫 실행 때 그 폴더의 `worker_cfg.json`(플러그인 설정 전체)을 `settings.json`과 `.env`로 옮깁니다. `.env`에 이미 적어 둔 `WTM_…` 값은 덮지 않습니다.
4. 플러그인 설정에 적었던 경로가 BookOasis 컨테이너 안 경로라면, 이 서버에서도 같은 경로로 보이는지 확인합니다 (`python3 app.py --check`가 경로마다 ✓/✗).

**텔레그램 채널 업로드** (작품 카드의 **📤 텔레그램** 버튼)
- 작품마다 켜고 끕니다. 켜는 순간 그 작품 폴더에 이미 받은 회차(zip·epub)를 **회차 순서대로 전부** 대기열에 넣고,
  그 뒤로는 그 작품의 **새 회차를 받을 때마다** 추가로 올립니다. 버튼을 켜지 않은 작품은 올리지 않습니다.
  끄면 아직 올리지 않은 회차는 대기열에서 뺍니다. 다시 켜도 이미 올린 회차는 다시 올리지 않습니다.
- 캡션은 `#작품명` 해시태그 + 파일 이름(무음 전송). 다운로드와 따로 도는 대기열(`WTM_DATA_DIR/telegram_upload.db`)로 하나씩 올립니다.
  재시작해도 이어서 올리고, 텔레그램 속도 제한(429)은 알려 준 시간만큼 쉬며, 그 밖의 실패는 1분부터 두 배씩(최대 1시간) 8번까지 다시 시도합니다.
  채널·토큰 오류(401/403/400)는 설정을 고칠 때까지 10분마다 다시 시도하고, 설정을 저장하면 기다리던 것·실패한 것을 바로 다시 올립니다.
- **크기 제한**: 공식 Bot API는 파일당 50MB까지라 그보다 큰 회차는 '건너뜀'으로 남깁니다.
  더 큰 파일은 [로컬 Bot API 서버](https://github.com/tdlib/telegram-bot-api)를 띄우고 Bot API 주소와 최대 크기(최대 2000MB)를 바꾸세요
  (최대 크기를 올려 저장하면 크기 때문에 건너뛴 파일도 다시 올립니다).
- 준비 ([설정] > [공통] > 텔레그램 채널 업로드): 봇을 만들고(@BotFather) 그 봇을 채널 관리자로 추가해 '메시지 보내기' 권한을 줍니다.
  채널 ID(`-100…`) 또는 `@채널이름`을 넣고, 봇 토큰은 비우면 알림용 텔레그램 봇 토큰을 씁니다. 저장 후 '알림 테스트 보내기'에
  `텔레그램 채널 업로드 ✅`가 나오면 됩니다. 채널 ID·봇 토큰·Bot API 주소는 `.env`의 `WTM_TELEGRAM_UPLOAD_…`에 저장됩니다.
- 진행 줄에 `텔레그램 업로드 N개 완료, 대기 N, 실패 N`이 나옵니다. 실패·건너뜀 사유는 작업 로그에 남습니다.
- 작품 정보(`kavita.yaml`)는 **`작품명.yaml`** 로 이름을 바꿔 회차보다 먼저 한 번 올립니다(캡션 `#작품명` + `작품 정보`).
  새 작품이면 첫 회차와 함께 올라가고, 이미 올린 뒤에는 내용이 바뀌어도 다시 올리지 않습니다.
- ⚠️ 받은 파일을 다른 사람에게 공유하는 것은 저작권법 위반입니다. 본인만 들어가는 **비공개 채널**(개인 보관용)로만 쓰세요.

**명령줄 도구** (저장소 폴더에서)
- `venv/bin/python -m wtm.backfill_all --dry-run` : 구독 작품의 빠진 과거 회차 일괄 받기 (먼저 `--dry-run`)
- `venv/bin/python wtm/migrate_filenames.py --dry-run <폴더>` : 예전 파일 이름 형식 정리

## 미니게임
`/games` (사이드바 **미니게임**). 게임 12종이 사이드바 서브 메뉴로 나오고, 주소의 `#게임id`(예: `/games#tetris`)로 바로 열 수 있습니다.
- 게임은 `mini/games/<id>/`(manifest.json · template.html · style.css · game.js) 그대로이고, 서버가 읽어서 화면 하나로 묶어 줍니다.
  플러그인처럼 index.html/style.css/script.js를 파일로 다시 쓰지 않고 메모리에서 묶으며, 게임 파일이 바뀌면 다음 요청 때 다시 묶습니다.
  게임을 추가하려면 같은 구성의 폴더를 `mini/games/` 아래에 넣으면 됩니다.
- **그림 땅따먹기 표지**: `MINI_COVERS_DIR`(기본 `mini/games/picture-territory/covers`)의 그림(jpg/png/gif/webp) 중 하나를 게임마다 무작위로 씁니다.
  플러그인 때는 `covers/list.json`을 직접 만들어야 했지만(저장소에 없어서 실제로는 쓰이지 않았음), 이제 서버가 폴더를 보고 목록을 만듭니다.
- 최고 점수 등은 게임마다 브라우저(localStorage)에 저장됩니다(플러그인과 같음).

## 관리 화면 / API

- **업데이트 표시**: 왼쪽 위 아이콘의 버전 배지(지금 보는 모듈의 버전)는 GitHub에 새 버전이 있으면 빨갛게 바뀌고 노란 점이 붙습니다.
  마우스를 올리거나 [설정 > 정보]에서 최신 버전을 볼 수 있습니다. 6시간마다 GitHub의 `VERSION`을 확인하며,
  `.env`에 `UPDATE_CHECK_URL=`(빈 값)을 넣으면 확인하지 않습니다.

- `GET /` 드라이브 변경 감시 (현황, 변경 기록, 감시 설정, 스캔 일정, 로그) · `GET /webtoon` 웹툰 다운로더 · `GET /games` 미니게임
- `POST /api/rpc/<동작>` 드라이브 변경 감시 RPC, `GET /api/wtm/data`·`POST /api/wtm/action` 웹툰 다운로더.
  `Content-Type: application/json`만 받습니다(다른 사이트 폼 전송 차단).
- **로그인**: YMPlayer와 같은 로그인 화면입니다. '로그인 유지'를 켜면 30일, 끄면 12시간 유지됩니다. 계정은 `DATA_DIR/users.json`(PBKDF2 해시)이고
  왼쪽 아래 계정 줄에서 비밀번호 변경·로그아웃, **설정 > 사용자**에서 사용자 추가·삭제·비밀번호 재설정을 합니다(모두 관리자).
  예전 HTTP Basic 인증의 `WEB_USER`/`WEB_PASSWORD`는 첫 실행 때 그대로 첫 계정이 되므로 같은 아이디·비밀번호로 로그인하면 됩니다.
  비밀번호를 바꾸면 다른 기기의 로그인은 끊깁니다. 로그인 실패가 IP마다 10분에 10번을 넘으면 잠시 막습니다.
- **MCP 서버**: Claude Code·Claude Desktop 같은 MCP 클라이언트가 `POST /mcp`(Streamable HTTP, `Authorization: Bearer <MCP_TOKEN>`)로 붙습니다.
  **설정 > MCP**에서 [켜기]를 누르면 토큰이 `.env`의 `MCP_TOKEN`에 저장되고, 연결 명령(Claude Code)과 설정(Claude Desktop, `mcp-remote`)이 나옵니다.
  도구: `gdw_status`·`gdw_events`·`gdw_log`·`gdw_schedules`(조회), `gdw_request_path`(경로 직접 반영)·`gdw_retry`·`gdw_poll_now`·`gdw_worker`,
  `wtm_status`·`wtm_titles`·`wtm_history`(조회), `wtm_set_subscription`·`wtm_download_title`·`wtm_run`. 켜진 모듈의 도구만 보입니다.
  토큰이 있으면 로그인 없이 이 동작을 할 수 있으니 비밀번호처럼 다루세요. 외부(인터넷)에서 쓰려면 https 리버스 프록시 뒤에 두세요.
- 화면은 YMPlayer와 같은 틀입니다. 왼쪽 메뉴 맨 아래 **설정**(화면 · 정보)에서 모든 사용자의 **기본 테마·강조색**을 정하고(`DATA_DIR/ui_prefs.json`),
  팔레트 버튼으로 이 브라우저에서만 쓸 테마를 따로 고를 수 있습니다.
  **설정 > 메뉴**에서 왼쪽 메뉴의 모듈 순서와 모듈 안 메뉴 순서를 ▲▼로 바꿉니다(모든 브라우저 공통, 같은 파일에 저장). [기본 순서로]로 되돌립니다. 파비콘은 강조색을 따라가고, 로고 옆 배지는 지금 모듈의 버전입니다.
- `POST /mcp` MCP 서버 (위 "MCP 서버" 참고)
- `GET /api/modules` 켜진 모듈·모듈별 버전·기본 테마, `POST /api/ui-prefs` 기본 테마·메뉴 순서 저장, `GET /healthz` 인증 없이 `{"ok": true, "worker": true|false}` (모니터링용)

## 파일
| 파일 | 역할 |
| --- | --- |
| `app.py` | 진입점: .env 읽기, 웹 서버, 워커 감독, DB 중복 확인 스레드, `--check` |
| `gdw/config.py` | .env 읽기/쓰기, 실행 환경 |
| `gdw/service.py` | 서비스 본체 (예전 `gdrive_watch.py`): 워커 실행/중지, runtime.json, 화면 RPC |
| `gdw/bookoasis_db.py` | BookOasis DB 직접 연결 (MySQL/MariaDB·SQLite) |
| `gdw/screener.py` | 이미 등록된 파일 건너뛰기 (BookOasis DB 확인) |
| `gdw/supervisor.py` | 자동 시작·워커 재시작·보관함 목록 갱신 |
| `gdw/web.py` | 관리 화면 웹 서버 (두 모듈 공용) |
| `gdw/handoff.py` | 다른 모듈이 라이브러리에 넣은 파일을 드라이브 변경 감시 대기열로 |
| `worker.py` | 드라이브 변경 감시 워커: 변경 감지, VFS 새로고침, 스캔 요청 (플러그인과 같은 코드) |
| `mini/` | 미니게임 (`games/` 게임 폴더 그대로 + `bundle.py`: /games 화면 만들기) |
| `wtm/` | 웹툰 다운로더 (플러그인 코드 그대로 + `host.py`: 설정·DB·데이터 폴더, `service.py`: 화면 연결) |
| `web/` | 관리 화면 (`theme.css` 공용, `index.html`·`style.css`·`script.js` 드라이브 감시, `webtoon/` 웹툰) |
| `docs/webtoon_manager_CHANGELOG.md` | 웹툰 다운로더 플러그인 시절 변경 기록 |
| `deploy/`, `Dockerfile`, `docker-compose.example.yml` | 배포 예시 |

테스트: `python3 -m unittest discover -s tests`

## 드라이브 변경 감시: Pipedream으로 바로 확인 (선택)

워커는 Drive 변경을 `poll_seconds`(기본 60초)마다 확인합니다. Pipedream의 Google Drive 트리거
**New or Modified Files (Instant)**(Drive 푸시 알림)를 쓰면, 파일이 바뀌는 즉시 이 프로그램을 깨워 기다리지 않고 확인하게 할 수 있습니다.
무엇이 바뀌었는지는 워커가 평소처럼 직접 확인하므로 Pipedream이 보내는 내용(파일 이름·경로)은 쓰지 않습니다 - 알림이 빠지거나
늦어도 원래 주기 확인이 그대로 돕니다.

1. `.env`에 `GDW_WAKE_TOKEN=<길고 임의의 값>`을 넣고 재시작합니다 (`openssl rand -hex 24`로 만들 수 있음).
2. Pipedream에서 새 Workflow → 트리거 **Google Drive → New or Modified Files (Instant)**
   - Google 계정 연결(감시하는 Drive의 계정), `Drive`: My Drive 또는 감시하는 공유 드라이브, `Folders`: 감시 폴더(비우면 Drive 전체)
   - `perFileInterval`은 1~5분 정도로 두면 같은 파일이 여러 번 바뀔 때 알림이 덜 옵니다.
3. 다음 단계로 **HTTP / Webhook → Send any HTTP Request**
   - Method `POST`, URL `https://<관리 화면 주소>/api/gdw/wake`
   - Headers `Authorization: Bearer <GDW_WAKE_TOKEN 값>` (본문은 비워도 됨)
4. Deploy 후 Drive에 파일을 하나 올려 보고, 감시 화면의 로그에서 바로 확인되는지 봅니다.
   주소 확인: `curl -X POST -H "Authorization: Bearer <값>" https://<주소>/api/gdw/wake` → `{"success": true, …}`

관리 화면이 인터넷에서 열려 있어야 합니다(리버스 프록시 등). 토큰 없이 부르면 401, `GDW_WAKE_TOKEN`이 비어 있으면 404로 거절합니다.

## 드라이브 변경 감시 기능 (플러그인과 동일)

> ⚠️ **윈도우에서는 사용할 수 없습니다 (리눅스 전용).** 경로를 `/`로 시작하는 리눅스 경로로만 다루고, 실시간 감지(inotify)와
> 마운트 정보(`/proc`)도 리눅스 기능이라 윈도우 경로(`D:\…`)를 인식하지 못합니다. 윈도우에서는 자동으로 꺼지며,
> `GDW_ENABLED=true`로 켜도 시작할 때 경고를 남기고 끕니다. 웹툰 다운로더·미니게임은 윈도우에서도 쓸 수 있습니다.
### 동작
```
Drive Changes/Activity 확인 (기본 60초)
  → 변경 이벤트 기록 (기본 60초 모아서 처리)
  → rclone RC: vfs/forget(이전 경로) → vfs/refresh(부모 폴더, 비재귀)
  → /api/webhook/scan?path=<보관함 기준 폴더>
```
- 보관함 목록과 보관함별 RC 주소는 BookOasis DB에서 자동으로 읽습니다(1분 캐시).
- 보관함 폴더가 마운트 안 어디에 있는지는 RC에 `vfs/refresh`를 경로 뒤쪽부터 시험해 찾고 기억합니다(`state.db`의 `vfs_map`). RC가 없는 보관함이나 여러 마운트에 동시에 보내야 할 때만 규칙을 직접 지정합니다.
- VFS 새로고침이 실패하면 스캔을 보류하고 재시도합니다(60초부터 두 배씩, 최대 30분 간격).
- 첫 실행 때 Drive API로 기존 파일 목록을 백그라운드에서 수집해, 시작 전부터 있던 파일의 삭제·이동도 이전 경로를 알 수 있게 합니다. 수집하는 동안에도 변경 감지는 계속됩니다.

### 파일 확인 후 스캔 (plex_mate 방식)
VFS 새로고침 뒤 마운트에 파일이 실제로 보이는지 확인하고, 추가·수정은 보일 때까지, 삭제는 사라질 때까지 20초 간격으로 새로고침하며 기다립니다(기본 최대 10분, 0이면 끔). 시간을 넘기면 '시간 초과'로 남깁니다. rclone 목록 반영이 늦어 빈 폴더를 스캔하고 '반영됨'으로 끝나는 일을 막습니다.

### 경로 직접 반영
변경 기록 탭에서 경로를 넣고 '추가로 반영'/'삭제로 반영'을 누르면 감시와 같은 처리(VFS → 파일 확인 → 스캔)를 태웁니다.

### 스캔 일정 (구 scan_scheduler 통합)
**스캔 일정** 탭에서 보관함별 전체 스캔(cron) 일정을 요일×시간 표와 보관함별 타임라인으로 보고, 겹치는 시간대를 찾아 조정합니다. 칸을 끌어 옮기거나 스케줄 도우미(매일/매주/매월/직접 입력)로 바꾼 뒤 저장합니다.
- ⚡ 표시: 이 프로그램이 실시간으로 반영 중인 보관함. 전체 스캔은 누락 보정용이라 하루 1회 정도면 충분합니다.
- **전체 스캔 회피**(처리 옵션, 기본 10분): 보관함의 전체 스캔이 시작된 뒤 이 시간 동안은 그 보관함의 부분 스캔을 미뤘다가 끝난 뒤 보냅니다. 0이면 끕니다.

BookOasis의 scan_scheduler 플러그인은 이 탭으로 통합되어 더 이상 관리하지 않습니다. 함께 쓰지 마세요.

### 토큰 (rclone.conf 공유 전제)
rclone.conf를 FF·호스트 rclone과 함께 쓰는 환경을 전제로, 리모트마다 자동으로 방식을 고릅니다.
- **메모리 갱신**: 리모트에 본인 `client_id`/`client_secret`이 있으면 워커가 Google에서 직접 새 토큰을 받아 메모리에만 둡니다. rclone.conf에는 쓰지 않습니다(gd-poller 방식).
- **rclone 갱신**: rclone 내장 client를 쓰는 리모트는 rclone에게 갱신을 맡깁니다(rclone이 rclone.conf에 저장).
- **커스텀 인증**(gds_endpoint 등): 갱신하지 않고, 공유 중인 FF·호스트 rclone이 갱신해 저장한 값을 읽습니다.

### 같은 드라이브의 여러 감시 폴더
Changes 방식의 변경 목록은 **드라이브 전체 단위**라, 같은 공유 드라이브 안의 폴더를 여러 개 감시하면 각 폴더에 다른 폴더의 변경도 함께 들어옵니다(요약의 '범위 밖'). 이는 정상이며 기록되지 않습니다. 한 번의 확인에서 같은 드라이브의 변경 목록은 **한 번만 받아 공유**하고, 범위 밖 항목은 로그에 하나하나 남기지 않습니다.

### 로그 보관
로그(worker.log)는 하루 단위로 나눠 저장하고 **처리 옵션 > 로그 보관(일)**(기본 3일)만큼만 남깁니다. 로그 탭의 **로그 비우기**로 바로 지울 수도 있습니다. 변경 기록 탭의 기록은 **기록 보관(일)**(기본 30일, 실패 기록은 2배)로 따로 정리됩니다.

### 부하 줄이기 · 점검
- **VFS 새로고침은 폴더 단위, 묶어서**: 파일마다 하지 않습니다. 같은 폴더의 변경은 하나로 합치고, 한 마운트로 가는 폴더들은 한 번의 요청(dir, dir2, …)으로 보냅니다.
- **폴더가 조용해질 때까지 기다림**: 같은 폴더에 새 변경이 '폴더가 조용해질 때까지(초)'(기본 60초) 안에 또 들어오면 기다렸다가 한 번에 처리합니다. 회차가 연달아 올라와도 새로고침·스캔은 한 번입니다. 계속 이어져도 '최대 대기(분)'(기본 10분)가 지나면 처리합니다.
- **마운트에 이미 보이면 생략**: 처리 전에 마운트를 먼저 확인해, 새 파일이 이미 보이거나(rclone 마운트 자체의 변경 감지·캐시 만료) 지운 파일이 이미 사라졌으면 새로고침하지 않습니다. 내용이 바뀐 수정은 겉으로 알 수 없어 새로고침합니다.
- **이미 등록된 파일 건너뛰기**(기본 켬): 새 파일이 감지되면 워커가 처리하기 전에 BookOasis DB에서 같은 경로의 도서를 찾고, 이미 있으면 VFS 새로고침·스캔 없이 '건너뜀 · 이미 등록됨'으로 끝냅니다. 최근 1시간 안에 같은 경로가 지워졌던 경우(다시 올림)는 내용이 바뀌었을 수 있어 그대로 처리합니다. 수동 요청·선택 재시도도 그대로 처리합니다.
- **내용이 그대로인 수정**: 수정 시각만 바뀌고 크기·md5가 같으면 수정으로 보지 않습니다.
- **보관함 밖 경로**: 어느 보관함에도 속하지 않는 경로는 VFS 새로고침도 하지 않고 바로 건너뜁니다.
- 상단 상태 줄 아래에 **최근 1시간** 동안 이 워커가 보낸 Drive 호출, VFS 새로고침, 스캔 요청 수와 워커 CPU·메모리가 나옵니다. BookOasis가 스캔을 처리하는 부하 자체는 포함하지 않습니다.
- **보관함 맨 위 변경**: 보관함 맨 위의 작품 폴더가 지워지는 등 부분 스캔 대상이 보관함 맨 위가 되면 사실상 전체 스캔이라 보내지 않고, 다음 예약 전체 스캔 때 반영합니다(처리 옵션에서 허용 가능). 다른 작품 폴더의 변경도 맨 위로 합쳐지지 않고 각자 부분 스캔합니다.
- 파일이 마운트에 보이기를 기다리는 동안 VFS 새로고침 간격은 20초에서 최대 2분으로 늘어나고, 전체 스캔 회피로 미뤄 둔 기록은 이미 보이면 VFS를 다시 새로고침하지 않습니다.
- **대기 내역**: 현황에 처리 대기 기록이 어디서 기다리는지(모으는 중 · DB 중복 확인 차례 · 처리 차례 · 파일/BookOasis/전체 스캔 회피 대기)와 가장 오래된 기록이 나오고,
  부하 줄에 스캔 1회 평균·최대 시간이 나옵니다. '모으는 중'이 많으면 '모아서 처리'·'폴더가 조용해질 때까지'·'최대 대기'를 줄이고,
  '처리 차례'가 많고 스캔 시간이 길면 BookOasis 스캔 자체가 병목입니다(스캔은 하나씩 결과를 기다리며 보냅니다).
- **폴더 단위로 조금씩 처리**: 기록을 500건씩이 아니라 폴더 10개씩(동시 스캔 수 × 10) 가져와 처리합니다. 한 폴더의 기록은 한 묶음에 모두 들어가 스캔이 한 번이고,
  묶음마다 결과가 바로 기록되며 그 사이에 새 변경 확인도 이어집니다. 다운로드 직후·수동 요청 기록은 대기열 맨 앞으로 갑니다.
- **동시 스캔 수**(기본 1, 최대 4): BookOasis에 부분 스캔을 동시에 몇 개 보낼지. 스캔이 밀리면 2로 올려 보세요(BookOasis 부하도 그만큼 늘어남).
- **BookOasis DB 잠금**: 스캔 응답이 `Lock wait timeout exceeded`(1205)·`Deadlock`(1213)이면 실패로 세지 않고 2분 뒤 다시 보내고,
  30분 동안 동시 스캔을 1개로 줄입니다. 자주 나면 동시 스캔 수를 1로 두고, BookOasis DB의 `innodb_lock_wait_timeout`(기본 50초)을 늘리세요.
- 이미 등록된 파일 확인은 대기 기록을 세션별로 모아 한 번의 DB 연결·`IN` 조회로 합니다(예전에는 기록마다 새로 접속).
- 폴더 비교의 '바로 아래 항목' 조회는 부모 경로 인덱스를 써서 하위 전체를 훑지 않습니다.

### 무시할 경로
정규식으로 경로를 제외합니다. 기본값은 업로드 중인 `[업로드]` 폴더, 숨김 파일·폴더, 받는 중인 임시 파일(`.part`, `.crdownload` 등)입니다. `[업로드]`에서 실제 폴더로 옮기면 '추가'로 처리됩니다.

### 디스코드 알림
- 처리 결과(반영됨·실패)는 모아 두었다가 **보내는 주기(분, 기본 10)가 지나거나 모인 건수(기본 100건)에 닿으면** 둘 중 먼저 오는 때에 한 번에 보냅니다. 둘 다 0이면 처리 묶음마다 바로 보냅니다. 메시지에는 앞 15건과 보관함별 건수가 나옵니다.
- 모아 둔 결과는 `notify_queue.json`에 남아 워커가 재시작돼도 이어서 보냅니다. 연결 오류·호출 제한이면 1분 뒤 다시 보냅니다.
- 감시 오류·복구 알림은 모으지 않고 바로 보냅니다.
디스코드 웹훅(`https://discord.com/api/webhooks/…`) 또는 디스코드로 중계하는 구글 앱스 스크립트 웹 앱(`https://script.google.com/macros/s/…/exec?parentId=…&threadId=…`, 쿼리 포함 그대로) 주소를 넣으면 처리 묶음마다 결과(반영됨·실패)를 한 번에 보내고, 감시 폴더 오류와 복구도 알립니다. 앱스 스크립트에는 디스코드 웹훅과 같은 JSON(`username`, `embeds`)을 POST로 보냅니다.

### Drive · 폴더 비교
공유 드라이브 멤버가 아니라 폴더만 공유받은 계정(gds 등)은 드라이브 단위 변경 목록을 받을 수 없고, 계정 전체 변경 목록은 관계없는 변경이 수십만 건이라 쓸 수 없습니다. 이런 폴더는 **폴더 비교** 방식으로 감시합니다.
- 정해진 주기(기본 600초, 최소 120초)마다 감시 폴더를 Drive API로 훑어(폴더 50개씩 묶어 동시 조회) 이전 목록과 비교합니다.
- **나눠 훑기**: 매 주기 모든 폴더를 다시 읽지 않습니다. 폴더마다 그 폴더 바로 아래가 마지막으로 바뀐 뒤 지난 기간에 따라 다시 읽습니다.

  | 마지막 변경 | 일반 폴더 | 분류 폴더 (감시 폴더에서 2단계까지, 옵션) |
  |---|---|---|
  | 1시간 안 | 10분 | 매 주기 |
  | 1~6시간 | 30분 | 매 주기 |
  | 6~24시간 | 1시간 | 매 주기 |
  | 1~2일 | 하루 2번 | 하루 2번 |
  | 2~7일 | 하루 1번 | 하루 1번 |
  | 7~15일 | 2일 | 2일 |
  | 16~30일 | 7일 | 7일 |
  | 31일 이상 | 30일 | 30일 |

  폴더가 바뀌면 바로 짧은 간격으로 돌아갑니다. 폴더를 실제로 읽는 시점은 그 감시 폴더의 비교 주기(기본 600초)마다이므로, 10분보다 짧게 읽지는 않습니다.
- **폴더별 규칙**: 감시 폴더 ▸ 펼치기에서 하위 폴더마다 다시 읽는 간격을 정할 수 있습니다(자동 / 매 주기 / 1시간 / 6시간 / 1일 / 7일 / 30일 / 읽지 않음). 규칙은 그 폴더와 하위 전체에 적용되고, 더 깊은 폴더에 따로 정한 규칙이 우선합니다. 예: `소설`은 30일, 그 안의 `소설/연재`는 매 주기. '읽지 않음'은 그 아래 변경을 감지하지 않습니다.
- **깨우기**: 분류 폴더를 읽을 때 함께 받는 작품 폴더 자체의 수정 시각이 바뀌어 있으면, 차례가 아니어도 다음 비교 때 바로 읽습니다.
- 훑기는 폴더마다 별도 스레드에서 돌아 다른 감시를 막지 않습니다.
- 첫 비교는 기준 목록만 만들고, 이후 추가·수정·이동·이름 변경·삭제를 기록합니다. 새 폴더나 사라진 폴더는 폴더 하나로 기록합니다.
- 대량 삭제(100개 이상이면서 20% 이상)로 보이면 반영을 멈춥니다.
- Changes에서 멤버십 오류가 나면 자동으로 이 방식으로 전환합니다.

### 로컬 폴더 감시
감시 방식을 **로컬 폴더**로 고르면 Google Drive가 아닌 폴더(로컬 디스크, NAS 공유 등)도 같은 화면에서 감시합니다.
- **실시간**: 로컬 파일시스템(ext4, xfs, btrfs 등)에서 inotify로 변경 알림을 받아, 바뀐 폴더만 다시 비교합니다. 1시간마다 전체 대조로 누락을 보완합니다. 외부 라이브러리 없이 동작합니다.
- **주기 비교**: 정해진 주기(기본 300초)마다 전체 파일 목록(크기·수정 시각)을 이전 목록과 비교합니다. NAS(SMB/NFS)나 rclone 마운트처럼 다른 기기가 바꾸는 폴더는 이 방식이어야 합니다.
- **자동**: 파일시스템 종류를 보고 위 둘 중 하나를 고릅니다.
- 첫 실행은 기준 목록만 만들고, 그 이후 변경부터 반영합니다. 로컬 폴더 이벤트는 VFS 새로고침 없이 바로 스캔합니다.
- 보호 장치: 파일이 한 번에 대량으로(100개 이상이면서 전체의 20% 이상) 사라지거나 다른 디스크로 바뀌면 마운트 문제로 보고 반영을 멈춥니다. 확인 후 **처음부터**를 누르면 기준을 다시 만듭니다.
- 숨김 파일·폴더와 `@eaDir`, `#recycle`, `$RECYCLE.BIN` 등은 무시합니다.

### 바로가기 폴더
- 감시 폴더 ID가 바로가기여도 됩니다. 실제 폴더 ID로 바꿔서 감시합니다.
- 감시 폴더 안의 폴더 바로가기도 따라갑니다(Changes 방식). 바로가기 대상 폴더 안의 변경을 바로가기 경로로 해석합니다.
- 감시 폴더 안의 바로가기가 **다른 드라이브**의 폴더를 가리키면, 그 대상 폴더를 **하위 감시**(`상위 › 폴더`)로 자동으로 따로 둡니다. 다른 드라이브의 변경은 상위 폴더의 변경 목록에 들어오지 않기 때문입니다. 하위 감시도 Changes로 시작하고, 그 드라이브의 멤버가 아니면 폴더 비교로 자동 전환됩니다. 바로가기가 지워지면 하위 감시도 끝납니다(6시간마다, 또는 바로가기 변경 시 다시 맞춤).


## 참고
Changes/Activity 감지, 체크포인트, file_id→경로 상태 설계는 BookOasis Mate(AGPL-3.0)의 자체 변경 감지를 참고해 다시 작성했습니다.
