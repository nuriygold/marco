---
name: stuck
description: Unstuck workflow — break through blockers, decision paralysis, or unclear next steps
user_invocable: true
args: situation
---

# stuck — Unstuck Workflow

When invoked, help break through a blocker. This is for when you know something is wrong but don't know where to start, or you're paralyzed on a decision, or you've been spinning on the same problem.

## Intake

If `{{situation}}` is empty, prompt:
```
Describe what you're stuck on:
1. What are you trying to do?
2. Where exactly are you blocked?
3. How long have you been stuck?
4. What have you already tried?
```

## Diagnose the Block Type

Classify the block into one of:

| Type | Description | Protocol |
|------|-------------|----------|
| **technical** | Code error, unexpected behavior, environment issue | → Use /debug |
| **clarity** | Don't know what to build or how to approach | → Decompose |
| **decision** | Two+ options, can't choose | → Decision matrix |
| **momentum** | Know what to do but can't start | → Micro-step |
| **context** | Lost track of where things are | → Orient |

---

## Protocol: Decompose (clarity block)

Break the vague problem into concrete pieces:

```
You're trying to: [restate clearly]

Smallest possible first step: [one sentence, very concrete]
What you need to know before you can do it: [list]
What you can defer: [list]
```

Then: "Start with [step 1]. Do nothing else yet."

---

## Protocol: Decision Matrix (decision block)

List the options with a score table:

```
Options: A vs B (vs C)

| Criterion | A | B | C |
|-----------|---|---|---|
| Reversible? | Yes/No | | |
| Time to implement | | | |
| Risk if wrong | Low/Med/High | | |
| Alignment with goal | | | |
| Cost | | | |

Recommendation: [Option X]
Reason: [1-2 sentences]
```

If the decision is irreversible and high-stakes, add:
```
Before deciding: sleep on it. Come back in 24h.
If you need to decide now: [Option X] because [reason].
```

---

## Protocol: Micro-step (momentum block)

```
You know what to do. You're not doing it.

The reason is usually one of:
1. The task feels too big → break it smaller
2. Fear of it being wrong → make it reversible
3. Unclear starting point → pick any file and open it

Your next action (takes < 5 minutes):
[very specific, time-boxed action]

Do that. Then come back.
```

---

## Protocol: Orient (context block)

Run a quick state check:
```
What branch are you on? → git branch --show-current
What changed recently? → git log --oneline -5
What's the current state? → python3 -m src.main status (or equivalent)
What was the last thing that worked? → git stash list / git log
```

Output a summary:
```
You are here: [branch / state]
Last known good: [commit or action]
Current delta: [what's changed]
Next clear action: [specific step]
```

---

## Always End With

One sentence. Exactly one next action. Concrete. Timed.

```
→ Do this now: [action] (takes ~X minutes)
```
