# Mode: tracker

Show a summary of the current application pipeline status.

## Data source

Read `data/tracker.md` from the repo root.

If the file doesn't exist, say:
> No tracker data found. Create `data/tracker.md` or run `/career-ops {JD}` to log your first application.

## Tracker file format

`data/tracker.md` uses this format (one row per application):

```
| Date | Company | Role | Grade | Status | Notes |
|------|---------|------|-------|--------|-------|
| 2026-04-01 | Acme Corp | Senior Engineer | B+ | Applied | Waiting for response |
| 2026-04-05 | Beta Inc | Staff Engineer | A- | Interview scheduled | System design round |
```

## Output

Parse the tracker and show:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APPLICATION TRACKER  (as of [today's date])
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total applications: N

BY STATUS
  Applied:              N
  Interview scheduled:  N
  In process:           N
  Offer received:       N
  Rejected:             N
  Withdrawn:            N

ACTIVE PIPELINE (non-rejected, non-withdrawn)
  [Company] — [Role] ([Grade]) · [Status] · [Date]
  ...

RECENT REJECTIONS
  [Company] — [Role] · [Date]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

End with a 1-line observation (e.g. "Pipeline is healthy — 3 active leads." or "Response rate low — consider following up on applications older than 2 weeks.").
