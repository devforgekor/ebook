# Watchdog × news 수집 감시 설계 — 웹/깃허브 조사 보고서

- 작성일: 2026-09-09
- 배경: `devforge-news.service`가 9/7 18:00 UTC 이후 **매 실행 900s 타임아웃**으로 사망.
  타이머는 정상 발동하지만 run이 끝까지 못 가서 Neon 동기화가 끊김 → 사이트에 뉴스가 1~2건만 노출.
- 질문: "devforge watchdog(60s 감시)이 이를 감시·관리하도록 수정하는 게 맞는가?"
- 방법: 웹 + GitHub 조사 후, 스케줄 배치(oneshot) 감시의 업계 원칙과 DevForge 구조에 매핑.

---

## 1. 조사 근거 (요약)

| # | 원칙 | 출처 |
|---|------|------|
| A | **타이머 존재 ≠ 작업 성공.** 성공 신호는 작업 "완료 후"에만 보낸다 (시작/중간에 보내지 않음) | QuietPulse, Healthchecks.io |
| B | 배치 실패 유형 분류 — "never started / **hung** / failed mid-run / succeeded-but-wrong / ran twice". hung은 프로세스만으론 안 잡히고 **최대 수행시간 초과 + 성공 heartbeat 부재**로만 감지 | johal.in |
| C | 감지 패턴 3종: **Push heartbeat / Freshness query(결과물 기준) / Pull 상태파일** — 신뢰성은 freshness가 refactor-proof로 최고 | johal.in |
| D | grace window는 p99 실측 기준, **경고(warning) 단계 → dead-zone(페이지)** 2티어 | johal.in, Healthchecks.io |
| E | `Type=oneshot` 자동 재시작은 의미·구현 모두 논쟁 대상. 단기 재시도가 아닌 **OnFailure= / 외부 watcher kick** 권장 | systemd issue #2582/#23696, Unix&Linux SE |
| F | systemd 감시 표준 패턴: `ExecStartPre …/start` → 작업 → `ExecStopPost …/$EXIT_STATUS` (시작/성공/실패 3신호), `runitor` 래퍼 | Healthchecks.io, bdd/runitor |
| G | **freshness만으로는 "죽었는데 표면상 fresh한 파이프라인"을 놓침 → heartbeat 보완.** 반대로 heartbeat만으론 "돌았지만 0건 처리"를 놓침 → 결과물 불변식(row count) 병행 | PipeCode, Webalert, Streamkap |
| H | 시스템 타이머(cron 아님)는 중복 실행(co-fire)이 없으므로 overlap lock 불필요 | johal.in |

---

## 2. 상세 근거

### A. 성공 신호는 "완료 후"에만 (QuietPulse / Healthchecks.io)

- timer가 활성 상태여도 service 실패/script hang/중요 단계 생략이 가능 → "실행 완료 여부"는 heartbeat로만 판정.
- `Do not ping at the start. Do not ping before the upload … Ping after success.` — **성공 경로 끝**에만 ping.
- Healthchecks.io 문서의 systemd 예:
  ```ini
  [Service]
  Type=oneshot
  ExecStartPre=-curl -fsS .../start          # 선택(수행시간 측정용)
  ExecStart=rsync -a ...                      # 실제 작업
  ExecStopPost=curl -fsS .../${EXIT_STATUS}   # 종료코드 전달(0=성공)
  ```
  - `-` 접두사: curl 실패가 본 작업 실행을 막지 않게.
  - `$EXIT_STATUS`(0~255)로 성공/실패 구분.
  - `--retry 5`로 일시 장애 내 ping 누락 방지.
- **운영 방안 대응**: collector 성공 지점(`run()` 마지막, Neon sync 이후)에서만
  `messenger.heartbeat("news_collector")` 호출. timeout으로 kill되면 heartbeat가 안 찍히므로
  "돌긴 도는데 완료 못 함"을 정확히 반영. Healthchecks.io의 `$EXIT_STATUS` 전달 대신 DB heartbeat로 동일 효과.

### B. 우리 사례 = "hung" 유형 (johal.in 분류)

