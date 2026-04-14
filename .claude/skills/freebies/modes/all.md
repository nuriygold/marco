# freebies all — Full Scan Mode

Scan all 6 categories simultaneously and return a unified opportunity report.

## Execution

1. Load all 6 data files: `data/student.md`, `data/founder.md`, `data/startup.md`, `data/oss.md`, `data/fire.md`, `data/usa.md`
2. Apply eligibility filter from `_shared.md`
3. De-duplicate any programs that appear in multiple categories (keep under highest-value category)
4. Output sections in this order: Startup → Student → OSS → Founder → USA → Fire

## Output Structure

```
# freebies — Full Opportunity Scan
*Profile: student · founder · startup · OSS · Fire sign · US resident*

## Summary
- Total programs found: X
- Estimated total value: $XXX,XXX
- Quick wins (apply today): X programs

---

## Startup Programs
[table]

## Student Programs  
[table]

## OSS Benefits
[table]

## Founder Perks
[table]

## US Grants & Programs
[table]

## Fire Sign Opportunities
[table]

---

## Master Quick Wins — Top 10 by Value + Ease
[ranked list]
```

## Estimated Value Calculation

After outputting all tables, calculate and show:
- **Cloud credits available:** sum all cloud credit programs
- **Tool savings/yr:** sum all software subscriptions
- **Grant potential:** sum non-dilutive grants you can apply for
- **Total addressable value:** combined estimate

Example:
```
### Value Summary
- Cloud credits: $151,000 (AWS + GCP + Azure + DigitalOcean + others)
- Tool/SaaS savings: ~$8,000/yr
- Non-dilutive grants: $275,000–$1,000,000 (SBIR Phase I/II)
- Total addressable: $1,400,000+
```
