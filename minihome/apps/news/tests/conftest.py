#!/usr/bin/env python3
"""Shared test fixtures and configuration."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Add scripts directory for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
