# Notifier 앱

독립적인 알림 중앙 서비스입니다. HTTP API를 통해 다양한 Provider(Telegram, Email 등)로 알림을 전송합니다.

## 환경변수 설정


`.env` 파일 또는 시스템 환경변수로 설정:

```
# Notifier API
NOTIFIER_API_KEY=your-secret-key
NOTIFIER_HOST=127.0.0.1
NOTIFIER_PORT=8001

# Telegram 알림
TELEGRAM_NOTICE_TOKEN=your_telegram_notice_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Email 알림 (선택)
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=your_smtp_user
SMTP_PASSWORD=your_smtp_password
EMAIL_FROM=your@email.com
EMAIL_TO=receiver@email.com

# 기타
DEBUG=False
LOG_DIR=logs
```

## 실행

```bash
cd apps/notifier
uvicorn api.main:app --reload --port 8001
```



## API 사용법

**엔드포인트**: `POST /v1/notify`  
**헤더**: `Authorization: Bearer {API_KEY}`  

**바디**:
```json
{
  "text": "알림 내용",
  "channel": "telegram"
}
```


1. .env 파일을 프로젝트 루트에 복사/생성
2. systemd 서비스 유닛 파일(예: notifier.service)에서 [Service] 섹션에 EnvironmentFile=/path/to/.env 지정
3. 아래 명령어로 서비스 등록 및 실행
  ```bash
  sudo cp notifier.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable notifier
  sudo systemctl start notifier
  sudo systemctl status notifier
  sudo journalctl -u notifier -f
  ```
4. 로그/데이터/임시폴더는 환경변수로 지정
3. `providers/__init__.py`의 `_providers` 딕셔너리에 추가
4. 필요시 core/config.py에 환경변수 추가

기존 API 코드는 수정할 필요 없습니다.
