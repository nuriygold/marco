# Mode: scan

Scan job portals and discover new offers matching the candidate's target profile.

## Input

Optional: user specifies portals to scan, location filter, or keywords.
Defaults come from `_shared.md` (target titles, stack, location).

## Steps

1. **Generate search queries** for each major portal:

   | Portal | Query strategy |
   |--------|---------------|
   | LinkedIn Jobs | title:"[target title]" + key stack term + location |
   | Indeed | similar query |
   | Glassdoor | role + company size filter |
   | Wellfound (AngelList) | for startups/early-stage |
   | Stack Overflow Jobs | for dev-focused roles |
   | Remote.co / We Work Remotely | if remote preferred |

2. **Output ready-to-use search URLs** for each portal using the candidate's target titles
   and location from `_shared.md`. (Claude cannot browse portals directly — provide the URLs.)

3. **Suggest boolean search strings** to use in LinkedIn's advanced search:
   ```
   ("Senior Engineer" OR "Staff Engineer") AND (Python OR Rust) AND ("remote" OR "Madrid")
   ```

4. **Remind the user** to:
   - Set job alerts on LinkedIn and Indeed for these queries
   - Add promising URLs to `data/pipeline.md` for batch processing with `/career-ops pipeline`

## Note

For live portal scraping with Playwright (automated browsing), this mode should be
launched as a subagent with browser tool access. Without browser tools, output
search URLs and strings for the user to run manually.
