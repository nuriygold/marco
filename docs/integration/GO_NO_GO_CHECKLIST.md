# Claw Code Integration Go/No-Go Checklist

Use this checklist as the source of truth for rollout decisions.

How to use:
1. Assign an owner and due date for each item.
2. Add evidence links or command output snippets.
3. Mark each item complete only when evidence exists.

## 1) Scope and Fit (Required)

| Item | Owner | Due | Evidence | Complete |
| --- | --- | --- | --- | --- |
| We have 2-3 concrete workflows to improve (repo analysis, safe code edits, PR drafting). |  |  |  | [ ] |
| Target users are identified (who uses `claw`, and in which repos). |  |  |  | [ ] |
| We explicitly want a CLI-based AI harness (not API-only backend automation). |  |  |  | [ ] |
| We accept Rust CLI runtime as the primary product surface. |  |  |  | [ ] |

## 2) Security and Governance (Required)

| Item | Owner | Due | Evidence | Complete |
| --- | --- | --- | --- | --- |
| Default permission mode is defined (`read-only` first). |  |  |  | [ ] |
| Rules for moving to `workspace-write` and `danger-full-access` are documented. |  |  |  | [ ] |
| API keys and auth storage are approved by internal security policy. |  |  |  | [ ] |
| Allowed tool policy is defined (`--allowedTools` profile per environment). |  |  |  | [ ] |
| Plugin policy is defined (allowlist only, signed/owned sources, review process). |  |  |  | [ ] |

## 3) Technical Integration Readiness (Required)

| Item | Owner | Due | Evidence | Complete |
| --- | --- | --- | --- | --- |
| Developer machines and CI have Rust toolchain + build/install path validated. |  |  |  | [ ] |
| Provider strategy is selected (Anthropic/xAI/OpenAI-compatible). |  |  |  | [ ] |
| Session handling and export/log expectations are defined. |  |  |  | [ ] |
| Git workflow mapping is approved (`/branch`, `/commit`, `/pr`, `/issue`). |  |  |  | [ ] |
| Custom skills/plugins locations are confirmed (`.codex/.claw/$CODEX_HOME`). |  |  |  | [ ] |

## 4) Pilot Plan (Required Before Full Rollout)

| Item | Owner | Due | Evidence | Complete |
| --- | --- | --- | --- | --- |
| Pilot duration is set (recommended: 1 week). |  |  |  | [ ] |
| Pilot repos are non-production or low-risk. |  |  |  | [ ] |
| Success metrics are defined (time saved, completion rate, error rate, developer satisfaction). |  |  |  | [ ] |
| Rollback path is documented (disable plugins, revert permissions, stop usage). |  |  |  | [ ] |

## 5) Decision Gate

- `GO`: all required items complete, pilot metrics meet target, no unresolved security concerns.
- `PILOT-ONLY`: minor gaps remain but controls are in place and risks are accepted.
- `NO-GO`: unresolved security concern, unclear ownership/governance, or pilot risk is above tolerance.

Decision:

- Date:
- Outcome (`GO`, `PILOT-ONLY`, `NO-GO`):
- Decision owner:
- Notes:

## 6) Immediate Next Actions (If GO)

1. Lock default policy (`read-only` + allowlisted tools).
2. Run pilot with 2-5 developers.
3. Review incidents and metrics at end of week.
4. Approve staged rollout by repo tier.

## 7) Immediate Next Actions (If NO-GO)

1. Document blockers with owners and due dates.
2. Re-run a narrowed pilot with tighter permissions.
3. Re-evaluate with this checklist after fixes.
