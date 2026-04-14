# Mode: oferta

Evaluate a single job offer or JD. No auto-PDF, no tracker log.

## Input

The user has provided a JD (text or URL). Fetch if URL.

## Evaluation rubric

Use the North Star from `_shared.md` to score each dimension 1–5.

Extract from JD:
- Company name and size (if findable)
- Role title and seniority
- Location / remote policy
- Tech stack mentioned
- Compensation (if disclosed)
- Team or product context

Score each North Star dimension. Show your reasoning per dimension.

## Output format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OFFER EVALUATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Company:     [name]
Role:        [title]
Location:    [location / remote]
Stack:       [key tech]
Comp:        [salary if known, else "not disclosed"]

SCORING
  Technical challenge   [1–5] — [reason]
  Autonomy & trust      [1–5] — [reason]
  Compensation          [1–5] — [reason]
  Team quality          [1–5] — [reason]
  Mission alignment     [1–5] — [reason]
  Work-life balance     [1–5] — [reason]

Weighted score: [X.X / 5.0]
Grade: [A/B/C/D/F]

VERDICT: APPLY / BORDERLINE / SKIP

PROS
  1. [pro]
  2. [pro]
  3. [pro]

CONS
  1. [con]
  2. [con]
  3. [con]

QUESTIONS TO ASK IN INTERVIEW
  - [question 1]
  - [question 2]
  - [question 3]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
