# MeetBrief — 2.5-Minute Demo Video Script

**Target Video Length:** 2 minutes 30 seconds  
**Speaker Tone:** Confident, energetic, analytical, and crisp  
**Preparation:**
- Have Bifrost running on `http://localhost:8080`
- Have MeetBrief open in browser at `http://127.0.0.1:8000`
- Keep a backup tab with the loaded demo briefing in case of network latency

---

### Segment 1: The Problem & Solution Hook (0:00 – 0:20)
- **Visual:** Face to camera or split-screen showing meeting calendar packed with customer calls.
- **Voiceover:**
  > *"Every executive, salesperson, and investor knows that thorough meeting prep wins deals. But researching a company's last 30 days takes 45 minutes of manual Googling, and generic chatbot summaries are notorious for hallucinating dates, numbers, and fake product launches."*
  > *"Meet **MeetBrief**: an autonomous, pre-meeting briefing agent that turns an entity name and meeting time into a verified, source-backed, one-page executive briefing in 15 seconds."*

---

### Segment 2: Initiating a Live Briefing (0:20 – 0:50)
- **Visual:** Screen share of MeetBrief web interface (`http://127.0.0.1:8000`).
- **Action:**
  - Type entity: `Stripe`
  - Meeting date-time: Tomorrow 10:00 AM (automatically localized)
  - Meeting type: Select `Investor`
  - User goal: *"Evaluating high-scale payment processing and AI agent commerce primitives."*
  - Click **Generate Briefing**.
- **Voiceover:**
  > *"Watch this. We enter Stripe, select an Investor meeting for tomorrow, and state our strategic goal. When we click Generate, MeetBrief executes a deterministic 7-step pipeline—not a black-box chatbot loop."*
- **Visual:** Point out the live 7-step stepper progressing from 30-day window clipping to Tavily research, syndication clustering, and Bifrost synthesis.

---

### Segment 3: The Verified One-Pager & Grounding (0:50 – 1:15)
- **Visual:** The completed briefing renders on the A4-proportioned sheet.
- **Action:** Scroll through the sections: Executive TL;DR, Key Developments timeline, clickable `[S#]` tags.
- **Voiceover:**
  > *"Here is the final one-page briefing. Notice four immediate differentiators:*
  > *First, every development is strictly bounded to the last 30 days before our meeting.*
  > *Second, every single bullet has clickable citations `[S1]`, `[S2]` that link directly to the primary crawled source.*
  > *Third, look at these colored badges: VERIFIED, REPORTED, UNVERIFIED. These confidence ratings are computed by Python code—never left to the LLM's own self-rating."*

---

### Segment 4: Transparent Honesty & "Saying What We Don't Know" (1:15 – 1:35)
- **Visual:** Zoom in on an `UNVERIFIED` item and the amber "Unverified Findings & Evidence Gaps" box.
- **Voiceover:**
  > *"Unlike typical AI tools that hallucinate when data is thin, MeetBrief practices radical transparency. If an ungrounded figure or an unconfirmed rumour appears, our verification pass downgrades it to UNVERIFIED and explicitly highlights it under 'Unverified Findings'."*
  > *"We tell the executive exactly what is verified, what is uncertain, and what evidence was missing."*

---

### Segment 5: Research Trace & Judging Differentiator (1:35 – 1:55)
- **Visual:** Click the **Research Trace** button on the toolbar; expand the audit drawer.
- **Voiceover:**
  > *"Clicking 'Research Trace' reveals the complete deterministic audit log: the exact queries planned across categories, Tavily cache hits, near-duplicate syndication clustering, and any claims stripped out by our fact-checker."*
  > *"Nothing is hidden; every step is inspectable and reproducible."*

---

### Segment 6: Bifrost Gateway & Architecture (1:55 – 2:20)
- **Visual:** Switch briefly to the Bifrost Gateway dashboard at `http://localhost:8080`.
- **Voiceover:**
  > *"Under the hood, all search queries run through Tavily with temporal filters and full-text extraction. All LLM calls pass exclusively through Bifrost—our OpenAI-compatible reverse-proxy gateway."*
  > *"With Bifrost, we get unified request logging, provider fallbacks, and the ability to switch models from Gemini 2.5 Flash to Claude or GPT-4o simply by updating a single environment variable."*

---

### Segment 7: A4 Print Preview & Close (2:20 – 2:30)
- **Visual:** Click **Print / Save PDF**. The native browser print dialog opens, showing a clean, pixel-perfect single A4 sheet.
- **Voiceover:**
  > *"Hit Print, and our CSS enforces a perfect single A4 page—ready to slide into your notebook or view on your iPad walking into the boardroom."*
  > *"MeetBrief: grounded, verified, and ready for work. Thank you!"*

---

### Demo Fallback Protocol
If the local Bifrost gateway is stopped or external WiFi is unavailable, click **Load Demo Briefing** in the header. The app immediately renders the offline-verified Stripe briefing with full trace and citation links enabled.
