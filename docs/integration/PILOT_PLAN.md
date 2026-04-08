# Claw Code Pilot Plan (1 Week)

This pilot template is required before full rollout.

## 1) Pilot Setup

- Duration: 1 week
- Participants: 2-5 developers
- Repositories: low-risk/non-production only
- Default permissions: `read-only` at start
- Escalation policy: use `workspace-write` only for approved edit tasks

## 2) Target Workflows

Select 2-3 workflows:

- Repository analysis and architecture summarization
- Safe code edits with review
- PR/issue drafting and git workflow acceleration

## 3) Success Metrics

Track these metrics per participant:

- Time saved per task (minutes)
- Completion rate without manual rework
- Error/regression rate introduced
- Developer satisfaction (1-5)

Target thresholds (example defaults):

- Median time saved: >= 20%
- Completion without rework: >= 80%
- Regression rate: <= baseline manual workflow
- Satisfaction: >= 4.0/5

## 4) Data Collection Template

| Date | Developer | Repo | Workflow | Permission Mode | Outcome | Time Saved | Rework Needed | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

## 5) Incident and Risk Log

| Date | Severity | Description | Trigger | Mitigation | Owner | Closed |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  | [ ] |

## 6) Rollback Playbook

If pilot risk exceeds tolerance:

1. Disable non-essential plugins.
2. Revert default mode to `read-only` only.
3. Restrict tool profile to `dev-readonly`.
4. Pause pilot and document blocker tickets with owners.

## 7) End-of-Week Review

Required outputs:

- Metric summary against thresholds
- Incident summary and corrective actions
- Recommendation: `GO`, `PILOT-ONLY`, or `NO-GO`
- Signed decision owner and date
