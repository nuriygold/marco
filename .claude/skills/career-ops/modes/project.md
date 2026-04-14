# Mode: project

Evaluate a portfolio project idea against career goals and hiring signal.

## Input

User describes a project idea (name, concept, tech stack, estimated effort).

## Evaluation

1. **Hiring signal** — does building this demonstrate skills that target employers care about?
   Rate: High / Medium / Low

2. **Differentiation** — is this project common (todo app, blog) or distinctive?
   Rate: Distinctive / Average / Overdone

3. **Tech alignment** — does the stack match the candidate's target roles?
   Rate: Strong fit / Partial / Mismatch

4. **Scope realism** — can this be completed to a shippable, demo-able state in a reasonable time?
   Estimate: Weekend / 1–2 weeks / 1 month / 3+ months

5. **Portfolio fit** — does this fill a gap or duplicate existing portfolio pieces?

## Output format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT EVALUATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Project:     [name]
Stack:       [tech]
Effort est:  [timeframe]

Hiring signal:     [High/Medium/Low]
Differentiation:   [Distinctive/Average/Overdone]
Tech alignment:    [Strong/Partial/Mismatch]
Scope realism:     [Weekend / weeks / months]

VERDICT: BUILD IT / MODIFY SCOPE / SKIP

What to emphasize if built:
- [point 1]
- [point 2]

Suggested twists to make it more distinctive:
- [twist 1]
- [twist 2]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
