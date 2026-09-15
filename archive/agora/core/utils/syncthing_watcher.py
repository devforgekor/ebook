# agora/core/kernel/utils/syncthing_watcher.py

import argparse
import os
import re
import shutil
import signal
import smtplib
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Tuple

# ---------------------------
# 설정/환경
# ---------------------------

DEFAULT_ROOT = Path(os.getenv("AGORA_ROOT", "/home/azureuser/agora"))
DEFAULT_BACKUP_ROOT = DEFAULT_ROOT / "_backup"
DEFAULT_LOG_FILE = DEFAULT_ROOT / "syncthing_watch.log"

# 메일 알림(선택)
ENV_SMTP = {
    "host": os.getenv("SMTP_HOST", ""),          # 예: smtp.gmail.com
    "port": int(os.getenv("SMTP_PORT", "587")),  # 일반적으로 587(STARTTLS)
    "user": os.getenv("SMTP_USER", ""),
    "password": os.getenv("SMTP_PASS", ""),
    "to": os.getenv("MAIL_TO", ""),
    "from_": os.getenv("MAIL_FROM", os.getenv("SMTP_USER", "")),  # 기본 from=SMTP_USER
}

# 감시/보관 정책
BASE_INTERVAL_SEC = int(os.getenv("WATCH_BASE_INTERVAL_SEC", "10"))     # 10초 시작
MAX_INTERVAL_SEC = int(os.getenv("WATCH_MAX_INTERVAL_SEC", "7200"))     # 2시간(7200초) 캡
RETENTION_DAYS = int(os.getenv("WATCH_RETENTION_DAYS", "7"))            # 7일 보관

# 탐지 패턴
CONFLICT_PATTERN = re.compile(r".*sync-conflict.*", re.IGNORECASE)
STVERSIONS_NAME = ".stversions"

# 종료 플래그
_SHOULD_STOP = False


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(line: str, log_file: Path):
    text = f"[{_ts()}] {line}"
    print(text)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        # 로그 파일 문제로 실패해도 프로세스는 계속
        pass


@dataclass
class WatchConfig:
    root: Path
    backup_root: Path
    log_file: Path
    dry_run: bool = False
    backup_before_delete: bool = True
    retention_days: int = RETENTION_DAYS
    base_interval: int = BASE_INTERVAL_SEC
    max_interval: int = MAX_INTERVAL_SEC
    email: dict = None  # ENV_SMTP 형태(dict)


