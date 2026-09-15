## ⚡️ pm2로 봇 관리하기

pm2는 Node.js 기반 프로세스 관리자이지만, Python 실행도 지원합니다. 서버 재부팅 시 자동 실행, 로그 관리, 프로세스 모니터링이 가능합니다.

## TelegramBot 운영/개발 가이드 (systemd 기준)

### 1. .env 파일 준비
- 프로젝트 루트 또는 앱 디렉토리에 .env 파일을 생성하고 환경변수 입력

### 2. systemd 서비스 등록 및 실행
1. 서비스 유닛 파일(예: telegrambot.service)에서 [Service] 섹션에 EnvironmentFile=/path/to/.env 지정
2. 아래 명령어로 서비스 등록 및 실행
  ```bash
  sudo cp telegrambot.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable telegrambot
  sudo systemctl start telegrambot
  sudo systemctl status telegrambot
  sudo journalctl -u telegrambot -f
  ```

### 3. 로컬 개발
- .env 파일만 있으면 python-dotenv로 자동 로드됨 (코드에 load_dotenv 추가)
- systemd 없이 직접 python run_bot.py 실행 가능

---

## 참고 사항

- 봇 이름은 `mesids_bot`으로 설정되어 있습니다. (`core/config.py`의 `BOT_NAMES`에서 변경 가능)
- 로그 파일은 `LOG_DIR` 환경변수로 지정된 디렉토리 아래 `mesids_bot/service.jsonl`에 저장됩니다. 기본값은 `/var/log/agora/telegrambot/mesids_bot/`입니다.
- Gemini AI 모델은 `gemini-2.5-flash-lite`를 사용합니다. (필요시 `core/kernel/agents/gemini.py`에서 변경)
- 사용량 카운트 및 알림 기능은 별도 모듈(`usage_counter.py`)로 분리되어 있어 유지보수가 용이합니다.

---
- **Node.js** 필요 (pm2 설치용)
- **pm2**: 프로세스 매니저 (개발/운영 모두 권장)
- **systemd**: 운영 환경 자동 실행 시 필요
- **tiktoken**: 토큰 최적화/메시지 전처리(lean/token_utils) 사용 시 필요
- **pytest**: 테스트 자동화 필요 시

### 주요 명령어/설정
- `.env` 파일로 환경변수 관리 (예시 아래 참고)
- `python3 -m venv .venv`로 가상환경 생성 및 활성화
- `pip install -r requirements.txt`로 의존성 설치
- pm2, systemd 모두 지원 (아래 예시 참고)

---

## 🚀 설치 및 초기 설정

### 1. 필수 패키지 설치

```bash
cd ~/app/telegrambot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```


`requirements.txt` 주요 항목:

```txt
python-dotenv>=1.0.0
google-genai>=1.0.0
python-telegram-bot[job-queue]>=20.0
aiofiles>=23.2.0
pytz>=2023.3
aiohttp>=3.0.0
nest_asyncio>=1.5.0
sniffio>=1.3.0
httpx>=0.27.0
tiktoken>=0.5.2
pytest>=7.0.0
```

### 2. 환경 변수 설정

`.env` 파일을 생성하고 다음 내용을 입력하세요.

```bash
nano .env
```

```
TELEGRAM_TOKEN=여기에_텔레그램_봇_토큰_입력
GEMINI_KEY=여기에_구글_Gemini_API_키_입력
TELEGRAM_CHAT_ID=관리자_텔레그램_ID          # 사용량 알림을 받을 계정
TOTAL_QUOTA=1000                          # 일일 최대 요청 수 (모델에 따라 조정)
```

**보안을 위해 권한 설정:**

```bash
chmod 600 .env
```

### 3. 파이썬 패키지 임포트 경로 설정

```bash
touch core/__init__.py
touch core/kernel/__init__.py
touch core/kernel/services/__init__.py
touch core/kernel/agents/__init__.py
```

필요시 기존 파일의 임포트 경로를 수정합니다.

```bash
sed -i 's/from kernel\./from core.kernel./g' core/kernel/**/*.py
```

## 📊 사용량 모니터링 및 데이터 관리

이 봇은 다음과 같은 자체 모니터링 기능을 포함합니다.

### 사용량 카운트
- 모든 메시지 응답 성공 시 `data/usage_count.json`에 일일 사용량이 기록됩니다.
- 파일 형식: `{"date": "2026-03-17", "count": 123}`

