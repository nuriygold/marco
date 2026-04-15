# ged-bestie
your bff that helps you pass the test by any means necessary

assistant
### README.md for Ged-Bestie: Personalized GED Math Practice App
Below is a complete, ready-to-use README.md file for your "ged-bestie" GitHub repo. This describes the project, setup, and usage—tailored to the MVP we're building (Next.js frontend with Supabase for adaptive quizzes). 

#### How to Add It
1. Go to github.com/nuriygold/ged-bestie.
2. Click "Add file" > "Create new file".
3. Name it: `README.md`.
4. Paste the content below.
5. Commit with message: "Add README for GED Math app".
6. This will make the repo more "real" and help with workspace activation (retry adding in Marco UI after).

Once added, reply "README added!" + your sample GED questions (5-10, e.g., algebra problems)—then we can stage the code files.

---

```markdown
# Ged-Bestie: Your Personalized GED Math Practice Companion

![Ged-Bestie Logo Placeholder](https://via.placeholder.com/400x200/4A90E2/FFFFFF?text=Ged-Bestie)  
*(Add a logo image here later for branding—e.g., math symbols with a friendly robot "bestie" vibe.)*

Ged-Bestie is a simple, web-based practice tool designed to help you prepare for the **GED Math Test**. It focuses on personalized learning: Take quizzes, track scores, and get adaptive recommendations (e.g., "Struggling with algebra? Here's a targeted drill!"). Built for one user (you), it's mobile-friendly, timer-based to simulate the real 115-minute test, and integrates free resources like explanations and videos.

This app covers all GED Math domains:
- **Quantitative and Algebraic Problem Solving** (fractions, equations, functions).
- **Quantitative Problem Solving with Data** (graphs, stats, probability).
- **Geometry and Measurement** (shapes, area, volume).
- **Number Operations and Number Sense** (basics, decimals, percentages).

**Why Ged-Bestie?** Traditional study guides are static— this adapts to your progress, saving time and boosting confidence for the real GED (aim for 145/200 score).

## Features
- **Personalized Dashboard**: Overview of strengths/weaknesses, progress charts, and daily recommendations based on your scores.
- **Interactive Quizzes**: Multiple-choice, fill-in, and graph-based questions. Timed sections (e.g., 45 questions in 115 mins). Built-in calculator (Desmos embed).
- **Adaptive Learning**: After a quiz, it analyzes results (stored in Supabase DB) and suggests focus areas (e.g., 70% weak topics + review).
- **Study Guides**: Bite-sized lessons with explanations, hints, and links to free resources (Khan Academy videos, GED practice PDFs).
- **Progress Tracking**: Save scores, view history, set goals (e.g., "Improve algebra by 20%"). Export reports (PDF/CSV).
- **User-Friendly**: Simple login (email or Google via Supabase), no ads, responsive design for phone/tablet.
- **GED-Specific**: Mirrors test format—no calculator on some questions, TI-30XS simulator.

**MVP Status**: Core login, dashboard, and basic quizzes ready. Expandable with more questions/content.

## Tech Stack
- **Frontend**: Next.js (React) – Fast, SEO-friendly, deploys easily to Vercel.
- **Database/Auth**: Supabase (PostgreSQL) – Handles user data, scores, and personalization (free tier for personal use).
- **Styling**: Tailwind CSS – Clean, modern UI.
- **Deployment**: Vercel (one-click from GitHub).
- **Other**: JSON for question bank; no complex backend needed.

## Quick Start (Local Development)
If you want to run it on your computer (optional—Vercel handles deploys):

1. **Prerequisites**:
   - Node.js (v18+): Download from nodejs.org.
   - Git: git-scm.com.

2. **Clone and Install**:
   ```
   git clone https://github.com/nuriygold/ged-bestie.git
   cd ged-bestie
   npm install  # Installs Next.js, Supabase, etc.
   ```

3. **Set Up Environment**:
   - Create `.env.local` file in root:
     ```
     NEXT_PUBLIC_SUPABASE_URL=https://ejmkliupmkqmougvkpai.supabase.co
     NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_7uWHwq6JIqG-_NWHkcwu7Q_Iy_o197E
     ```
   - In Supabase Dashboard (supabase.com > Your Project):
     - Run SQL for tables (if not done): See `supabase/migrations/` or dashboard SQL Editor.
     - Enable Auth: Email + optional Google.

4. **Run Locally**:
   ```
   npm run dev
   ```
   - Open http://localhost:3000.
   - Sign up/login > Take a sample quiz > See dashboard.

5. **Test Personalization**:
   - Answer questions > Check Supabase dashboard for saved scores.
   - Reload: See recs like "Focus on algebra (score: 60%)".

## Deployment to Vercel (Recommended – 2 Minutes)
1. Go to vercel.com > Sign up (free, GitHub login).
2. Click "New Project" > Import your repo (`nuriygold/ged-bestie`).
3. In Vercel Settings > Environment Variables: Add the two Supabase vars from above.
4. Click "Deploy" – Gets a live URL (e.g., ged-bestie-abc.vercel.app).
5. Updates auto-deploy on GitHub pushes.

**Cost**: Free for personal use (Vercel hobby tier, Supabase starter).

## Content & Questions
- Questions stored in `data/questions.json` (expandable).
- Current: Starter bank (add more via JSON: topic, question, options, correct, explanation).
- Example Entry:
  ```json
  {
    "topic": "Algebra",
    "question": "Solve for x: 2x + 4 = 10",
    "options": ["A) 3", "B) 4", "C) 6", "D) 7"],
    "correct": "A) 3",
    "explanation": "Subtract 4: 2x = 6, divide by 2: x = 3."
  }
  ```
- To Add: Edit JSON or reply to Marco AI for patches.

## Supabase Setup (If Starting Fresh)
1. supabase.com > New Project: "ged-math-db".
2. Settings > API: Copy URL and anon key to `.env.local`.
3. SQL Editor: Create tables for users, scores, progress (see code in repo or ask Marco).
4. Auth: Enable email logins.

## Roadmap & Expansion
- **Short-Term**: Add 100+ questions, video embeds, full test simulator.
- **Medium**: Multi-user (if needed), AI-generated questions (integrate OpenAI).
- **Long**: Mobile app export (React Native).

## Contributing / Getting Help
- **Built