class SyncthingConflictWatcher:
    def __init__(self, cfg: WatchConfig):
        self.cfg = cfg

    # ---------- 메일 ----------
    def _send_mail(self, subject: str, body: str):
        email = self.cfg.email or {}
        host = email.get("host") or ""
        user = email.get("user") or ""
        password = email.get("password") or ""
        to = email.get("to") or ""
        from_ = email.get("from_") or user

        if not (host and user and password and to and from_):
            _log("메일 설정이 비어 있어 알림은 생략합니다.", self.cfg.log_file)
            return

        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = from_
        msg["To"] = to

        try:
            with smtplib.SMTP(host, email.get("port", 587), timeout=15) as s:
                s.starttls()
                s.login(user, password)
                s.sendmail(from_, [to], msg.as_string())
            _log(f"메일 알림 전송 완료 → {to} / 제목: {subject}", self.cfg.log_file)
        except Exception as e:
            _log(f"메일 알림 전송 실패: {e}", self.cfg.log_file)

    # ---------- 스캔 ----------
    def _scan(self) -> Tuple[List[Path], List[Path]]:
        conflicts: List[Path] = []
        stversions: List[Path] = []
        root = self.cfg.root

        for dirpath, dirnames, filenames in os.walk(root):
            dpath = Path(dirpath)

            # .stversions 디렉터리 수집
            if STVERSIONS_NAME in dirnames:
                stversions.append(dpath / STVERSIONS_NAME)

            # 충돌 파일 수집
            for fn in filenames:
                if CONFLICT_PATTERN.match(fn):
                    conflicts.append(dpath / fn)

        return conflicts, stversions

    # ---------- 백업/삭제 ----------
    def _backup_dir(self) -> Path:
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        bdir = self.cfg.backup_root / f"syncthing_{ts}"
        return bdir

    def _backup_and_delete(
        self, conflicts: List[Path], stversions: List[Path]
    ) -> Path:
        """
        발견된 파일/디렉터리를 백업 후 삭제. (dry_run이면 이동/삭제하지 않음)
        return: 백업 디렉터리(실행 시점) 경로 (dry_run이면 생성만 안 할 수 있음)
        """
        dry = self.cfg.dry_run
        backup_first = self.cfg.backup_before_delete

        backup_dir = self._backup_dir()
        conflicts_backup = backup_dir / "conflicts"
        stversions_backup = backup_dir / "stversions"

        if not dry and backup_first:
            conflicts_backup.mkdir(parents=True, exist_ok=True)
            stversions_backup.mkdir(parents=True, exist_ok=True)

        # 파일(충돌 파일)
        for p in conflicts:
            if dry:
                _log(f"[DRY-RUN] 충돌 파일 발견: {p}", self.cfg.log_file)
                continue
            try:
                if backup_first:
                    dst = conflicts_backup / p.name
                    shutil.move(str(p), str(dst))
                    _log(f"백업 이동: {p} → {dst}", self.cfg.log_file)
                else:
                    p.unlink(missing_ok=True)
                    _log(f"삭제: {p}", self.cfg.log_file)
            except Exception as e:
                _log(f"파일 처리 실패({p}): {e}", self.cfg.log_file)

        # 디렉터리(.stversions)
        for d in stversions:
            if dry:
                _log(f"[DRY-RUN] .stversions 폴더 발견: {d}", self.cfg.log_file)
                continue
            try:
                if backup_first:
                    dst = stversions_backup / d.name
                    shutil.move(str(d), str(dst))
                    _log(f"백업 이동: {d} → {dst}", self.cfg.log_file)
                else:
                    shutil.rmtree(d, ignore_errors=True)
                    _log(f"삭제: {d}", self.cfg.log_file)
            except Exception as e:
                _log(f"디렉터리 처리 실패({d}): {e}", self.cfg.log_file)

        return backup_dir

    # ---------- 백업 보관기간 정리 ----------
    def _cleanup_old_backups(self):
        """
        backup_root 아래 syncthing_YYYY-mm-dd-HHMMSS 폴더 중,
        보관기간(retention_days) 지난 것은 모두 삭제
        """
        limit = datetime.now() - timedelta(days=self.cfg.retention_days)
        pattern = re.compile(r"^syncthing_\d{4}-\d{2}-\d{2}-\d{6}$")

        for child in self.cfg.backup_root.glob("syncthing_*"):
            if not child.is_dir():
                continue
            if not pattern.match(child.name):
                continue
            try:
                ts_str = child.name.replace("syncthing_", "")
                ts = datetime.strptime(ts_str, "%Y-%m-%d-%H%M%S")
            except Exception:
                continue

            if ts < limit:
                try:
                    shutil.rmtree(child, ignore_errors=True)
                    _log(f"백업 보관기간 만료 → 삭제: {child}", self.cfg.log_file)
                except Exception as e:
                    _log(f"백업 삭제 실패({child}): {e}", self.cfg.log_file)

    # ---------- 메인 루프 ----------
    def run(self):
        """
        감시 루프:
        - 초기 간격: base_interval (기본 10초)
        - 발견 못하면 간격을 2배씩 증가(최대 max_interval=2시간)
        - 한 번이라도 발견하면 즉시 처리(백업/삭제/메일), 간격을 다시 10초로 리셋
        - 2시간에 도달하면 이후 2시간 주기로 감시(발견되면 다시 10초부터)
        """
        interval = max(1, self.cfg.base_interval)
        max_interval = max(interval, self.cfg.max_interval)

        _log(
            f"감시 시작: root={self.cfg.root} backup_root={self.cfg.backup_root} "
            f"base={interval}s max={max_interval}s retention={self.cfg.retention_days}d "
            f"dry_run={self.cfg.dry_run} backup_first={self.cfg.backup_before_delete}",
            self.cfg.log_file,
        )

        while not _SHOULD_STOP:
            try:
                conflicts, stversions = self._scan()
                if conflicts or stversions:
                    # 발견됨 → 즉시 처리
                    _log(
                        f"DETECTED: 충돌 파일={len(conflicts)}, .stversions={len(stversions)}",
                        self.cfg.log_file,
                    )

                    # 메일 알림(상세 목록 포함)
                    try:
                        body_lines = []
                        if conflicts:
                            body_lines += ["[충돌 파일]"] + [str(p) for p in conflicts] + [""]
                        if stversions:
                            body_lines += ["[.stversions]"] + [str(d) for d in stversions] + [""]
                        self._send_mail(
                            "[Syncthing] 충돌/보관 파일 감지",
                            "\n".join(body_lines) if body_lines else "감지됨",
                        )
                    except Exception as e:
                        _log(f"메일 알림 중 오류: {e}", self.cfg.log_file)

                    # 백업 후 삭제
                    self.cfg.backup_root.mkdir(parents=True, exist_ok=True)
                    backup_dir = self._backup_and_delete(conflicts, stversions)

                    # 백업 보관기간 정리
                    self._cleanup_old_backups()

                    _log(f"처리 완료. 백업 위치: {backup_dir}", self.cfg.log_file)

                    # 간격 리셋
                    interval = max(1, self.cfg.base_interval)
                else:
                    # 미발견 → 지수 백오프
                    _log(f"OK: 없음. 다음 감시까지 {interval}s 대기", self.cfg.log_file)
                    self._sleep(interval)
                    interval = min(interval * 2, max_interval)
                    continue

                # 처리 직후 기본 간격으로 대기
                self._sleep(interval)
            except Exception as e:
                _log(f"루프 예외: {e}", self.cfg.log_file)
                # 문제 있어도 감시를 계속
                self._sleep(interval)
                interval = min(interval * 2, max_interval)

    def _sleep(self, seconds: int):
        """SIGINT/SIGTERM 수신 시 빠르게 종료 되도록 0.5초 단위로 쪼개서 대기"""
        end = time.time() + seconds
        while time.time() < end and not _SHOULD_STOP:
            time.sleep(0.5)


