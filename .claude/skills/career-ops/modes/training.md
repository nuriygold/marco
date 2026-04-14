# Mode: training

Evaluate a course, certification, or training program against the candidate's North Star.

## Input

User provides: course name, provider, cost, time commitment, and optionally a URL.

## Evaluation

Answer these questions:

1. **Relevance to target roles** — does this skill appear in JDs for the candidate's target titles?
   Rate: High / Medium / Low / Irrelevant

2. **Market signal** — is this cert recognized by hiring managers in the target industry?
   Rate: Strong signal / Moderate / Weak / Unknown

3. **Time ROI** — hours to complete vs. expected career benefit
   - < 10h: quick win
   - 10–40h: short investment
   - 40–100h: significant investment
   - > 100h: major commitment

4. **Cost ROI** — cost vs. expected salary impact or job unlock
   Rate: Worth it / Borderline / Overpriced for the outcome

5. **Alternatives** — is there a faster/cheaper path to the same signal?

## Output format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRAINING EVALUATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Course:      [name]
Provider:    [provider]
Cost:        [cost]
Time:        [hours/weeks]

Relevance:   [High/Medium/Low]
Market signal: [Strong/Moderate/Weak]
Time ROI:    [assessment]
Cost ROI:    [Worth it / Borderline / Overpriced]

VERDICT: DO IT / DEFER / SKIP

Reason: [2–3 sentences]

Better alternative: [if one exists]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
