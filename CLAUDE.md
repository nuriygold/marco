# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this repo is

Marco is a Python-first CLI operator companion (`src/`) with a Rust secondary track (`rust/`).
The Python CLI is the primary surface. All v3 operator commands live in `src/marco_v3/`.

## Running things

```bash
# Python CLI
python3 -m src.main <command>

# Python tests
python3 -m unittest discover -s tests -v

# Rust (from rust/)
cargo fmt --all
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Use `/marco <command>` as a shorthand skill for the Python CLI.
Use `/rust-check` to run the full Rust verification suite.
Use `/test` to run both Python and Rust tests.

## Key paths

| Path | Contents |
|------|----------|
| `src/marco_v3/cli.py` | All v3 command handlers (doctor, plan, execute, etc.) |
| `src/marco_v3/autonomy.py` | Session plan/execute/validate/recover logic |
| `src/marco_v3/memory.py` | Notes, decisions, conventions |
| `src/marco_v3/patches.py` | Patch propose/apply/rollback |
| `src/marco_v3/repo_intel.py` | File scan, routes, env discovery |
| `src/marco_v3/scaffold.py` | Page/component/route/service scaffolding |
| `src/main.py` | CLI entry point — registers all parsers |
| `tests/` | Python unittest surface |
| `rust/` | Rust workspace |
| `.claude/skills/` | Claude Code skills (marco, rust-check, test, commit, career-ops) |
| `data/pipeline.md` | career-ops URL inbox |
| `data/tracker.md` | career-ops application tracker |

## Commit conventions

Use conventional commits: `<type>(<scope>): <summary>`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `skill`
Scopes: `v3`, `skills`, `career-ops`, `marco`, `rust`, `tests`, `cli`, `memory`, `patches`, `scaffold`, `repl`, `data`

Use `/commit` skill for structured commits.

## Safety rules

- `apply-patch` and `run-script --execute` are mutating — confirm with user before running.
- When editing `src/marco_v3/`, update `tests/` alongside if behavior changes.
- Do not overwrite `CLAUDE.md` or `CLAW.md` automatically.
- Keep `src/` and `rust/` consistent when shared behavior changes.

## Skills available

| Skill | Trigger |
|-------|---------|
| `/marco <cmd>` | Run any Marco v3 CLI command |
| `/rust-check` | Run cargo fmt + clippy + test |
| `/test` | Run Python + Rust test suites |
| `/commit` | Create a structured conventional commit |
| `/career-ops` | Job search command center |