### 관리자 알림
- 일일 할당량(`TOTAL_QUOTA`) 대비 남은 비율이 **50%, 20%, 10%** 에 도달하면 관리자(`TELEGRAM_CHAT_ID`)에게 텔레그램 알림이 전송됩니다.
- 중복 알림을 방지하기 위해 `data/notified.json`에 오늘 날짜와 전송한 임계치가 저장됩니다.

### 임시 파일 자동 정리
- `data/temp/` 디렉토리에 저장된 파일은 **24시간 이상 경과 시 매일 0시에 자동 삭제**됩니다.
- 이 기능은 봇 실행 시 내부적으로 `JobQueue`를 사용하여 구현되어 있습니다.
- 별도의 크론탭 설정 없이, 봇이 실행 중이면 자동으로 동작합니다.

### 로그 파일 위치
- 로그 파일은 `LOG_DIR` 환경변수로 지정된 디렉토리 아래 `mesids_bot/service.jsonl`에 저장됩니다.
- 기본값: `/var/log/agora/telegrambot/mesids_bot/service.jsonl` (`.env`에서 `LOG_DIR` 변경 가능)
- 로그는 JSON Lines 형식이며, 10MB 단위로 로테이션됩니다 (최대 5개 백업).

## 🏃 수동 실행

```bash
cd ~/app/telegrambot
source .venv/bin/activate
python run_bot.py
```

- 실행 중지는 `Ctrl+C`를 누릅니다.
- 최초 실행 시 `data/` 폴더와 하위 디렉토리가 자동 생성됩니다.

## ⚙️ systemd 서비스 등록 (재부팅 시 자동 실행)

### 1. 서비스 파일 생성

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

```ini
[Unit]
Description=Telegram Bot Service
After=network.target

[Service]
User=azureuser
WorkingDirectory=/home/azureuser/app/telegrambot
Environment="PATH=/home/azureuser/app/telegrambot/.venv/bin"
EnvironmentFile=/home/azureuser/app/telegrambot/.env
ExecStart=/home/azureuser/app/telegrambot/.venv/bin/python /home/azureuser/app/telegrambot/run_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. 서비스 활성화 및 시작

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service
sudo systemctl start telegram-bot.service
```

### 3. 서비스 상태 확인

```bash
sudo systemctl status telegram-bot.service
```

### 4. 실시간 로그 확인

```bash
sudo journalctl -u telegram-bot.service -f
```

## 🔧 서비스 관리 명령어

| 작업 | 명령어 |
|------|--------|
| 서비스 시작 | `sudo systemctl start telegram-bot.service` |
| 서비스 중지 | `sudo systemctl stop telegram-bot.service` |
| 서비스 재시작 | `sudo systemctl restart telegram-bot.service` |
| 서비스 상태 확인 | `sudo systemctl status telegram-bot.service` |
| 부팅 시 자동 실행 활성화 | `sudo systemctl enable telegram-bot.service` |
| 부팅 시 자동 실행 비활성화 | `sudo systemctl disable telegram-bot.service` |
| 실시간 로그 확인 | `sudo journalctl -u telegram-bot.service -f` |
| 최근 로그 50줄 보기 | `sudo journalctl -u telegram-bot.service -n 50` |

## 📂 데이터 파일 확인

```bash
# 사용량 확인
cat ~/app/telegrambot/data/usage_count.json

# 알림 기록 확인
cat ~/app/telegrambot/data/notified.json

# 로그 파일 확인 (운영 기본 경로)
ls -la /var/log/agora/telegrambot/mesids_bot/
```

## 🔄 재부팅 테스트

서버를 재부팅하여 봇이 자동으로 실행되는지 확인합니다.

```bash
sudo reboot
```

재접속 후 서비스 상태 확인:

```bash
sudo systemctl status telegram-bot.service
```

## 🧹 불필요한 파일 정리 (선택)

```bash
# 백업 파일 삭제
rm ~/app/telegrambot/config.py.bak
rm ~/app/telegrambot/run_bot.py.bak

# 이전 로그 디렉토리 삭제 (모든 로그가 data/logs/로 이전된 경우)
rm -rf ~/app/telegrambot/logs

# 파이썬 캐시 삭제
find ~/app/telegrambot -type d -name "__pycache__" -exec rm -rf {} +
```

## 📝 참고 사항

- 봇 이름은 `mesids_bot`으로 설정되어 있습니다. (`core/config.py`의 `BOT_NAMES`에서 변경 가능)
- 로그 파일은 `LOG_DIR` 환경변수로 지정된 디렉토리 아래 `mesids_bot/service.jsonl`에 저장됩니다. 기본값은 `/var/log/agora/telegrambot/mesids_bot/`입니다.
- Gemini AI 모델은 `gemini-2.5-flash-lite`를 사용합니다. (필요시 `core/kernel/agents/gemini.py`에서 변경)
- 사용량 카운트 및 알림 기능은 별도 모듈(`usage_counter.py`)로 분리되어 있어 유지보수가 용이합니다.

