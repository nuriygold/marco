---
name: commit
description: Create a structured git commit following Marco repo conventions
user_invocable: true
args: message
---

# Commit Skill

Create a conventional commit for the Marco repo.

## Steps

### 1. Assess what's staged

Run `git status` and `git diff --staged`.

If nothing is staged, run `git diff` to see unstaged changes, then ask the user which files to stage before proceeding.

### 2. Draft the commit message

Use conventional commit format:
```
<type>(<scope>): <summary under 72 chars>

[optional body — explain WHY, not WHAT]
```

**Types:**
| Type | When to use |
|------|------------|
| `feat` | New feature or command |
| `fix` | Bug fix |
| `refactor` | Code change with no behavior change |
| `test` | Adding or fixing tests |
| `docs` | Documentation only |
| `chore` | Build, config, dependency changes |
| `skill` | Adding or modifying a `.claude/skills/` file |

**Scopes for this repo:**
`v3`, `skills`, `career-ops`, `marco`, `rust`, `tests`, `cli`, `memory`, `patches`, `scaffold`, `repl`, `data`

If `{{message}}` was provided, use it as the summary line (still apply type/scope).

### 3. Confirm before committing

Show the proposed commit message and the list of staged files.
Ask the user to confirm (or adjust the message) before running `git commit`.

### 4. Commit

```bash
git commit -m "<type>(<scope>): <summary>"
```

Report the commit hash and summary on success.

## Rules

- Never use `git add -A` or `git add .` — stage specific files only.
- Never use `--no-verify`.
- Never amend an existing commit — always create a new one.
- If the pre-commit hook fails, fix the underlying issue before retrying.
