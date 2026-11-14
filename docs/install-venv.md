# BookOasis Assistant 설치 가이드 ① 가상환경(venv) + systemd

> 이 문서만 따라 하면 설치가 끝나도록 썼습니다. 리눅스(Ubuntu 22.04/24.04, Debian 12) 서버 기준입니다.
> 도커로 설치하려면 → [install-docker.md](install-docker.md) · 설치한 뒤 화면 설정 → [setup-guide.md](setup-guide.md)

**권장 방식입니다.** 도커는 저장 경로를 BookOasis와 같게 맞추기, rclone 마운트 전파, 파일 소유자, 업데이트마다 이미지 다시 만들기 등
막히는 곳이 많습니다.

---

## 0. 무엇이 설치되나

| 항목 | 위치 (이 문서 기준) |
|---|---|
| 프로그램 | `/opt/bookoasis_assistant` (git 저장소) |
| 파이썬 가상환경 | `/opt/bookoasis_assistant/venv` |
| 설정 파일 | `/opt/bookoasis_assistant/.env` |
| 기록·쿠키·로그·자동 올리기 설정 | `/opt/bookoasis_assistant/data` |
| 서비스 | `bookoasis_assistant` (systemd) |
| 접속 주소 | `http://서버IP:5931` |

| 모듈 | 하는 일 | 켜기 (`.env`) |
|---|---|---|
| 웹툰 다운로더 | 네이버웹툰·카카오웹툰·카카오웹소설 구독/다운로드 | `WTM_ENABLED=true` (기본) |
| 드라이브 변경 감시 | Google Drive·로컬 폴더 변경 → rclone VFS 새로고침 → BookOasis 부분 스캔 (리눅스 전용) | `GDW_ENABLED=true` (기본) |
| 텔레그램 자동 올리기 | Plex·rclone 드라이브의 새 동영상 → 텔레그램 채널 | `TGUP_ENABLED=true` (기본) |
| 미니게임 | 브라우저 게임 12종 | `MINI_ENABLED=true` (기본) |

쓰지 않는 모듈은 `false`로 끄면 됩니다.

---

## 1. 필요한 프로그램 설치

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ffmpeg fonts-nanum
```

| 패키지 | 왜 필요한가 | 없으면 |
|---|---|---|
| `git` | 내려받기·업데이트 | 설치 불가 |
| `python3` (3.9 이상), `python3-venv` | 프로그램 실행, 가상환경 | 설치 불가 |
| `ffmpeg` | 텔레그램 자동 올리기의 인코딩·나눠 올리기 | 그 기능만 안 됨 |
| `fonts-nanum` | 자동 올리기에서 한글 자막을 화면에 입힐 때 | 자막 글자가 네모 |

**rclone** (드라이브 변경 감시를 쓸 때, 자동 올리기에서 rclone 원격을 쓸 때): 이미 BookOasis용으로 깔려 있으면 그대로 씁니다.
없으면 `sudo -v ; curl https://rclone.org/install.sh | sudo bash`.

---

## 2. 내려받기

```bash
sudo git clone https://github.com/yume-script/bookoasis_assistant.git /opt/bookoasis_assistant
cd /opt/bookoasis_assistant
```

---

## 3. 가상환경 만들고 패키지 설치

```bash
cd /opt/bookoasis_assistant
sudo python3 -m venv venv
sudo venv/bin/pip install --upgrade pip
sudo venv/bin/pip install -r requirements.txt
```

- **꼭 `venv/bin/pip`로** 설치하세요. 그냥 `pip install`은 Ubuntu/Debian에서 막히거나(`externally-managed-environment`) 다른 파이썬에 깔립니다.
- 설치되는 것: `requests`·`Pillow`(웹툰), `PyMySQL`(BookOasis DB), `aiohttp`·`telethon`·`cryptg`(텔레그램 자동 올리기).
- `cryptg` 설치에서 오류가 나면 무시해도 됩니다(텔레그램 올리기가 조금 느려질 뿐). 그래도 설치가 멈추면:
  `sudo venv/bin/pip install PyMySQL requests Pillow aiohttp telethon`

---

## 4. `.env` 만들기

```bash
cd /opt/bookoasis_assistant
sudo cp env.example .env
sudo chmod 600 .env          # 비밀번호·토큰이 들어가는 파일
sudo nano .env
```

**처음에 꼭 넣을 것**만 추렸습니다(나머지는 화면에서 넣어도 이 파일에 저장됩니다):

