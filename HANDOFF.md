# MeetBrief — Teammate Handoff & Launch Guide

> **Welcome to MeetBrief!**  
> This guide is designed for anyone to copy and paste without needing Python coding knowledge. Follow these simple steps in order to add your API keys, run preflight verification, and publish the project to GitHub.

---

## 1. What This Is & What Is Already Done

MeetBrief is an autonomous, pre-meeting briefing agent built for the Global AI Hackathon (Problem Statement 05). It turns any company or person name plus a meeting time into a verified, 1-page executive briefing backed by real web citations and code-computed confidence ratings.

**Status:** The entire application, frontend, API, search & LLM clients, tests, and offline demo mode are **100% built, passing all 25 test suites, and verified offline**. You only need to plug in your live API keys to perform the final real-network validation.

---

## 2. Prerequisites

Ensure you have these tools installed on your computer. Open a terminal and run:

| Command | Minimum Version Required |
|---|---|
| `python --version` (or `python3 --version`) | Python 3.11 or higher |
| `node --version` | Node.js v18 or higher (for Bifrost) |
| `git --version` | Git 2.30 or higher |

---

## 3. Get Your Free API Keys

1. **Tavily Search API Key**:
   - Sign up at [https://app.tavily.com/](https://app.tavily.com/)
   - Copy your API key (looks like `tvly-xxxxxxxxxxxxxxxxxxxx`).
2. **Google Gemini API Key**:
   - Get a free key at [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

---

## 4. One-Time Setup

Open your terminal in the `random hackathon` repository directory:

### Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux (Terminal):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

---

## 5. Paste Your Keys

Open the newly created `.env` file in your text editor (VS Code, Notepad, etc.):

1. Replace `tvly-xxxxxxxx` with your real Tavily key:
   ```ini
   TAVILY_API_KEY=tvly-your_actual_key_here
   ```
2. Leave these settings as they are:
   ```ini
   BIFROST_BASE_URL=http://localhost:8080/v1
   BIFROST_API_KEY=dummy
   LLM_MODEL=gemini/gemini-2.5-flash
   ```
3. Save the `.env` file.

---

## 6. Start Bifrost Gateway

Open a **separate, dedicated terminal window** and run:

### Windows (PowerShell):
```powershell
scripts\start_bifrost.ps1
```

### macOS / Linux (Terminal):
```bash
bash scripts/start_bifrost.sh
```

- Leave this terminal window running in the background.
- Open your browser to [http://localhost:8080](http://localhost:8080).
- In the Bifrost dashboard, navigate to:  
  **Model Providers** → **Google Gemini** → **Add Key**
- Paste your Gemini API key from Step 3 and click **Save**.

---

## 7. Preflight Verification (Doctor Script)

In your original terminal window (with `.venv` activated), run:

```bash
python scripts/doctor.py
```

Every line should display **`[PASS]`** and conclude with:
```
=================================================================
READY FOR LIVE USE: yes
=================================================================
```

### Troubleshooting Guide:
| Issue | Cause | Fix |
|---|---|---|
| `TAVILY_API_KEY is missing or placeholder` | `.env` has default placeholder | Open `.env` and paste your `tvly-...` key from Step 3. |
| `Bifrost gateway unreachable at http://localhost:8080/v1` | Bifrost is not running or port occupied | Ensure Step 6 is running in its own terminal window. |
| `LLM completion failed` | Gemini key not added in Bifrost | Visit [http://localhost:8080](http://localhost:8080), go to Model Providers → Google Gemini, and add your key. |
| `429 Rate Limit from Gemini` | Free tier quota spike | Wait 60 seconds and re-run. Gemini free tier resets every minute. |
| `Tavily returned 0 results` | Obscure or misspelled company | Test with a well-known entity like `Stripe` or `Microsoft`. |

---

## 8. Generate Real Artifacts (Run Once)

Once `scripts/doctor.py` passes, execute these commands in order to generate live hackathon artifacts:

1. **Regenerate Live Sample Briefing**:
   ```bash
   python scripts/make_sample.py
   ```
2. **Execute Live Benchmark Evaluation**:
   ```bash
   python scripts/eval_samples.py --live
   ```
   *(This updates `docs/eval-results.md` with real network latency and live metrics).*
3. **Launch the Web App**:
   ```bash
   python scripts/run.py
   ```
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Generate 2–3 briefings for your favorite companies (e.g., Stripe, NVIDIA, OpenAI).

---

## 9. Push to GitHub

1. Create a new **empty public repository** named `meetbrief` on [GitHub](https://github.com/new).
   *(Do NOT check the boxes for README, .gitignore, or license—those are already present).*
2. In your terminal, run the following commands (replace `<GITHUB_USERNAME>` with your GitHub handle):

```bash
# Verify that .env is NOT tracked (must return empty)
git status

# Rename branch and set remote
git branch -M main
git remote add origin https://github.com/AnmolSinha23/MeetBrief.git

# Stage any new live artifacts and commit
git add -A
git commit -m "chore: add real sample, eval results, and live verification"

# Push to GitHub
git push -u origin main
git tag v0.1.0
git push origin v0.1.0
```

### Recommended Repository Settings on GitHub:
- **Repository Description**: `MeetBrief — Grounded, source-backed pre-meeting briefings powered by Tavily & Bifrost`
- **Topics**: `ai-agent`, `tavily`, `bifrost`, `fastapi`, `hackathon`, `llm`, `gemini`, `python`

---

## 10. Record Demo & Submit

1. Follow the 2.5-minute script in [`docs/demo-script.md`](docs/demo-script.md) to record your presentation walkthrough.
2. Submit your project on the Hackathon portal:
   - **Repository Link**: `https://github.com/AnmolSinha23/MeetBrief`
   - **Demo Video URL**: Your uploaded YouTube / Loom link.
   - **Problem Statement**: #05 (Pre-Meeting Briefing Agent).

---

## 11. Live Verification Checklist (LIVE-PENDING)

The following items were verified using deterministic mock fixtures during the automated build and are pending final live validation with your real keys:

- [ ] **Live Tavily News Search & Temporal Filter**:
  - *How to check:* Run `python scripts/doctor.py`. Check 3 will search for Microsoft news over the past 30 days and report result count and raw field names.
  - *What to report if it fails:* Output from check 3 (e.g. `401 Unauthorized` or `400 Bad Request`).
- [ ] **Live Bifrost LLM Route & Gateway Latency**:
  - *How to check:* Run `python scripts/doctor.py`. Check 5 will ping `gemini/gemini-2.5-flash` through `http://localhost:8080/v1` and print the latency in ms.
  - *What to report if it fails:* Error message from check 5 or check 6.
- [ ] **Live Evaluation Benchmark Suite**:
  - *How to check:* Run `python scripts/eval_samples.py --live`.
  - *What to report if it fails:* Any assertion failure or traceback in `docs/eval-results.md`.
