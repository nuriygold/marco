# Marco

Marco is an AI operator companion with a clear identity: practical, loyal, and built for real work.

He is not a clone, not a rebrand, and not "Claw" or "Claude." He is **Marco**.

## Who Marco is

Marco is designed with a strong operator personality:

- **Calm under pressure** — keeps sessions structured when tasks get messy.
- **Direct and honest** — reports what worked, what failed, and what is still unknown.
- **Execution-first** — does not just plan; he routes, runs, verifies, and iterates.
- **Loyal to mission** — Marco serves **Rudolph** as a dependable technical partner.

## Stack

**Python-first, Rust-secondary.**

- All v3 operator logic lives in `src/marco_v3/` (Python).
- The `rust/` workspace is an active systems track.
- The web console is served by `src/marco_v3/server.py` (FastAPI + Uvicorn).

## Live Instance

**[marco.nuriy.com](https://marco.nuriy.com)** — deployed on a DigitalOcean Droplet behind Caddy. See `deploy/` for setup docs.

## Web Console

Marco ships a browser-based operator console at `/console`. Key features:

- **AI chat with live tool-call streaming** — tool invocations appear in real time as Marco works, not after.
- **Smart reasoning mode** — Marco defaults to the reasoning model (`grok-4-1-fast-reasoning`) for precision. For simple lookups he offers an inline fast-mode prompt before spending any tokens:
  > *Simple lookup — take my thinking cap off? **[Yes, go fast]** **[No, keep thinking]***
- **Mobile-ready** — responsive layout with a hamburger nav, `dvh`-based console height that survives iOS Safari's address bar.
- **Multi-workspace** — register and switch between workspaces from the sidebar.

## LLM Providers

Marco is provider-agnostic. Configure via environment variables in `/etc/marco/marco.env`:

| Provider | Env vars required |
|----------|------------------|
| `grok` (xAI) | `XAI_API_KEY` |
| `azure-openai` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` |
| `azure-foundry` | `AZURE_FOUNDRY_API_KEY`, `AZURE_FOUNDRY_ENDPOINT`, `AZURE_FOUNDRY_MODEL` |

```bash
MARCO_LLM_PROVIDER=grok          # grok | azure-openai | azure-foundry
XAI_API_KEY=...
XAI_MODEL=grok-4-1-fast-reasoning   # default; override to grok-4-1-fast-non-reasoning for speed
```

## v3 Command Surface

```bash
# Foundation
marco doctor / status / summary / manifest / inspect

# Autonomy
marco plan / execute / validate / recover / sessions / resume

# Toolbox
marco find / lookup / routes / env / scripts / run-script / tree

# Memory
marco note / notes / remember / recall / decision / convention

# Patching
marco propose-patch / show-patch / apply-patch / rollback-patch / list-patches

# Scaffold
marco scaffold page|component|route|service

# REPL
marco repl
```

## Running Marco

```bash
# CLI
python3 -m src.main <command>

# Web console (dev)
python3 -m src.main serve

# Alias shorthand
alias marco='python3 -m src.main'
```

## Tests

```bash
# Python
python3 -m unittest discover -s tests -v

# Rust
cd rust && cargo fmt --all && cargo clippy --workspace --all-targets -- -D warnings && cargo test --workspace
```

## Repository Layout

```text
.
├── src/
│   └── marco_v3/         # v3 operator core (CLI, server, LLM, chat, patches, memory)
│       ├── templates/    # Jinja2 HTML templates
│       └── static/       # app.js, app.css
├── tests/                # Python unittest surface
├── rust/                 # Rust workspace
├── deploy/               # Caddy + systemd deployment configs
└── .claude/skills/       # Claude Code skills (marco, commit, test, career-ops, etc.)
```

## Identity

- Call him **Marco**.
- Preserve his operator personality.
- His role is explicit: **Marco serves Rudolph**.

---

Marco is a working partner, not just a demo.
