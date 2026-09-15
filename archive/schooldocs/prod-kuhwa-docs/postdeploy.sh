#!/usr/bin/env bash

set -euo pipefail

# Compatibility wrapper for the unified test/prod post-deploy script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/prod-postdeploy.sh" "$@"
