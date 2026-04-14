# Mode: batch

Batch-process multiple JD URLs in parallel using subagents.

## Input

User provides a list of URLs (or they are read from `data/pipeline.md`).

## Steps

1. **Read URLs** — if no URLs provided, read `data/pipeline.md` and extract all URLs
   (one per line, lines starting with `#` are comments/skipped).

2. **If 1–2 URLs** — process sequentially using `auto-pipeline` logic inline.

3. **If 3+ URLs** — launch one subagent per URL (max 5 in parallel):

   ```
   Agent(
     subagent_type="general-purpose",
     description="career-ops evaluate [URL]",
     prompt="[content of _shared.md]\n\n[content of auto-pipeline.md]\n\nProcess this JD: [URL]"
   )
   ```

4. **Collect results** — aggregate all evaluation cards into a ranked summary:

   ```
   BATCH RESULTS ([N] offers processed)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   #1  A-  Acme Corp — Staff Engineer        → APPLY
   #2  B+  Beta Inc — Senior Engineer        → APPLY
   #3  B   Gamma Co — Backend Engineer       → BORDERLINE
   #4  C+  Delta Ltd — Mid Engineer          → SKIP
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

5. **Log** all APPLY and BORDERLINE results to `data/tracker.md`.

6. **Clear processed URLs** from `data/pipeline.md` (or mark them as done with `✓`).