## 🎉 완료

이제 텔레그램 봇이 서버에서 안정적으로 실행되며, 사용량 모니터링, 자동 로그 관리, 임시 파일 정리 기능이 함께 동작합니다.

---

## 🧪 테스트/로컬 실행 및 관리 규칙 (2026-03 최신)

### 테스트 전용 실행 파일 관리
- 테스트용 진입점(run_testbot.py, run_test_bot.py 등)은 .gitignore와 .stignore에 추가하여 git/Syncthing 동기화에서 제외합니다.
- 필요시 복사/이름변경하여 사용하고, 운영 배포에는 포함하지 않습니다.

### 테스트 토큰 우선 적용
- 테스트 실행 파일은 `.env`의 `TELEGRAM_TEST_TOKEN`이 있으면 우선 사용, 없으면 `TELEGRAM_TOKEN`을 사용합니다.
- 운영/테스트 봇을 완전히 분리하여 실험할 수 있습니다.

### 로컬 실행과 서버 실행의 차이
- 로컬에서 `python run_testbot.py`로 실행하면 터미널이 점유(폴링 대기)되고, 실시간 로그가 콘솔에 바로 찍힙니다.
- 서버에서는 systemd/supervisor/docker 등으로 백그라운드 실행되어 터미널이 즉시 반환되고, 로그는 파일로 기록됩니다.
- 로컬에서 운영처럼 "대기창+실시간 로그"를 원하면 `nohup python run_testbot.py > testbot.log 2>&1 &`로 백그라운드 실행 후, `tail -f testbot.log`로 로그를 확인하세요.

### 기타 변경점 요약
- requirements.txt에 `python-telegram-bot[job-queue]` 명시 (JobQueue 필수)
- 테스트 실행 파일(run_testbot.py 등)은 .gitignore, .stignore 모두에 추가
- .env에서 TELEGRAM_TEST_TOKEN 등 테스트 토큰은 필요시만 유지, 테스트 종료 후 삭제 권장

---

## 🛡️ 운영 안전/폴백/복구 가이드 (2026-03 최신)

### Gemini API 완전 비활성화(운영 안전)
- 서비스 중지 및 disable:
  ```bash
  sudo systemctl stop gemini.service
  sudo systemctl disable gemini.service
  ```
- (선택) 완전 차단(mask):
  ```bash
  sudo mv /etc/systemd/system/gemini.service /etc/systemd/system/gemini.service.disabled.bak
  sudo ln -s /dev/null /etc/systemd/system/gemini.service
  sudo systemctl daemon-reload
  systemctl status gemini --no-pager  # masked 표시 확인
  ```
- (원복) unmask 및 복구:
  ```bash
  sudo rm /etc/systemd/system/gemini.service
  sudo mv /etc/systemd/system/gemini.service.disabled.bak /etc/systemd/system/gemini.service
  sudo systemctl daemon-reload
  sudo systemctl enable --now gemini.service
  ```

### 텔레그램봇 운영 체크리스트
- `.env`는 반드시 **AI_MODE=notifier** (알림 전용)
- 인라인 주석 금지(값 뒤에 # ... 금지, 별도 줄에 주석)
- 서비스 상태/로그:
  ```bash
  sudo systemctl status telegrambot --no-pager
  sudo journalctl -u telegrambot.service -n 60 --no-pager
  ```
- 로그/데이터/권한: `/srv/agora/logs/telegram_bot/`, `/srv/agora/data/telegram_bot/`, `azureuser:azureuser` 유지

### (선택) run_bot.py 폴백 패턴 예시
```python
try:
    ai_agent = get_ai_agent("gemini", config.GEMINI_KEY)
except Exception as e:
    logger.error(f"Gemini init 실패: {e} -> notifier fallback")
    class DummyAgent:
        async def generate(self, prompt: str) -> str:
            return "[AI 비활성화 모드: 답변 없음]"
    ai_agent = DummyAgent()
```

### Gemini 필요 시 복구
- 코어 방식: `.env`에 `AI_MODE=gemini`, `GEMINI_KEY=...` 후 재시작
- REST 방식: unmask/enable, `.env`에 `AI_MODE=rest`, `GEMINI_REST_URL=...` 후 재시작
- 반드시 쿼터/과금 상태 확인(429 방지)

---