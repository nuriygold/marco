# Mode: ofertas

Compare and rank multiple job offers side by side.

## Input

The user provides 2–5 offers (text, URLs, or names of previously evaluated offers).
Fetch/evaluate any that haven't been scored yet using the `oferta` rubric.

## Steps

1. Score each offer using the full North Star rubric from `_shared.md`.
2. Build a comparison table.
3. Rank by weighted score.
4. Give a final recommendation.

## Output format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OFFER COMPARISON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                        [Co A]    [Co B]    [Co C]
Tech challenge           4         3         5
Autonomy & trust         5         4         3
Compensation             3         5         4
Team quality             4         3         4
Mission alignment        3         4         5
Work-life balance        4         4         3
────────────────────────────────────────────────────────
Weighted score          3.9       3.8       4.1
Grade                    B+        B+        A-
────────────────────────────────────────────────────────
RANK: #1 [Co C] · #2 [Co A] · #3 [Co B]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RECOMMENDATION
[2–3 paragraphs explaining the recommendation, trade-offs,
and what to negotiate for in each offer before deciding.]
```
