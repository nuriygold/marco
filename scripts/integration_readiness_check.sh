#!/usr/bin/env bash
set -euo pipefail

DEEP_CHECKS=0
OUT_FILE="${OUT_FILE:-.claw/integration/readiness-report.md}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deep)
      DEEP_CHECKS=1
      shift
      ;;
    --out)
      OUT_FILE="${2:?missing value for --out}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--deep] [--out <path>]" >&2
      exit 1
      ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
mkdir -p "$(dirname "$OUT_FILE")"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

check_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "yes"
  else
    echo "no"
  fi
}

tool_version_or_missing() {
  local cmd="$1"
  local version_arg="${2:---version}"
  if command -v "$cmd" >/dev/null 2>&1; then
    "$cmd" "$version_arg" 2>/dev/null | head -n 1
  else
    echo "missing"
  fi
}

env_present() {
  local key="$1"
  if [[ -n "${!key:-}" ]]; then
    echo "set"
  else
    echo "unset"
  fi
}

{
  echo "# Integration Readiness Report"
  echo
  echo "- Generated: $(timestamp)"
  echo "- Repository: \`$ROOT\`"
  echo "- Deep checks: \`$DEEP_CHECKS\`"
  echo
  echo "## Toolchain"
  echo
  echo "| Check | Result | Details |"
  echo "| --- | --- | --- |"
  echo "| cargo installed | $(check_cmd cargo) | $(tool_version_or_missing cargo) |"
  echo "| rustc installed | $(check_cmd rustc) | $(tool_version_or_missing rustc) |"
  echo "| claw installed | $(check_cmd claw) | $(tool_version_or_missing claw) |"
  echo "| python3 installed | $(check_cmd python3) | $(tool_version_or_missing python3 --version) |"
  echo
  echo "## Auth Environment Presence"
  echo
  echo "| Variable | Presence |"
  echo "| --- | --- |"
  echo "| ANTHROPIC_API_KEY | $(env_present ANTHROPIC_API_KEY) |"
  echo "| ANTHROPIC_BASE_URL | $(env_present ANTHROPIC_BASE_URL) |"
  echo "| XAI_API_KEY | $(env_present XAI_API_KEY) |"
  echo "| XAI_BASE_URL | $(env_present XAI_BASE_URL) |"
  echo "| OPENAI_API_KEY | $(env_present OPENAI_API_KEY) |"
  echo
  echo "## Skills and Agents Paths"
  echo
  echo "| Path | Exists |"
  echo "| --- | --- |"
  for path in \
    ".codex/skills" \
    ".claw/skills" \
    ".codex/agents" \
    ".claw/agents" \
    "${CODEX_HOME:-\$CODEX_HOME}/skills" \
    "${CODEX_HOME:-\$CODEX_HOME}/agents"
  do
    if [[ "$path" == "\$CODEX_HOME/skills" || "$path" == "\$CODEX_HOME/agents" ]]; then
      echo "| \`$path\` | unresolved (CODEX_HOME unset) |"
      continue
    fi
    if [[ -d "$ROOT/$path" || -d "$path" ]]; then
      echo "| \`$path\` | yes |"
    else
      echo "| \`$path\` | no |"
    fi
  done
  echo
  echo "## Git State"
  echo
  echo "\`\`\`text"
  git -C "$ROOT" status --short --branch || true
  echo "\`\`\`"
  echo
  if [[ "$DEEP_CHECKS" -eq 1 ]]; then
    echo "## Deep Checks"
    echo
    echo "### cargo check --workspace"
    echo
    echo "\`\`\`text"
    if [[ -f "$ROOT/rust/Cargo.toml" && "$(check_cmd cargo)" == "yes" ]]; then
      (cd "$ROOT/rust" && cargo check --workspace) || true
    else
      echo "Skipped: rust/Cargo.toml or cargo missing."
    fi
    echo "\`\`\`"
    echo
  fi
} >"$OUT_FILE"

echo "Wrote readiness report: $OUT_FILE"
