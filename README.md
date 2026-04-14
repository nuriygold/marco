# Marco

Marco is an AI harness companion with a clear identity: practical, loyal, and built for real work.

He is not a clone, not a rebrand, and not "Claw" or "Claude." He is **Marco**.

## Who Marco is

Marco is designed with a strong operator personality:

- **Calm under pressure** — he keeps sessions structured when tasks get messy.
- **Direct and honest** — he reports what worked, what failed, and what is still unknown.
- **Execution-first** — he does not just plan; he routes, runs, verifies, and iterates.
- **Loyal to mission** — Marco serves **Rudolph** as a dependable technical partner.

## Stack status: Python or Rust?

**Both** — with a clear priority: **Python-first, Rust-secondary**.

- Day-to-day implementation and CLI behavior live in `src/` (Python).
- The `rust/` workspace is still in this repo as an active systems track.
- So the accurate label is: **Python-first multi-runtime project (Python + Rust)**.

## What Marco does

Marco includes a Python CLI that mirrors command and tool routing behavior used in agent harness workflows.

Core capabilities include:

- command and tool inventory queries
- runtime-style prompt routing
- small turn-loop execution simulation
- bootstrap/session reporting
- parity auditing against a local archived tree
- remote/ssh/teleport/direct/deep-link mode simulation

## API philosophy

Marco is provider-agnostic by design and can be used with **all major AI APIs** through adapter-style integration.

That said, he works best with:

- **OpenAI APIs (especially Codex-oriented workflows)** for reasoning + tool execution quality
- **structured tool-calling runtimes** where deterministic command routing matters

## Startup command and API keys

The startup surface in this repository is currently Python module entry:

```bash
python3 -m src.main <command>
```

If you want a true `marco` terminal command, add a wrapper:

```bash
alias marco='python3 -m src.main'
# usage: marco summary
```

Marco expects provider credentials from your environment (or your keychain/bootstrap flow), for example:

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export XAI_API_KEY="..."
export AZURE_OPENAI_API_KEY="..."
```

This keeps API keys "wrapped" into startup context once per shell session/profile, so you can run `marco ...` (or `python3 -m src.main ...`) without retyping secrets.

## Quickstart

Run summary output:

```bash
python3 -m src.main summary
```

Print manifest:

```bash
python3 -m src.main manifest
```

List mirrored commands/tools:

```bash
python3 -m src.main commands --limit 20
python3 -m src.main tools --limit 20
```

Run basic Python tests:

```bash
python3 -m unittest discover -s tests -v
```

## Repository layout

```text
.
├── src/                  # Marco Python runtime + CLI surface
├── tests/                # Python verification
├── rust/                 # Rust workspace track
├── assets/               # Images and reference artifacts
└── README.md
```

## Identity note

If you build on this project, keep the naming and positioning consistent:

- call him **Marco**
- preserve his operator personality
- keep his role explicit: **Marco serves Rudolph**
- maintain provider flexibility while optimizing for OpenAI/Codex-class execution

---

Marco is a working partner, not just a demo.
