# Mode: deep

Deep research prompt about a company before interview or application.

## Input

User provides company name (and optionally a role level).

## Research areas

Compile a structured research brief covering:

### 1. Company basics
- Founded, HQ, size (headcount), stage (public / private / pre-IPO)
- Funding history and latest valuation
- Revenue model and key customers

### 2. Product and tech
- Core product(s) — what problem, for whom
- Known tech stack (job postings, engineering blog, GitHub orgs)
- Engineering blog, talks, open-source contributions

### 3. Team signals
- CTO / VP Eng background and tenure
- Recent leadership hires or departures (LinkedIn, news)
- Engineering culture indicators (on-call culture, incident history, blog tone)

### 4. Growth and trajectory
- Recent funding rounds or acquisitions
- Headcount trend (growing fast / stable / layoffs)
- Product launches in the last 12 months

### 5. Competitive landscape
- Top 3 competitors
- Candidate company's differentiation

### 6. Red flags and green flags
- Glassdoor patterns (not individual reviews — patterns)
- Engineering blog freshness
- Interview process reputation

## Output format

Structured brief, one section per heading above.
End with: **3 smart questions to ask in the interview** based on the research.
