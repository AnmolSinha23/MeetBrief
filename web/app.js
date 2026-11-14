/**
 * MeetBrief Web Application JavaScript
 */

document.addEventListener("DOMContentLoaded", () => {
  // UI Elements
  const briefingForm = document.getElementById("briefingForm");
  const entityInput = document.getElementById("entityInput");
  const hintInput = document.getElementById("hintInput");
  const meetingTimeInput = document.getElementById("meetingTimeInput");
  const timezoneDisplay = document.getElementById("timezoneDisplay");
  const meetingTypeSelect = document.getElementById("meetingTypeSelect");
  const contextInput = document.getElementById("contextInput");
  const contextCharCount = document.getElementById("contextCharCount");
  const btnSubmit = document.getElementById("btnSubmit");
  const btnLoadDemo = document.getElementById("btnLoadDemo");
  const btnLoadDemoHeader = document.getElementById("btnLoadDemoHeader");
  const connectionStatus = document.getElementById("connectionStatus");

  const stepperBox = document.getElementById("stepperBox");
  const progressBar = document.getElementById("progressBar");
  const stepProgressLabel = document.getElementById("stepProgressLabel");
  const currentStepText = document.getElementById("currentStepText");

  const errorBanner = document.getElementById("errorBanner");
  const errorMessage = document.getElementById("errorMessage");

  const disambiguationBox = document.getElementById("disambiguationBox");
  const candidateList = document.getElementById("candidateList");

  const emptyState = document.getElementById("emptyState");
  const briefingSheet = document.getElementById("briefingSheet");
  const briefingToolbar = document.getElementById("briefingToolbar");
  const briefingTitleDisplay = document.getElementById("briefingTitleDisplay");
  const briefingBadgeStatus = document.getElementById("briefingBadgeStatus");

  const btnCopyMd = document.getElementById("btnCopyMd");
  const btnDownloadMd = document.getElementById("btnDownloadMd");
  const btnPrintPdf = document.getElementById("btnPrintPdf");
  const btnToggleTrace = document.getElementById("btnToggleTrace");
  const tracePanel = document.getElementById("tracePanel");
  const btnCloseTrace = document.getElementById("btnCloseTrace");
  const traceContent = document.getElementById("traceContent");

  let activeBriefingId = null;
  let activeBriefingData = null;
  let pollInterval = null;

  // 1. Initialize Defaults
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  timezoneDisplay.value = userTimezone;

  // Default meeting date: tomorrow at 10:00 AM local
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(10, 0, 0, 0);

  const pad = (n) => String(n).padStart(2, "0");
  const formattedDefault = `${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(tomorrow.getDate())}T${pad(tomorrow.getHours())}:${pad(tomorrow.getMinutes())}`;
  meetingTimeInput.value = formattedDefault;

  // Character counter for context
  contextInput.addEventListener("input", () => {
    contextCharCount.textContent = `${contextInput.value.length}/400`;
  });

  // 2. Health check
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Health check returned status " + res.status);
      const data = await res.json();
      if (data.mock_mode) {
        connectionStatus.textContent = "⚡ MOCK MODE (Offline Fixtures)";
        connectionStatus.className = "status-indicator mock";
      } else if (data.ok) {
        connectionStatus.textContent = `🟢 LIVE (${data.model})`;
        connectionStatus.className = "status-indicator ready";
      } else {
        const issues = [];
        if (!data.tavily_configured) issues.push("Tavily key missing");
        if (!data.bifrost_reachable) issues.push("Bifrost unreachable");
        connectionStatus.textContent = `⚠️ Setup needed: ${issues.join(", ")}`;
        connectionStatus.className = "status-indicator";
      }
    } catch (e) {
      connectionStatus.textContent = "⚪ Offline / Connecting...";
      connectionStatus.className = "status-indicator";
    }
  }
  checkHealth();

  // 3. Form Submission & Polling
  briefingForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    hideError();
    hideDisambiguation();

    const entity = entityInput.value.trim();
    if (!entity) return;

    const entityType = document.querySelector('input[name="entityType"]:checked').value;
    const hint = hintInput.value.trim() || null;
    const meetingType = meetingTypeSelect.value;
    const userContext = contextInput.value.trim() || null;

    // Convert datetime-local to ISO string with timezone offset
    const localDate = new Date(meetingTimeInput.value);
    const tzOffsetMinutes = -localDate.getTimezoneOffset();
    const offsetSign = tzOffsetMinutes >= 0 ? "+" : "-";
    const absOffsetHours = pad(Math.floor(Math.abs(tzOffsetMinutes) / 60));
    const absOffsetMinutes = pad(Math.abs(tzOffsetMinutes) % 60);
    const isoStringWithOffset = `${meetingTimeInput.value}:00${offsetSign}${absOffsetHours}:${absOffsetMinutes}`;

    const payload = {
      entity,
      entity_type: entityType,
      meeting_time: isoStringWithOffset,
      timezone: userTimezone,
      meeting_type: meetingType,
      hint,
      user_context: userContext,
    };

    setLoading(true);
    showStepper(1, "Starting briefing generation...");

    try {
      const res = await fetch("/api/briefings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to start briefing job.");
      }

      const { job_id } = await res.json();
      pollJob(job_id);
    } catch (err) {
      setLoading(false);
      hideStepper();
      showError(err.message);
    }
  });

  // Poll Job Progress
  function pollJob(jobId) {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw new Error("Could not check job status");
        const job = await res.json();

        updateStepper(job.steps_done || 1, job.step || "Processing...");

        if (job.status === "done") {
          clearInterval(pollInterval);
          setLoading(false);
          hideStepper();
          loadBriefingResult(job.briefing_id);
        } else if (job.status === "error") {
          clearInterval(pollInterval);
          setLoading(false);
          hideStepper();
          showError(job.error || "Generation encountered an error.");
        }
      } catch (err) {
        clearInterval(pollInterval);
        setLoading(false);
        hideStepper();
        showError("Lost connection while waiting for briefing result.");
      }
    }, 700);
  }

  // Load and Render Briefing
  async function loadBriefingResult(briefingId) {
    try {
      // 1. Fetch JSON data
      const jsonRes = await fetch(`/api/briefings/${briefingId}`);
      if (!jsonRes.ok) throw new Error("Failed to load briefing data");
      activeBriefingData = await jsonRes.json();
      activeBriefingId = activeBriefingData.id;

      // Handle needs_clarification
      if (activeBriefingData.status === "needs_clarification") {
        showDisambiguation(activeBriefingData.candidates);
        return;
      }

      // 2. Fetch rendered A4 HTML
      const viewRes = await fetch(`/api/briefings/${briefingId}/view`);
      if (!viewRes.ok) throw new Error("Failed to load briefing document");
      const htmlText = await viewRes.text();

      // Display rendered briefing
      briefingSheet.innerHTML = htmlText;
      emptyState.style.display = "none";
      briefingSheet.style.display = "block";
      briefingToolbar.style.display = "flex";

      briefingTitleDisplay.textContent = `${activeBriefingData.entity.canonical_name} — Pre-Meeting Briefing`;
      briefingBadgeStatus.textContent = activeBriefingData.status === "ok" ? "READY (ONE-PAGER)" : activeBriefingData.status.toUpperCase();

      // Populate trace panel
      renderTrace(activeBriefingData);

      // Scroll smoothly to result on smaller screens
      if (window.innerWidth < 1024) {
        briefingToolbar.scrollIntoView({ behavior: "smooth" });
      }
    } catch (e) {
      showError(e.message);
    }
  }

  // Load Demo Briefing
  async function loadDemo() {
    hideError();
    hideDisambiguation();
    setLoading(true);
    try {
      const res = await fetch("/api/samples/demo");
      if (!res.ok) throw new Error("Could not load demo sample");
      const demoData = await res.json();
      await loadBriefingResult(demoData.id);
      setLoading(false);
    } catch (e) {
      setLoading(false);
      showError("Could not load demo briefing: " + e.message);
    }
  }

  btnLoadDemo.addEventListener("click", loadDemo);
  btnLoadDemoHeader.addEventListener("click", loadDemo);

  // Stepper UI helper
  function showStepper(stepNum, msg) {
    stepperBox.style.display = "block";
    updateStepper(stepNum, msg);
  }

  function hideStepper() {
    stepperBox.style.display = "none";
  }

  function updateStepper(stepNum, msg) {
    const clamped = Math.max(1, Math.min(7, stepNum));
    const percent = Math.round((clamped / 7) * 100);
    progressBar.style.width = `${percent}%`;
    stepProgressLabel.textContent = `Step ${clamped} of 7`;
    currentStepText.textContent = msg;

    for (let i = 1; i <= 7; i++) {
      const el = document.getElementById(`step${i}`);
      if (!el) continue;
      el.className = "step-item";
      if (i < clamped) {
        el.classList.add("done");
      } else if (i === clamped) {
        el.classList.add("active");
      }
    }
  }

  // Disambiguation UI
  function showDisambiguation(candidates) {
    candidateList.innerHTML = "";
    candidates.forEach((cand) => {
      const card = document.createElement("div");
      card.className = "candidate-card";
      card.innerHTML = `
        <div class="cand-name">${cand.label}</div>
        <div class="cand-hint">${cand.hint || ""}</div>
      `;
      card.addEventListener("click", () => {
        hintInput.value = cand.hint || cand.label;
        disambiguationBox.style.display = "none";
        briefingForm.dispatchEvent(new Event("submit"));
      });
      candidateList.appendChild(card);
    });
    disambiguationBox.style.display = "block";
  }

  function hideDisambiguation() {
    disambiguationBox.style.display = "none";
  }

  // Error Banner UI
  function showError(msg) {
    errorMessage.textContent = msg;
    errorBanner.style.display = "flex";
  }

  function hideError() {
    errorBanner.style.display = "none";
  }

  function setLoading(isLoading) {
    btnSubmit.disabled = isLoading;
    const textSpan = btnSubmit.querySelector(".btn-text");
    const spinner = btnSubmit.querySelector(".spinner");
    if (isLoading) {
      textSpan.textContent = "Researching...";
      if (spinner) spinner.style.display = "inline-block";
    } else {
      textSpan.textContent = "Generate Briefing";
      if (spinner) spinner.style.display = "none";
    }
  }

  // Toolbar Actions
  btnCopyMd.addEventListener("click", async () => {
    if (!activeBriefingId) return;
    try {
      const res = await fetch(`/api/briefings/${activeBriefingId}/export.md`);
      const md = await res.text();
      await navigator.clipboard.writeText(md);
      btnCopyMd.textContent = "✅ Copied!";
      setTimeout(() => (btnCopyMd.textContent = "📋 Copy Markdown"), 2000);
    } catch (e) {
      alert("Failed to copy markdown to clipboard.");
    }
  });

  btnDownloadMd.addEventListener("click", () => {
    if (!activeBriefingId) return;
    window.location.href = `/api/briefings/${activeBriefingId}/export.md`;
  });

  btnPrintPdf.addEventListener("click", () => {
    window.print();
  });

  btnToggleTrace.addEventListener("click", () => {
    tracePanel.style.display = tracePanel.style.display === "none" ? "block" : "none";
  });

  btnCloseTrace.addEventListener("click", () => {
    tracePanel.style.display = "none";
  });

  // Render Research Trace
  function renderTrace(briefing) {
    let html = `
      <div style="margin-bottom: 12px; display: flex; gap: 16px; flex-wrap: wrap;">
        <span><strong>Total Latency:</strong> ${briefing.stats.duration_ms || 0} ms</span>
        <span><strong>Model:</strong> ${briefing.stats.model_used || "Bifrost"}</span>
        <span><strong>Word Count:</strong> ${briefing.stats.word_count || 0} / 520 max</span>
        <span><strong>Sources Kept:</strong> ${briefing.sources.length}</span>
      </div>
    `;

    briefing.trace.forEach((step) => {
      html += `
        <div class="trace-step-block">
          <div class="trace-step-title">
            <span>› ${step.name}</span>
            <span>${step.duration_ms} ms</span>
          </div>
          <pre style="margin-top: 4px; overflow-x: auto; color: #cbd5e1;">${JSON.stringify(step.detail, null, 2)}</pre>
        </div>
      `;
    });

    traceContent.innerHTML = html;
  }

  // Auto-parameter handlers for headless testing & screenshots
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("demo") === "1") {
    loadDemo().then(() => {
      if (urlParams.get("trace") === "1") {
        tracePanel.style.display = "block";
      }
    });
  } else if (urlParams.get("progress") === "1") {
    showStepper(4, "Gathering verified web intelligence via Tavily (topic: news)...");
  } else if (urlParams.get("disambig") === "1") {
    showDisambiguation([
      { label: "Alex Smith (Venture Partner)", hint: "Acme Ventures seed investor" },
      { label: "Alex Smith (Robotics Lead)", hint: "Beta Robotics systems engineer" }
    ]);
  }
});
