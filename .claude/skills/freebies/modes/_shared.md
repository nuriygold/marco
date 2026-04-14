# freebies — Shared Context & Output Format

## User Profile

Read `.marco/config.json`. The user qualifies under these roles:
- **student** — Self-certified. Accepts GitHub Student Pack enrollment, .edu email, or self-declaration for most programs. No formal proof required for many.
- **founder** — Early-stage startup founder. Has or can form a legal entity (LLC/Corp) for programs that require one.
- **startup** — Early-stage company, pre-revenue or early revenue, < 5 years old.
- **oss-license-holder** — Holds projects under OSI-approved licenses (MIT, Apache-2.0, GPL). Has public GitHub repos.
- **fire-sign** — Aries, Leo, or Sagittarius. Use this to surface astrologically-timed opportunities and communities.
- **us-resident** — US resident. Eligible for federal programs, SBA, SBIR, state incentives. Has or can get EIN.

## Eligibility Filtering Rules

When presenting programs, apply these filters:
1. INCLUDE if the user meets the eligibility gate for any of their active roles
2. FLAG as `[CHECK]` if eligibility is ambiguous (e.g., requires active enrollment vs. self-certified)
3. EXCLUDE programs that explicitly require what the user doesn't have (e.g., VC backing from a specific firm)
4. Note when applying: easier applications first (no verification), harder ones last (requires docs)

## Output Format

For each category, output a markdown table:

```
## {Category Name}

| Program | What You Get | Gate | Value | Deadline | Link |
|---------|-------------|------|-------|----------|------|
| Name | Description | Easy/Medium/Hard | $X,XXX | Date or Rolling | URL |
```

**Value tiers:**
- `$0` = fully free, no strings
- `~$XXX/yr` = estimated annual value
- `$X,000 credits` = one-time cloud/tool credits
- `Varies` = depends on usage

**Deadline:**
- `Rolling` = apply anytime
- `Cohort-based` = periodic intake
- Specific date if known

**Tags:**
- `[NEW]` — discovered via live web search, not in static catalog
- `[URGENT]` — deadline within 30 days
- `[CHECK]` — eligibility needs verification
- `[HIGH VALUE]` — estimated value > $10,000

## Quick-Apply Sorting

After the main table, add a **Quick Wins** section listing the top 5 programs by:
1. Easiest to apply (rolling, self-certified)
2. Highest value

Format:
```
### Quick Wins — Apply Today
1. **[Program]** — $XXX, rolling, 5-minute application → [link]
2. ...
```

## Currency Note

Data is accurate to knowledge cutoff (Aug 2025). Run `/freebies new` to surface programs announced after that date. Always verify current terms before applying — amounts and deadlines change frequently.
