# Claw Code Technical Readiness

Use this page to validate machine and CI readiness for integration.

## 1) Local Machine Validation

Run:

```bash
./scripts/integration_readiness_check.sh
```

Optional deep checks:

```bash
./scripts/integration_readiness_check.sh --deep
```

Expected baseline:

- `cargo` and `rustc` are installed.
- `claw --version` returns expected build info.
- Repository is a valid git worktree.
- Provider env strategy is selected and documented.

## 2) CI Validation

Required CI checks:

```bash
cd rust
cargo check --workspace
cargo test --workspace
cargo build --release -p claw-cli
```

Recommended additional CI checks:

```bash
cd rust
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

## 3) Provider Strategy

Pick and document one primary provider path:

- Anthropic-compatible (`ANTHROPIC_API_KEY` + optional `ANTHROPIC_BASE_URL`)
- xAI (`XAI_API_KEY` + optional `XAI_BASE_URL`)
- OpenAI-compatible provider path where applicable

Document:

- Primary provider
- Fallback provider
- Model defaults
- Secret source and rotation process

## 4) Session and Logging Expectations

Define:

- When to use `/export` for run traceability.
- Where session exports are stored.
- Retention period for exported session artifacts.

## 5) Git Workflow Mapping

Validate usage and guardrails for:

- `/branch`
- `/worktree`
- `/commit`
- `/commit-push-pr`
- `/pr`
- `/issue`

Document branch naming convention and required PR checks.

## 6) Skills and Plugins Location Contract

Confirm where team-managed assets live:

- Project: `.codex/skills`, `.claw/skills`, `.codex/agents`, `.claw/agents`
- User/global: `$CODEX_HOME/skills`, `$CODEX_HOME/agents`

Confirm plugin roots and registry expectations from runtime config.
