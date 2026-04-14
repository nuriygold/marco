# Mode: pdf

Generate an ATS-optimized CV tailored to a specific JD.

## Input

User provides a JD (text or URL). Candidate profile comes from `_shared.md`.

## Steps

1. **Extract JD keywords** — pull hard skills, soft skills, tools, and role-specific verbs
   that appear in the JD. Note which appear multiple times (high weight).

2. **Tailor the profile** — from the CV in `_shared.md`:
   - Reorder bullet points to front-load JD-relevant achievements
   - Mirror JD language in bullets (without fabricating experience)
   - Ensure every high-weight keyword appears at least once naturally
   - Trim irrelevant experience to keep CV to 1–2 pages

3. **Write the tailored CV** in this structure:

   ```
   [NAME]
   [Location] · [Email] · [LinkedIn]

   SUMMARY
   2–3 sentences. Mirror the role's language. Lead with years of relevant exp.

   EXPERIENCE
   [Company] — [Title] | [Date range]
   • [Achievement 1 — quantified]
   • [Achievement 2 — quantified]
   • [Achievement 3]

   [Repeat for each role]

   SKILLS
   [Grouped: Languages | Frameworks | Infra | Tools]

   EDUCATION
   [Degree, Institution, Year]
   [Certs if relevant]
   ```

4. **ATS check** — confirm:
   - No tables, columns, or graphics (plain text friendly)
   - Job title in summary matches JD title closely
   - Contact info on first line
   - Standard section headings

5. **Output** the full CV text, ready to paste into a PDF generator or Google Docs.

> To actually produce a PDF file, the user should paste this into their preferred editor
> (Google Docs, Notion, Typst, LaTeX) — PDF generation from CLI requires a separate tool.
