# Mode: apply

Live application assistant — read a job application form and generate tailored answers.

## Input

User pastes the application form fields (or describes them). Profile comes from `_shared.md`.

## Steps

1. For each form field, generate a tailored answer:

   **Short text fields** (e.g. "Why do you want to work here?"):
   - 2–4 sentences max
   - Specific to the company/role — not generic
   - Reference something real about the company (product, mission, engineering culture)

   **Long text fields** (e.g. cover letter, "Tell us about yourself"):
   - 3 paragraphs: who you are → why this role → why this company
   - Lead with the strongest relevant experience
   - Mirror the JD's language

   **Yes/No or multiple choice** — answer directly based on profile facts.

   **Salary expectation** — use the range from `_shared.md`. Give a number, not a range,
   unless the field explicitly asks for range. Start at mid-to-high of your range.

2. Flag any fields that require information not in `_shared.md` (e.g. references, specific project URLs).

## Output

Print each field label followed by the generated answer, clearly separated:

```
--- Why do you want to work here? ---
[answer]

--- Describe a technical challenge you solved ---
[answer]

--- Expected salary ---
[answer]

--- NEEDS YOUR INPUT ---
- References: [not in profile — add 2–3 names]
```