# ---------------------------
# CLI / Entry
# ---------------------------

def _signal_handler(signum, frame):
    global _SHOULD_STOP
    _SHOULD_STOP = True


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="syncthing_watcher",
        description="Syncthing 충돌 파일 감시/정리(백업/삭제/보관) + 지수 백오프 + 메일 알림",
    )
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=f"감시 루트 (기본: {DEFAULT_ROOT})")
    p.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT, help=f"백업 루트 (기본: {DEFAULT_BACKUP_ROOT})")
    p.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE, help=f"로그 파일 (기본: {DEFAULT_LOG_FILE})")
    p.add_argument("--dry-run", action="store_true", help="실제 이동/삭제 없이 감지만 수행")
    p.add_argument("--no-backup", action="store_true", help="백업 없이 즉시 삭제")
    p.add_argument("--retention-days", type=int, default=RETENTION_DAYS, help=f"백업 보관 기간 일수 (기본: {RETENTION_DAYS})")
    p.add_argument("--base-interval", type=int, default=BASE_INTERVAL_SEC, help=f"초기 감시 간격 초 (기본: {BASE_INTERVAL_SEC})")
    p.add_argument("--max-interval", type=int, default=MAX_INTERVAL_SEC, help=f"최대 감시 간격 초 (기본: {MAX_INTERVAL_SEC})")
    p.add_argument("--no-email", action="store_true", help="메일 알림 비활성화")
    return p


def main(argv=None):
    argv = argv or sys.argv[1:]
    args = build_arg_parser().parse_args(argv)

    email = None if args.no_email else ENV_SMTP

    cfg = WatchConfig(
        root=args.root,
        backup_root=args.backup_root,
        log_file=args.log_file,
        dry_run=args.dry_run,
        backup_before_delete=not args.no_backup,
        retention_days=args.retention_days,
        base_interval=args.base_interval,
        max_interval=args.max_interval,
        email=email,
    )

    # 신호 처리
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    watcher = SyncthingConflictWatcher(cfg)
    watcher.run()


if __name__ == "__main__":
    sys.exit(main())
