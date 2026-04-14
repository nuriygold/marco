---
name: rust-check
description: Run the full Rust workspace verification suite -- cargo fmt, clippy -D warnings, cargo test
user_invocable: true
args: target
---

# Rust Check

Run the full Rust verification suite as defined in `CLAW.md`, from the `rust/` directory.

## Steps

Run these in order. Stop and report on first failure.

### 1. Format check
```bash
cd rust && cargo fmt --all -- --check
```
If this fails: run `cargo fmt --all` to auto-fix, show the diff, and ask the user to review.

### 2. Clippy (deny warnings)
```bash
cd rust && cargo clippy --workspace --all-targets -- -D warnings
```
If this fails: show each warning/error with its file and line. Do not suppress warnings — fix them.

### 3. Tests
```bash
cd rust && cargo test --workspace
```
If `{{target}}` was provided, scope to that crate:
```bash
cd rust && cargo test -p {{target}}
```

## Output

Report pass/fail per step:

```
rust-check
  ✓ cargo fmt       (or ✗ + diff)
  ✓ cargo clippy    (or ✗ + errors)
  ✓ cargo test      (or ✗ + failures)

All checks passed.  (or: N checks failed.)
```

If all pass, say so clearly. If any fail, list the specific errors and suggest fixes.
