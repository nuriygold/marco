---
name: debug
description: Systematic debug workflow — diagnose errors, trace root cause, propose fix with verification steps
user_invocable: true
args: context
---

# debug — Systematic Debug Workflow

When invoked, run a structured root-cause analysis on the error or problem described in `{{context}}`.

## Protocol

### Step 1 — Capture the Error

If `{{context}}` is empty, ask:
```
What's the error? Paste:
1. The exact error message / stack trace
2. The file and line number (if shown)
3. What you expected vs. what happened
4. Any recent changes that might be related
```

If context is provided, extract:
- Error type / message
- File path + line number
- Call stack (if available)
- Triggering conditions

### Step 2 — Hypothesize (3 candidates)

Generate exactly 3 root-cause hypotheses, ordered by likelihood:

```
Hypothesis 1 (most likely): [concise cause]
  Evidence: [what points to this]
  Test: [how to confirm]

Hypothesis 2: [concise cause]
  Evidence: [what points to this]
  Test: [how to confirm]

Hypothesis 3 (least likely): [concise cause]
  Evidence: [what points to this]
  Test: [how to confirm]
```

### Step 3 — Investigate

For each hypothesis (starting with #1):
1. Read the relevant file(s) at the line(s) indicated
2. Check recent git changes: `git log --oneline -10 -- {file}`
3. Look for related test files
4. Check for environmental causes (env vars, config, dependencies)

Do NOT fix yet — understand first.

### Step 4 — Diagnose

State the confirmed root cause:
```
ROOT CAUSE: [one sentence, precise]
Location: {file}:{line}
Why it breaks: [mechanism]
Why it worked before (if regression): [what changed]
```

### Step 5 — Fix

Propose the minimal fix:
- Show exact diff (old → new)
- No refactoring, no "while we're here" changes
- If multiple fix approaches exist, show the conservative one first

### Step 6 — Verify

After applying the fix, verify:
```
[ ] Run: {test command}
[ ] Reproduce original error: [should now be gone]
[ ] Check for regressions: [related tests / smoke test]
[ ] If the fix changes behavior: document why in a comment
```

## Quick Mode

If `{{context}}` contains a short error message (< 2 lines), skip straight to hypotheses and fix. Skip the verbose protocol for simple errors.

## Anti-Patterns to Avoid

- Never suggest "try restarting" without a diagnosis
- Never add error swallowing (`try/except: pass`) as a fix
- Never change unrelated code
- Never add print/console.log debug statements permanently