| 실패 유형 | 관찰 | 일반 감시가 놓치는 이유 | 감지법 |
|---|---|---|---|
| Never started | 무소음 | 요청=로그 없음 | heartbeat/freshness |
| **Started, hung** ← 본 사례 | 프로세스 alive, 진행 없음 | CPU idle, crash 신호 없음 | **max-duration timeout + completion heartbeat** |
| Failed mid-run | 에러 1회 후 조용 | 아무도 로그 안 읽음 | exit code + 완료 heartbeat |
| Succeeded but wrong | 2초만에 "완료" | 0건 처리=성공처럼 보임 | 불변식(row count) |

- `devforge-news.service`는 정확히 "Started, hung": 900s kill 직전까지 CPU 1~2분 사용 후 idle,
  crash 신호 없음, journal에 error 없음 → **타이머 idle 검사(`check_timer`)로는 절대 탐지 불가**.
  systemd의 `result=timeout`(unit failed)조차 watchdog `svc_active`는 "active/activating"만 보므로 놓침.

### C. 감지 패턴 3종과 신뢰성 (johal.in)

1. Push heartbeat — 가장 단순, 단 호스트/네트워크와 함께 죽으면 무소음(가끔은 그게 맞음).
2. **Freshness query — 결과물(DB) 기준.** job이 이사/리팩터링돼도 동작 → 최고의 refactor-proof.
   ```sql
   SELECT CASE WHEN max(collected_at) < now() - interval '7 hours'
               THEN 'STALE' ELSE 'OK' END FROM news_articles;
   ```
3. Pull 상태파일 — duration/row count 등 메타데이터로 "ran"을 "ran sanely"로 승격.

- DevForge 매핑: 수집기의 **진짜 산출물은 Neon DB**(사용자 노출)이므로 이상적으로는
  "collector 성공 heartbeat" + "Neon 최신 수집 fresh 유지"를 함께 봐야 함.
  단, local DB freshness는 hung 중에도 row가 찍히므로(본 사례: local 18건 vs Neon 2건)
  **local freshness는 성공 신호가 될 수 없음** — 반드시 "완료 heartbeat"가 주 신호.

### D. Grace window와 2티어 알림 (johal.in)

- grace는 "관찰된 p99 duration + upstream 지연"으로 산정, 낙관치 금지. (6h 주기 → 6h + 여유 ≈ 7h, 현재 `max_idle=25200`과 일치)
- warning(티켓) → dead-zone(페이지) 2티어: 야간 슬로우 화요일로 사람을 깨우지 않게.
- 지연된 정상 실행은 alert를 자동 해제(re-arm).
- DevForge 매핑: watchdog 30분 heartbeat 요약(Slack) = ticket 성격, `send_alert` = page 성격.

### E. oneshot 자동 재시작은 부적합 (systemd GitHub issue / SE)

- systemd issue #2582: `Restart=`가 oneshot에 동작하지만 의미 논쟁 지속 —
  `Restart=on-success`는 oneshot에서 금지해야 한다는 의견, 구현도 불안정.
- Unix&Linux SE: "oneshot 자동 재시도는 `Restart=on-failure`" 로 가능하나 **즉시 재시도**가 기본.
- 15분 걸리고 외부 rate-limit(429)에 걸려 hung 되는 job을 즉시/60초 간격 재시도하는 것은
  retry storm + API 할당량 추가 소진(429 악화)만 유발.
- **따라서 news.service를 `SERVICE_TARGETS`(상시 서비스 restart 모델)에 넣는 것은 금지**가 맞음.
  대신: (1) 60s 단위 재시작 금지, (2) stale 시 "1회 kick + backoff/circuit" 제한 복구.

### F. systemd 작업 감시 표준 (Healthchecks.io + runitor)

- 오픈소스 표준 구현: `ExecStartPre /start` + `ExecStopPost /$EXIT_STATUS`, `runitor`(Go)가
  start/success/fail 신호 + 출력 캡처 래핑. 동일 개념을 collector 내부 heartbeat로 구현 가능.
