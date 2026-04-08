# Claw Code Operator Guide

This guide is for operators who want to run the project safely and consistently.

## What this repo is

- `rust/` is the primary product surface.
- `src/` and `tests/` are a Python parity and porting workspace.

Use the Rust CLI (`claw`) for real agent workflows. Use Python commands for parity/reporting workflows.

## Prerequisites

- macOS or Linux
- Rust stable toolchain + Cargo
- API credentials for your model provider

Example provider env vars:

```bash
export ANTHROPIC_API_KEY="..."
# optional
export ANTHROPIC_BASE_URL="https://api.anthropic.com"

export XAI_API_KEY="..."
# optional
export XAI_BASE_URL="https://api.x.ai"
```

## Build and install

From repo root:

```bash
cd rust
cargo install --path crates/claw-cli --locked
```

Or build without installing globally:

```bash
cd rust
cargo build --release -p claw-cli
./target/release/claw --help
```

## First-run workflow

```bash
claw
```

In the REPL:

1. `/init`
2. `/status`
3. ask a real task

Useful slash commands:

- `/help`
- `/model <name>`
- `/permissions <read-only|workspace-write|danger-full-access>`
- `/plugin list`
- `/session list`
- `/diff`
- `/export [file]`

## Non-interactive usage

```bash
claw "summarize this repository"
claw prompt "explain rust/crates/runtime"
claw --output-format json prompt "review the latest changes"
```

## Plugin operations

- List plugins: `/plugin list`
- Install plugin from path: `/plugin install <path>`
- Enable/disable: `/plugin enable <name>` or `/plugin disable <name>`
- Update/uninstall: `/plugin update <id>` and `/plugin uninstall <id>`

### Hook and lifecycle behavior

- Plugin hooks are merged into runtime hook execution.
- Plugin lifecycle `Init` runs when runtime state is created.
- Plugin lifecycle `Shutdown` runs when runtime state is dropped.

## Health checks

### Python workspace checks

```bash
python3 -m src.main --help
python3 -m src.main summary
python3 -m unittest discover -s tests -v
```

### Rust workspace checks

```bash
cd rust
cargo check --workspace
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all -- --check
```

## CI status baseline

Current CI workflow verifies:

- `cargo check --workspace`
- `cargo test --workspace`
- `cargo build --release`

on `ubuntu-latest` and `macos-latest`.

## Integration and rollout gating

Use the integration packet when evaluating whether to include Claw Code in another product or team workflow:

- `docs/integration/GO_NO_GO_CHECKLIST.md`
- `docs/integration/SECURITY_GOVERNANCE_POLICY.md`
- `docs/integration/TECHNICAL_READINESS.md`
- `docs/integration/PILOT_PLAN.md`
- `docs/integration/DECISION_RULES.md`

Generate technical readiness evidence:

```bash
./scripts/integration_readiness_check.sh
./scripts/integration_readiness_check.sh --deep
```

## Troubleshooting

- `cargo: command not found`: install Rust via `rustup`.
- OAuth issues: run `claw login` and retry.
- Provider auth errors: verify provider key env vars are present in current shell.
- Plugin not found: check plugin path, manifest path (`plugin.json` or `.claw-plugin/plugin.json`), and `/plugin list` output.

## Safe operation tips

- Start with `read-only` for new repos.
- Move to `workspace-write` only when editing is needed.
- Use `danger-full-access` only when explicitly required.
- Keep plugin directories version-controlled where possible.
