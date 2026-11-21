#!/bin/bash
# Build the venv that hosts the token-usage MCP server and print the ~/.claude.json
# entry for it. Never edits ~/.claude.json: paste the entry (or `claude mcp add`) yourself.
# Idempotent. Needs: uv.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
readonly VENV_DIR="${HOME}/.venvs/todoimpl-mcp"

main() {
    command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }
    uv venv --quiet --python 3.15 "${VENV_DIR}"
    uv pip install --quiet --python "${VENV_DIR}/bin/python" -e "${SCRIPT_DIR}"
    "${VENV_DIR}/bin/python" -c 'import mcp, todoimpl_mcp.server'
    echo "venv ready: ${VENV_DIR}"
    echo '"token-dashboard": {"type": "stdio", "command": "'"${VENV_DIR}"'/bin/python",'
    echo ' "args": ["-m", "todoimpl_mcp.server"], "env": {}}'
    # The peer server (DOCS-peer.md); scripts/deploy.sh registers it with `claude mcp add` itself.
    echo '"peer": {"type": "stdio", "command": "'"${VENV_DIR}"'/bin/python",'
    echo ' "args": ["-m", "todoimpl_mcp.peer_server"], "env": {}}'
}

main "$@"
