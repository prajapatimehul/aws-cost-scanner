#!/usr/bin/env bash
set -euo pipefail

# Augment PATH with common uvx/uv installation locations
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

if ! command -v uvx &> /dev/null; then
    echo "Error: uvx not found. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

exec uvx awslabs.aws-api-mcp-server@latest
