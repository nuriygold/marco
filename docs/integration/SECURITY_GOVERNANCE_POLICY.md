# Claw Code Security and Governance Policy

This policy defines minimum controls for adopting `claw` in developer workflows.

## 1) Permission Baseline

- Default mode: `read-only`.
- Escalate to `workspace-write` only for approved edit tasks in approved repos.
- Use `danger-full-access` only as break-glass, with explicit ticket approval and time limit.

Required controls:

- Every escalation must be tied to a tracked task or ticket.
- Break-glass sessions require post-run review notes.
- New repos must start in `read-only` until owner approval is recorded.

## 2) Allowed Tools Policy

Define and enforce environment profiles with `--allowedTools`.

Recommended profile: `dev-readonly`

- `read_file`
- `glob_search`
- `grep_search`
- `WebFetch`
- `WebSearch`
- `ToolSearch`
- `Skill`
- `Sleep`
- `SendUserMessage`
- `StructuredOutput`

Recommended profile: `dev-write`

- All `dev-readonly` tools
- `write_file`
- `edit_file`
- `TodoWrite`
- `NotebookEdit`
- `Config`

Recommended profile: `break-glass`

- All `dev-write` tools
- `bash`
- `PowerShell`
- `REPL`
- `Agent`

Policy requirements:

- `break-glass` profile cannot be the default.
- Profile changes must be reviewed by repo owner or security owner.
- Environment-specific profiles (local/dev/CI) must be version-controlled.

## 3) Plugin Policy

- Allowlist-only plugin sources (internal repository paths or approved vendor sources).
- Do not install plugins from unknown paths or unsigned artifacts.
- Every plugin must have an owner, version pin, and review record.
- Plugins with hook/lifecycle scripts must be reviewed like executable code.
- Disable and remove plugins that fail review or violate policy.

Minimum review checklist for plugins:

- Manifest fields validated (`name`, `version`, hooks/tools/commands scope).
- Script paths are local and expected.
- Required permissions are least-privilege.
- No hidden network or filesystem side effects outside approved scope.

## 4) Credential and Auth Policy

- API keys must come from approved secrets management, not hardcoded files.
- Never commit credentials to git.
- Use OAuth flows where policy requires centralized revocation and auditability.
- Require key rotation and deprovisioning for offboarded users.

## 5) Audit and Traceability

- Keep session exports for high-impact runs (`/export`).
- Record key operational decisions (permission escalations, plugin changes, break-glass use).
- Store rollout decisions and pilot outcomes with owner/date in `docs/integration/`.

## 6) Minimum Enforcement for Rollout

Before `GO`:

- Default permission mode configured to `read-only`.
- Tool profiles documented and applied.
- Plugin allowlist active.
- Credential handling approved by security.