```ini
# ── 관리 화면 ──
WEB_HOST=0.0.0.0              # 다른 PC·폰에서 접속 (이 서버 안에서만 쓰면 127.0.0.1)
WEB_PORT=5931
WEB_USER=admin                # 첫 관리자 아이디 (사용자가 없을 때 한 번만 만듦)
WEB_PASSWORD=처음비밀번호      # ← 반드시 바꾸기. 0.0.0.0으로 열 때 계정이 없으면 시작하지 않음

# ── 모듈 켜기/끄기 ──
WTM_ENABLED=true              # 웹툰 다운로더
GDW_ENABLED=true              # 드라이브 변경 감시 (안 쓰면 false)
TGUP_ENABLED=true             # 텔레그램 자동 올리기
MINI_ENABLED=true             # 미니게임

# ── BookOasis와 연결 (받은 웹툰을 바로 스캔, 드라이브 변경 감시) ──
BOOKOASIS_URL=http://127.0.0.1:5930
WEBHOOK_TOKEN=BookOasis의_.env와_같은_값
```

BookOasis DB에 직접 붙이면(권장) 보관함 목록·이미 등록된 파일 건너뛰기·스캔 일정이 BookOasis와 똑같이 동작합니다:

```ini
BOOKOASIS_DB_URL=mysql://사용자:비밀번호@127.0.0.1:3306/bookoasis_{db_type}
```

(`{db_type}`은 general·adult·audiobook·video로 바뀝니다. DB 없이 쓰면 `data/libraries.manual.json`에 보관함을 직접 적습니다 - README "보관함 목록".)

---

## 5. 설정 점검하고 한 번 실행해 보기

```bash
cd /opt/bookoasis_assistant
sudo venv/bin/python app.py --check      # .env, rclone, BookOasis DB, WEBHOOK_TOKEN, 웹툰 경로 점검 (✗가 있으면 그 줄을 고침)
sudo venv/bin/python app.py              # 관리 화면 실행
```

`관리 화면: http://0.0.0.0:5931/` 줄이 나오면 성공입니다. 브라우저로 `http://서버IP:5931`에 들어가 보세요.
확인했으면 `Ctrl+C`로 끄고 다음 단계로.

`WEB_USER`/`WEB_PASSWORD`를 넣었으면 로그인 화면이, 비워 두었으면(`127.0.0.1`로 열 때만 가능) 관리자 계정 만들기 화면이 나옵니다.

![로그인 화면](images/02-login.png)

---

## 6. 서비스로 등록 (부팅할 때 자동 실행)

저장소의 `deploy/bookoasis_assistant.service`는 `/opt/bookoasis_assistant`, `root` 계정 기준입니다(이 문서와 같음).

```bash
sudo cp /opt/bookoasis_assistant/deploy/bookoasis_assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bookoasis_assistant
```

다른 폴더나 다른 계정으로 돌리려면 서비스 파일의 `User=`, `WorkingDirectory=`, `ExecStart=` 세 줄을 고친 뒤 복사하세요.
(다른 계정이면 그 계정이 `.env`·`data/`·웹툰 저장 경로에 쓸 수 있어야 합니다.)

확인:

```bash
systemctl status bookoasis_assistant           # active (running)
journalctl -u bookoasis_assistant -f           # 실시간 로그 (Ctrl+C로 나가기)
```

브라우저: `http://서버IP:5931` → 로그인 → 웹툰 다운로더 화면이 첫 화면입니다.

![첫 화면: 웹툰 다운로더](images/03-webtoon-list.png)

이제 [setup-guide.md](setup-guide.md)를 따라 저장 경로·쿠키·감시 폴더·자동 올리기를 설정하세요.
접속이 안 되면 방화벽: `sudo ufw allow 5931/tcp`

---

## 7. 업데이트

화면 왼쪽 위 버전 배지가 빨갛게 바뀌면 새 버전이 있다는 뜻입니다(설정 > 정보에도 나옴).

```bash
cd /opt/bookoasis_assistant
sudo git pull
sudo venv/bin/pip install -r requirements.txt     # 새 패키지가 생겼을 때만 실제로 설치됨 (매번 해도 안전)
sudo systemctl restart bookoasis_assistant
```

`.env`와 `data/`는 git에 올라가지 않으므로 업데이트해도 그대로입니다.
멈출 때 진행 중인 작업을 마치느라 최대 40초쯤 걸릴 수 있습니다.

