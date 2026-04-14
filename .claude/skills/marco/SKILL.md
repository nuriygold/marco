---
name: marco
description: Marco v3 operator -- run Marco CLI commands (doctor, status, inspect, plan, execute, validate, recover, patch, memory, scaffold, and more)
user_invocable: true
args: command
---

# Marco v3 Operator Skill

Run `python3 -m src.main {{command}}` from the repo root and interpret the output.

## Command surface

### Foundation
| Command | Usage | Purpose |
|---------|-------|---------|
| `doctor` | `marco doctor` | Environment + config health check |
| `status` | `marco status` | Workspace status (files, patches, sessions) |
| `summary` | `marco summary` | Human-readable workspace summary |
| `manifest` | `marco manifest` | Full repo manifest as JSON |
| `inspect` | `marco inspect [--query X]` | Repo intelligence maps |

### Autonomy
| Command | Usage | Purpose |
|---------|-------|---------|
| `plan` | `marco plan "goal"` | Create an autonomous session plan |
| `execute` | `marco execute <session_id>` | Mark session as executing |
| `validate` | `marco validate <session_id>` | Run validation loop |
| `recover` | `marco recover <session_id>` | Run recovery loop |
| `sessions` | `marco sessions` | List all session artifacts |
| `resume` | `marco resume <session_id>` | Resume a stored session |

### Toolbox
| Command | Usage | Purpose |
|---------|-------|---------|
| `find` | `marco find "**/*.py"` | Glob files |
| `lookup` | `marco lookup "keyword"` | Search file contents |
| `routes` | `marco routes` | Discover route candidates |
| `env` | `marco env` | Discover env var references |
| `scripts` | `marco scripts` | Discover runnable scripts |
| `run-script` | `marco run-script <name> [--execute] [--yes]` | Run a script (dry-run by default) |
| `script-info` | `marco script-info <name>` | Show script metadata |
| `tree` | `marco tree [--depth N]` | Workspace tree (default depth 3) |

### Memory
| Command | Usage | Purpose |
|---------|-------|---------|
| `note` / `remember` | `marco note <key> <topic> "text"` | Save a technical note |
| `notes` | `marco notes` | List all notes |
| `recall` | `marco recall "query"` | Fuzzy recall across notes/decisions/conventions |
| `decision` | `marco decision <key> <topic> "text"` | Store a technical decision |
| `decisions` | `marco decisions` | List decisions |
| `convention` | `marco convention <key> <topic> "text"` | Store a coding convention |
| `conventions` | `marco conventions` | List conventions |

### Patches (mutating — confirm before applying)
| Command | Usage | Purpose |
|---------|-------|---------|
| `propose-patch` | `marco propose-patch --name X --target file --find "old" --replace "new"` | Stage a patch (safe, no write) |
| `show-patch` | `marco show-patch <id>` | Show patch diff |
| `apply-patch` | `marco apply-patch <id> [--yes]` | Apply patch with checkpoint |
| `rollback-patch` | `marco rollback-patch <id>` | Rollback from checkpoint |
| `list-patches` | `marco list-patches` | List all patch sessions |

### Scaffold
| Command | Usage | Purpose |
|---------|-------|---------|
| `scaffold` | `marco scaffold page|component|route|service <name>` | Scaffold code structure |

### REPL
| Command | Usage | Purpose |
|---------|-------|---------|
| `repl` | `marco repl` | Interactive slash-command shell |
| `repl --once` | `marco repl --once "/status"` | Run one command and exit |

---

## Execution steps

1. Parse `{{command}}` — identify the subcommand and its arguments.
2. Run: `python3 -m src.main {{command}}`
3. Parse the JSON or text output and present it clearly.
4. If the command fails, read the error, check usage in the table above, and suggest a fix.

## Safety rules

- `apply-patch` and `run-script --execute` are **mutating** — always confirm with the user first.
- `propose-patch` and `show-patch` are read-only — safe to run freely.
- `plan` creates a session artifact but does not execute anything.
- All other commands are read-only.
