# Mode: pipeline

Process pending URLs from the inbox file `data/pipeline.md`.

## Steps

1. **Read `data/pipeline.md`** — extract all unprocessed URLs.
   - Lines starting with `#` are comments — skip.
   - Lines starting with `✓` are already processed — skip.
   - Plain URLs are pending.

2. **If file is empty or all done:**
   > Pipeline is empty. Add URLs to `data/pipeline.md` (one per line) to queue them.

3. **If 1–2 pending URLs** — process inline with `auto-pipeline` logic.

4. **If 3+ pending URLs** — delegate to `batch` mode logic (parallel subagents, max 5).

5. **After processing** — mark each processed URL with `✓` prefix in `data/pipeline.md`.

6. **Print summary** — show evaluation cards for all processed offers and the updated tracker count.

## data/pipeline.md format

```markdown
# Career-Ops Pipeline Inbox
# Add one URL per line. Lines starting with ✓ are processed.

https://example.com/jobs/senior-engineer
https://example.com/jobs/staff-engineer
✓ https://example.com/jobs/backend-dev  (processed 2026-04-01, Grade: B+, APPLIED)
```
