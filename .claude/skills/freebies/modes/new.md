# freebies new — Live Discovery Mode

Search for programs announced or updated within the last 30 days.

## Execution

Perform 6 targeted web searches — one per role category. Run them as a batch:

```
WebSearch: "startup credits program free 2025 2026 new announced"
WebSearch: "student developer free program credits 2025 2026"  
WebSearch: "open source maintainer free tools credits 2025 2026"
WebSearch: "founder startup perks deals new 2025 2026"
WebSearch: "SBIR STTR grant opportunity 2025 2026 deadline"
WebSearch: "fire sign astrology event community 2025 2026"
```

Also search for limited-time offers:
```
WebSearch: "startup cloud credits limited time 2025 apply now deadline"
WebSearch: "student developer pack new tool added 2025"
```

## Filtering

From search results:
1. Extract program names, what they offer, eligibility, and links
2. Flag anything with a deadline as `[URGENT]` if < 30 days
3. Compare against static catalogs — mark as `[NEW]` if not already listed
4. Discard duplicate results and marketing noise

## Output

```
# freebies new — Recently Announced (Live Search)
*Searched: {current date}*

## New Programs Found [NEW]
[table with NEW tag on each]

## Updated / Deadline Alerts [URGENT]
[table with URGENT tag — programs with imminent deadlines]

## Confirmed Still Active (from searches)
[brief list confirming major programs are still running]

---
*Run /freebies all for the full static catalog.*
```
