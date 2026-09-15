import os
import sys
import yaml
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from jinja2 import Environment, FileSystemLoader

SYSTEMD_DIR = Path("/etc/systemd/system")
TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_USER = "azureuser"
DEFAULT_GROUP = "azureuser"

@dataclass
class StartLimit:
    interval_sec: int = 60
    burst: int = 5

@dataclass
class TimerSpec:
    name: str
    description: str
    working_dir: str
    exec_start: str
    environment_file: str
    on_calendar: str
    env: Dict[str, str] = field(default_factory=dict)
    user: str = DEFAULT_USER
    group: str = DEFAULT_GROUP
    restart_sec: int = 5
    wants: List[str] = field(default_factory=list)
    after: List[str] = field(default_factory=list)
    start_immediately: bool = False
    start_limit: Optional[StartLimit] = None
    disabled: bool = False

def sh(cmd: List[str], check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)

def read_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text())

def render(tpl_name: str, ctx: Dict[str, Any]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False, trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template(tpl_name)
    return tpl.render(**ctx).strip() + "\n"

def write_atomic(path: Path, content: str) -> bool:
    tmp = path.with_suffix(path.suffix + ".tmp")
    bak = path.with_suffix(path.suffix + ".bak")
    new = content
    old = path.read_text() if path.exists() else ""
    if old == new:
        return False
    if path.exists():
        shutil.copy2(path, bak)
    tmp.write_text(new)
    os.replace(tmp, path)
    return True

def validate_calendar(expr: str) -> str:
    import shutil
    if shutil.which("systemd-analyze") is None:
        print(f"[WARN] systemd-analyze not found, skipping calendar validation for: {expr}")
        return f"[SKIPPED] systemd-analyze not found: {expr}"
    try:
        out = sh(["systemd-analyze", "calendar", expr]).stdout.strip()
        return out
    except subprocess.CalledProcessError as e:
        raise ValueError(f"OnCalendar invalid: {expr}\n{e.stderr}")

def to_timer_spec(item: Dict[str, Any]) -> TimerSpec:
    sl = None
    if "start_limit" in item and item["start_limit"]:
        sl = StartLimit(
            interval_sec=int(item["start_limit"].get("interval_sec", 60)),
            burst=int(item["start_limit"].get("burst", 5)),
        )
    return TimerSpec(
        name=item["name"],
        description=item.get("description", item["name"]),
        working_dir=item["working_dir"],
        exec_start=item["exec_start"],
        environment_file=item.get("environment_file", "/home/azureuser/agora/.env"),
        on_calendar=item["on_calendar"],
        env=item.get("env", {}) or {},
        user=item.get("user", DEFAULT_USER),
        group=item.get("group", DEFAULT_GROUP),
        restart_sec=int(item.get("restart_sec", 5)),
        wants=item.get("wants", []) or [],
        after=item.get("after", []) or [],
        start_immediately=bool(item.get("start_immediately", False)),
        start_limit=sl,
        disabled=bool(item.get("disabled", False)),
    )

def sync(config_path: str,
         dry_run: bool = False,
         only: Optional[List[str]] = None,
         remove_orphans: bool = False,
         check_calendars: bool = True,
         restart_changed: bool = True,
         name_prefix: str = "agora-") -> None:

    cfg = read_yaml(Path(config_path))
    items = cfg.get("timers", [])
    specs: List[TimerSpec] = []
    for it in items:
        spec = to_timer_spec(it)
        if only and spec.name not in only:
            continue
        if check_calendars:
            validate_calendar(spec.on_calendar)
        specs.append(spec)

    changed_any = False
    defined_names = {s.name for s in specs}

    for s in specs:
        svc_path = SYSTEMD_DIR / f"{s.name}.service"
        tmr_path = SYSTEMD_DIR / f"{s.name}.timer"

        ctx = {
            "name": s.name,
            "description": s.description,
            "user": s.user, "group": s.group,
            "working_dir": s.working_dir,
            "environment_file": s.environment_file,
            "env": s.env,
            "exec_start": s.exec_start,
            "restart_sec": s.restart_sec,
            "start_limit": s.start_limit,
            "wants": s.wants, "after": s.after,
            "on_calendar": s.on_calendar,
        }

        svc_txt = render("unit.service.j2", ctx)
        tmr_txt = render("unit.timer.j2", ctx)

        if dry_run:
            print(f"[DRY] write {svc_path}\n{svc_txt}")
            print(f"[DRY] write {tmr_path}\n{tmr_txt}")
        else:
            ch1 = write_atomic(svc_path, svc_txt)
            ch2 = write_atomic(tmr_path, tmr_txt)
            if ch1 or ch2:
                changed_any = True
            if s.disabled:
                sh(["systemctl", "disable", "--now", f"{s.name}.timer"], check=False)
                sh(["systemctl", "stop", f"{s.name}.service"], check=False)
            else:
                sh(["systemctl", "enable", "--now", f"{s.name}.timer"], check=False)
                if s.start_immediately:
                    sh(["systemctl", "start", f"{s.name}.service"], check=False)

    if remove_orphans:
        existing = {p.stem for p in SYSTEMD_DIR.glob("*.timer")}
        to_remove = [n for n in existing if n.startswith(name_prefix) and n not in defined_names]
        for name in to_remove:
            if dry_run:
                print(f"[DRY] remove orphan {name}.timer/{name}.service")
            else:
                sh(["systemctl", "disable", "--now", f"{name}.timer"], check=False)
                sh(["systemctl", "stop", f"{name}.service"], check=False)
                for p in (SYSTEMD_DIR / f"{name}.timer", SYSTEMD_DIR / f"{name}.service"):
                    if p.exists():
                        p.unlink()
                changed_any = True

    if not dry_run and changed_any:
        sh(["systemctl", "daemon-reload"], check=False)
        if restart_changed:
            pass

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Sync systemd service/timer units from YAML.")
    ap.add_argument("config", help="Path to schedules.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="+", help="Sync only given unit names")
    ap.add_argument("--no-check-calendars", action="store_true")
    ap.add_argument("--remove-orphans", action="store_true")
    ap.add_argument("--no-restart-changed", action="store_true")
    ap.add_argument("--prefix", default="agora-")
    args = ap.parse_args()

    sync(
        config_path=args.config,
        dry_run=args.dry_run,
        only=args.only,
        remove_orphans=args.remove_orphans,
        check_calendars=not args.no_check_calendars,
        restart_changed=not args.no_restart_changed,
        name_prefix=args.prefix,
    )

if __name__ == "__main__":
    import argparse
    # dry-run 여부를 미리 파싱
    is_dry_run = "--dry-run" in sys.argv
    if not is_dry_run and os.geteuid() != 0:
        print("This tool must run as root (sudo).")
        sys.exit(1)
    main()
