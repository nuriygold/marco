# freebies apply — Application Deep-Dive Mode

Usage: `/freebies apply <program name>`

Prepare everything needed to apply for a specific program.

## Execution

1. Identify the program from the argument (fuzzy match against all data catalogs)
2. If ambiguous, list matches and ask which one
3. If not found in catalogs, run a WebSearch to find current details

## For Each Program, Produce:

### 1. Program Brief
- Full name and provider
- What you get (exact amounts/benefits)
- Eligibility requirements (full list)
- Application URL
- Deadline
- Time to apply (estimated)
- Approval timeline (estimated)

### 2. Eligibility Check
Run through each eligibility requirement against the user profile:
```
✅ US company / US resident → PASS
✅ Early-stage startup → PASS  
✅ OSS project on GitHub → PASS
⚠️  Requires .edu email → CHECK (self-certified student)
❌ Requires VC backing from specific firm → NOT ELIGIBLE
```

### 3. Application Materials Checklist
List everything needed:
- [ ] Company name and EIN (if required)
- [ ] GitHub profile URL
- [ ] 1-sentence project description
- [ ] Team size
- [ ] Monthly active users / GitHub stars (if required)
- [ ] Pitch deck (if required)
- [ ] Tax ID / W9 (for grants)

### 4. Draft Application Text
If the program has a form or essay questions, draft the answers based on the user's profile.
Keep answers short, confident, execution-first tone.

Example for AWS Activate:
```
Company name: [your company]
Website: [your site]
Stage: Pre-seed
Team size: 1-5
What are you building? [1-2 sentences]
How will you use AWS? Primary cloud infrastructure for [product]
```

### 5. Next Steps
```
1. Visit: [application URL]
2. Have ready: [checklist items from step 3]
3. Submit by: [deadline]
4. Expected response: [timeline]
```