---

## 8. 백업

```bash
sudo systemctl stop bookoasis_assistant
sudo tar czf ~/boa_backup.tgz -C /opt/bookoasis_assistant .env data
sudo systemctl start bookoasis_assistant
```

`data/`에 구독·다운로드 이력·쿠키(`data/webtoon/cookies/`)·감시 기록·텔레그램 로그인 세션(`data/tgup/`)이 모두 있습니다.

---

## 9. 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `error: externally-managed-environment` | `pip` 대신 `venv/bin/pip` (3단계) |
| `로그인 계정이 없어 0.0.0.0에 열 수 없습니다` | `.env`에 `WEB_USER`/`WEB_PASSWORD`를 넣거나, `WEB_HOST=127.0.0.1`로 열어 화면에서 계정을 만든 뒤 바꾸기 |
| 사이드바에 텔레그램 자동 올리기가 없음 | `venv/bin/pip install -r requirements.txt`를 안 했거나(aiohttp·telethon) `TGUP_ENABLED=false` |
| `--check`에서 rclone ✗ | `.env`의 `RCLONE_PATH`(실행 파일), `RCLONE_CONFIG`(rclone.conf 경로) 확인 |
| `--check`에서 스캔 요청 ✗ | `BOOKOASIS_URL`이 이 서버에서 닿는지, `WEBHOOK_TOKEN`이 BookOasis `.env`와 같은지 |
| 받은 웹툰이 BookOasis에 안 잡힘 | 웹툰 저장 경로가 BookOasis 보관함 경로 안인지, BookOasis DB 연결(`BOOKOASIS_DB_URL`)이 되는지 |
| 서비스가 `failed` | `journalctl -u bookoasis_assistant -n 50`으로 마지막 오류 확인 |
| 윈도우에서 드라이브 감시 오류 | 드라이브 변경 감시는 리눅스 전용입니다. `GDW_ENABLED=false` |

로그 파일: 서비스 로그는 `journalctl`, 드라이브 감시 워커는 `data/worker.log`, 웹툰은 `data/webtoon/` 아래.

---

## 주요 `.env` 값

| 변수 | 기본값 | 설명 |
|---|---|---|
| `WEB_HOST` / `WEB_PORT` | `127.0.0.1` / `5931` | 관리 화면 주소 |
| `WEB_USER` / `WEB_PASSWORD` | `admin` / (없음) | 첫 관리자 (사용자가 없을 때 한 번만) |
| `DATA_DIR` | `data` | 기록·쿠키·로그 폴더 |
| `WTM_ENABLED` / `GDW_ENABLED` / `TGUP_ENABLED` / `MINI_ENABLED` | `true` | 모듈 켜기/끄기 |
| `GDWPLX_ENABLED` | `false` | 드라이브 변경 감시 FOR PLEX (Plex 부분 스캔) |
| `RCLONE_PATH` / `RCLONE_CONFIG` | `rclone` / (기본 위치) | rclone 실행 파일·설정 파일 |
| `BOOKOASIS_URL` / `WEBHOOK_TOKEN` | `http://127.0.0.1:5930` / (없음) | BookOasis 스캔 요청 |
| `BOOKOASIS_DB_URL` | (없음) | BookOasis DB (`{db_type}` 템플릿) |
| `PLEX_URL` / `PLEX_TOKEN` / `PLEX_PATH_MAP` | (없음) | Plex (드라이브 감시 Plex 스캔, 자동 올리기 Plex 규칙) |
| `WTM_DOWNLOAD_ROOT` 등 `WTM_…` | | 웹툰 저장 경로·임시 폴더·알림 (화면에서 넣어도 됨) |
| `TGUP_API_ID` / `TGUP_API_HASH` | (없음) | 자동 올리기 텔레그램 API (화면에서 넣어도 됨) |
| `TGUP_DISCORD_WEBHOOK_URL` | (없음) | 자동 올리기 디스코드 알림 (화면에서 넣어도 됨) |
| `FFMPEG_PATH` / `FFPROBE_PATH` | PATH에서 찾음 | ffmpeg 경로를 따로 줄 때 |
| `LIB3D_URL` | (없음) | 따로 설치한 BookOasis 3D 서재 주소 (사이드바 메뉴) |

전체 목록은 `env.example`과 README의 ".env" 표를 보세요.
