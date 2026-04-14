# Mode: auto-pipeline

Triggered when the user pastes a JD or URL directly (no sub-command).

## Steps

1. **Fetch JD** — if input is a URL, fetch and extract the job description text. If it's raw text, use as-is.

2. **Evaluate** — run the `oferta` scoring rubric against the candidate's North Star from `_shared.md`:
   - Extract: company, role title, location/remote, stack, seniority, compensation (if listed)
   - Score each North Star dimension (1–5)
   - Compute weighted total
   - Issue grade: A (≥4.5), B (≥4.0), C (≥3.5), D (≥3.0), F (<3.0)
   - List top 3 pros and top 3 cons

3. **Report** — print a concise evaluation card:
   ```
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   [Company] — [Role]
   Grade: B+ | Score: 4.1/5
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Pros: ...
   Cons: ...
   Verdict: APPLY / SKIP / BORDERLINE
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ```

4. **If verdict is APPLY or BORDERLINE:**
   - Generate a tailored CV using the `pdf` mode logic (ATS-optimized, keywords from JD)
   - Log entry to `data/tracker.md`: date, company, role, grade, status=Applied
   - Suggest a LinkedIn contact to reach out to (use `contacto` mode logic)

5. **Summary** — end with a one-paragraph cover letter hook (3 sentences max).
