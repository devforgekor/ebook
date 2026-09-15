"""
core/copilot_rules | Copilot instruction sync helper: copy shared rule text into Copilot instructions file | sync_copilot_instructions()
"""

import os
import tempfile
from pathlib import Path

DEFAULT_RULE_SRC = Path("/home/opc/common-rule.md")
DEFAULT_COPILOT_INSTRUCTIONS = Path("/home/opc/.copilot/copilot-instructions.md")
DEFAULT_COPILOT_HEADER = (
    "# Copilot Instructions\n\n"
    "> 인프라/배포 관련 작업 시 `/home/opc/common-main.md`를 읽어라.\n\n"
    "---\n\n"
)


def _atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
        handle.write(text)
        temp_name = handle.name
    os.replace(temp_name, path)


def sync_copilot_instructions(
    rule_src: Path = DEFAULT_RULE_SRC,
    copilot_instructions: Path = DEFAULT_COPILOT_INSTRUCTIONS,
    header: str = DEFAULT_COPILOT_HEADER,
) -> None:
    """Sync the shared rule file into the Copilot instructions file."""
    rule_text = Path(rule_src).read_text(encoding="utf-8")
    _atomic_write_text(Path(copilot_instructions), header + rule_text)
