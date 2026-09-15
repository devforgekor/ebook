# AGORA Scheduler 운영자 치트시트 & 문서

## 주요 명령어

```bash
# 타이머 동기화 (실제 적용)
sudo /home/azureuser/agora/.venv/bin/python -m core.kernel.services.scheduler.sync_timers \
  /home/azureuser/agora/core/kernel/services/scheduler/configs/schedules.yaml --remove-orphans

# 드라이런(적용 없이 결과만 확인)
sudo /home/azureuser/agora/.venv/bin/python -m core.kernel.services.scheduler.sync_timers \
  /home/azureuser/agora/core/kernel/services/scheduler/configs/schedules.yaml --dry-run

# 타이머 목록 확인
systemctl list-timers --all | grep agora-

# 즉시 1회 실행(트리거)
sudo systemctl start agora-reporter-monthly.service

# 상태 확인
systemctl status agora-reporter-monthly --no-pager

# 로그 확인
journalctl -u agora-reporter-monthly.service -n 100 --no-pager

# OnCalendar 검증
systemd-analyze calendar "*-01,04,07,10 00:05:00"
```

---

## 구조 설명

- configs/schedules.yaml : 모든 주기 작업 선언 (systemd timer/service)
- templates/unit.service.j2, unit.timer.j2 : systemd 유닛 템플릿
- sync_timers.py : YAML → systemd 유닛 자동 동기화 스크립트

---

## 운영 팁
- schedules.yaml만 수정하면 systemd 유닛이 자동으로 관리됩니다.
- orphan(낡은 타이머)도 자동 정리되어 운영 실수 방지
- 드라이런으로 변경사항을 미리 검토 가능
- systemd-analyze calendar로 OnCalendar 문법 검증 가능
- .env 등 민감값은 Git에 저장하지 않고 서버에서만 관리

---

## 참고
- systemd, Jinja2, PyYAML, Python 3.11+
- 운영 자동화/CI/CD 연동 권장 (예: GitHub Actions self-hosted runner)
