---
name: test
description: Run the full Marco test suite -- Python unittest and Rust cargo test
user_invocable: true
args: filter
---

# Test Runner

Run both test surfaces for this repo. Report results for each suite separately.

## Python tests

```bash
python3 -m unittest discover -s tests -v
```

If `{{filter}}` is provided, use it as a test name pattern:
```bash
python3 -m unittest discover -s tests -v -k {{filter}}
```

## Rust tests

```bash
cd rust && cargo test --workspace
```

If `{{filter}}` is provided, also pass it to cargo:
```bash
cd rust && cargo test --workspace {{filter}}
```

## Output

```
TEST RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Python (unittest)
  Ran N tests in Xs
  ✓ OK  (or ✗ FAILED: N failures, N errors)

Rust (cargo test)
  running N tests
  ✓ N passed  (or ✗ N failed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall: PASS / FAIL
```

If any tests fail, show the full failure output (test name, assertion, traceback).
Do not summarize away failures — show them in full so they can be fixed.
