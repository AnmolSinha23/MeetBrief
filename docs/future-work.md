# MeetBrief — Future Work & Roadmap

This document captures forward-looking architectural extensions, potential roadmap enhancements, and research ideas identified during the hackathon build.

---

## 1. CRM & Calendar Integrations
- **Google Calendar / Outlook 365 Auto-Trigger**:
  - Automatically poll tomorrow's meetings, extract participant email domains and attendee names, and pre-generate briefings overnight.
  - Deliver generated briefings directly to email or Slack at 8:00 AM before the workday begins.
- **HubSpot & Salesforce Bi-Directional Sync**:
  - Enrich briefings with internal CRM deal history, previous meeting notes, and ARR stages.
  - Automatically log the pre-meeting briefing back to the relevant CRM deal or account timeline.

## 2. Advanced Multi-Modal Intelligence
- **Quarterly Earnings Call Audio Analysis**:
  - Leverage Gemini 2.5 multimodal audio reasoning to transcribe and ingest the latest 45-minute earnings call audio alongside Tavily text extracts.
- **Executive Video Appearance Extraction**:
  - Ingest keynote presentations and podcast appearances directly via Gemini video tokens to extract non-verbal strategic priorities and demeanor.

## 3. Real-Time Collaboration & Annotation
- **Collaborative Notes Layer**:
  - Allow team members to highlight briefing claims, add internal commentary, and check off open questions during the live meeting.
- **Post-Meeting Debrief Mode**:
  - Record meeting audio or notes and compare actual discussion topics against the pre-meeting briefing to highlight unanswered questions or unexpected divergences.

## 4. Specialized Industry Depth Packs
- **Biotech / Pharma Mode**:
  - Ingest clinicaltrials.gov, FDA filings, and PubMed citations for drug candidate pipelines.
- **Legal / IP Mode**:
  - Ingest USPTO patent grants and PACER court dockets for litigation risk assessment.
