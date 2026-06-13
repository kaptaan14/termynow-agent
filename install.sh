#!/usr/bin/env bash
# Termynow agent one-line installer. Intended to be hosted at https://termynow.com/install.sh
set -euo pipefail

TERMYNOW_API_BASE="${TERMYNOW_API_BASE:-https://api.termynow.com}"
TERMYNOW_DASHBOARD_URL="${TERMYNOW_DASHBOARD_URL:-https://termynow.com}"
TERMYNOW_AGENT_REPO="${TERMYNOW_AGENT_REPO:-git+https://github.com/kaptaan14/termynow-agent.git}"
export TERMYNOW_API_BASE TERMYNOW_DASHBOARD_URL

# Resolve local agent source when running from a checkout (not curl | bash).
AGENT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && "${BASH_SOURCE[0]}" != "bash" && "${BASH_SOURCE[0]}" != "-" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    AGENT_DIR="${SCRIPT_DIR}"
  elif [[ -f "${SCRIPT_DIR}/../agent/pyproject.toml" ]]; then
    AGENT_DIR="$(cd "${SCRIPT_DIR}/../agent" && pwd)"
  fi
fi

have_cmd() { command -v "$1" >/dev/null 2>&1; }

if ! have_cmd python3; then
  echo "python3 is required but not found in PATH." >&2
  exit 1
fi

if ! python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
  echo "Python 3.11+ is required (found $(python3 -V))." >&2
  exit 1
fi

if [[ -z "${AGENT_DIR}" ]] && ! have_cmd git; then
  echo "git is required to install termynow-agent." >&2
  exit 1
fi

STACK="${HOME}/.local/share/termynow"
VENV="${STACK}/venv"
BIN="${HOME}/.local/bin"
mkdir -p "${STACK}" "${BIN}"

echo "Installing Termynow..."
if [[ ! -x "${VENV}/bin/python" ]]; then
  python3 -m venv "${VENV}"
fi
"${VENV}/bin/pip" install -q -U pip wheel setuptools

if [[ -n "${AGENT_DIR}" ]]; then
  "${VENV}/bin/pip" install -q "${AGENT_DIR}"
else
  "${VENV}/bin/pip" install -q "${TERMYNOW_AGENT_REPO}"
fi

ln -sf "${VENV}/bin/termynow-agent" "${BIN}/termynow-agent"
export PATH="${BIN}:${PATH}"

if ! have_cmd termynow-agent; then
  echo "termynow-agent is not on PATH. Add ${BIN} to PATH, then re-run this script." >&2
  exit 1
fi

termynow-agent --api-base "${TERMYNOW_API_BASE}" setup

echo ""
echo "Installing background service..."
termynow-agent install-service

echo ""
echo "Done. The agent is running in the background and will reconnect automatically."