- GitHub 실무 프로젝트: `healthchecks/healthchecks`(셀프호스트 cron/heartbeat 모니터, Django),
  `bdd/runitor`(명령 래퍼), `dimo414/task-mon`(CLI), `dripips/pulse`(Go+SQLite dead man's switch).

### G. heartbeat ↔ freshness 상호보완 (PipeCode/Webalert/Streamkap)

- "freshness alert가 '최근 갱신된 테이블'을 못 잡는 경우 = 죽었지만 fresh한 파이프라인" → heartbeat 필요.
- 반대로 heartbeat만 있으면 "돌았지만 0건/엉뚱한 처리"를 놓침 → **산출물 불변식**(일별 Neon row 수 기대치) 병행 권장.

### H. 중복 실행

- systemd `OnCalendar`는 cron과 달리 동시 실행이 없어 overlap lock 불필요(이미 해결됨).

---

## 3. 결론 및 DevForge 적용 권고

**"watchdog에 넣되, heartbeat 형태로, 재시작은 제한적으로."** (타이머 idle 검사는 유지하되 대체 불가)

1. **주 신호 = collector 성공 heartbeat** (Healthchecks.io 원칙 A, johal.in B/C)
   - `collector.py` `run()` 성공 완료 지점(Neon sync + revalidation 이후)에서만
     `heartbeat("news_collector")` 기록. kill/예외 시 heartbeat 없음 → stale 판정.
   - `HEARTBEAT_WORKERS`에 `news_collector: {max_age: 25200}` 등록 (6h 주기 + grace).
   - 코드 선행 조건(필수): 429 회로차단 + sync 무조건 수행으로 run이 반드시 완료되게 해야
     watchdog이 "정상 완료"를 볼 수 있음. (watchdog 추가가 근본 원인 수정을 대체하지 못함)

2. **복구는 "stale 시 1회 kick + backoff"로 제한** (_run_timers kick 모델, E)
   - `SERVICE_TARGETS`(60s 재시작) 절대 금지. 6h 주기 배치가 stale면 정시 다음 주기까지
     공백이 길므로, watchdog action으로 최대 1회 kick + circuit(3회 실패 시 중단)만 허용.

3. **2차 신호 = 산출물(freshness) 불변식** (C/G)
   - daily digest 등에서 "금일 Neon 신규 기사 수" 기대치 대비 검증 → succeeded-but-wrong/0건 방어.

4. **알림 2티어** (D)
   - stale → 이벤트(30분 heartbeat 요약) + Slack 알림. (현재 `check_heartbeats`는 stale를
     로그+이벤트만 기록하고 `send_alert`를 안 하므로, news 수준에선 전용 알림 추가 검토)

5. **grace는 실측 기반** — 완료 소요(p99) 기록을 heartbeat `detail`에 넣어 향후 grace 산정 근거로 사용.

---

## 4. 참고 문헌 (웹/GitHub)

- QuietPulse — Systemd Timer Monitoring: https://quietpulse.xyz/blog/systemd-timer-monitoring
- Healthchecks.io — Monitoring systemd tasks: https://healthchecks.io/docs/monitoring_systemd_tasks/
- johal.in — Cron Job Monitoring / Dead Man's Switches: https://johal.in/cron-job-dead-man-switch-monitoring-guide
- PipeCode — Data Freshness & SLA: Heartbeats vs Freshness: https://pipecode.ai/blogs/data-freshness-sla-monitoring-budgets
- Webalert — Never Miss a Failed Background Task: https://web-alert.io/blog/cron-job-monitoring-background-tasks
- OneUptime — Heartbeat & Dead Man's Switch Alerts: https://oneuptime.com/blog/post/2026-02-06-heartbeat-dead-man-switch-opentelemetry-pipeline/view
- UpDog — What is a Dead Man's Switch: https://updog.watch/learn/what-is-dead-mans-switch
- GitHub healthchecks/healthchecks: https://github.com/healthchecks/healthchecks
- GitHub bdd/runitor: https://github.com/bdd/runitor
- GitHub dimo414/task-mon: https://github.com/dimo414/task-mon
- GitHub dripips/pulse: https://github.com/dripips/pulse
- systemd issue #2582 (Restart + oneshot): https://github.com/systemd/systemd/issues/2582
- systemd issue #23696 (timer oneshot retry): https://github.com/systemd/systemd/issues/23696
- Unix&Linux SE — oneshot retry/failure: https://unix.stackexchange.com/questions/272313/
