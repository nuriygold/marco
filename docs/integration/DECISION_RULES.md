# Claw Code Go/No-Go Decision Rules

Use these rules after pilot review and checklist completion.

## Decision Outcomes

### GO

Choose `GO` only when:

- All required checklist items are complete.
- Pilot metrics meet or exceed defined thresholds.
- No unresolved security or governance concern remains.

### PILOT-ONLY

Choose `PILOT-ONLY` when:

- Core controls are in place.
- Minor gaps remain with owners and due dates.
- Risks are accepted for limited continued trial only.

### NO-GO

Choose `NO-GO` when:

- Any unresolved security concern exists.
- Ownership/governance is unclear.
- Pilot regression risk exceeds tolerance.

## Required Sign-Off Record

| Field | Value |
| --- | --- |
| Decision Date |  |
| Decision Owner |  |
| Outcome (`GO`/`PILOT-ONLY`/`NO-GO`) |  |
| Open Risks |  |
| Required Follow-ups |  |

## Immediate Action Plans

If `GO`:

1. Lock default policy (`read-only` + allowlisted tools).
2. Extend pilot to staged rollout by repo tier.
3. Keep weekly review cadence for first month.

If `PILOT-ONLY`:

1. Keep rollout limited to approved pilot repos.
2. Close named gaps by due date.
3. Re-run decision gate with updated evidence.

If `NO-GO`:

1. Freeze expansion.
2. Create blocker tickets with owners and due dates.
3. Re-scope with tighter permissions/tool policy and re-pilot.
