/**
 * VIGIL Video Forensics Mission Control - Interactive Application Logic
 * Full autonomous multi-agent forensic suite frontend
 */

(function () {
  "use strict";

  // Application State
  const state = {
    activeInvestigationId: null,
    investigations: [],
    status: null,
    events: [],
    observations: [],
    artifacts: [],
    assessments: [],
    auditLogs: [],
    mediaAssets: [],
    ws: null,
    activeFilter: "all",
    eventSearchQuery: "",
    selectedFile: null,
    currentMediaSource: "primary", // "primary" or artifactId
  };

  // DOM Elements
  const el = {
    invSelect: document.getElementById("invSelect"),
    refreshInvBtn: document.getElementById("refreshInvBtn"),
    loadDemoBtn: document.getElementById("loadDemoBtn"),
    caseStatusBadge: document.getElementById("caseStatusBadge"),
    wsIndicator: document.getElementById("wsIndicator"),
    wsLabel: document.getElementById("wsLabel"),
    hotkeysBtn: document.getElementById("hotkeysBtn"),
    newInvBtn: document.getElementById("newInvBtn"),
    placeholderUploadBtn: document.getElementById("placeholderUploadBtn"),
    placeholderDemoBtn: document.getElementById("placeholderDemoBtn"),
    exportMenuBtn: document.getElementById("exportMenuBtn"),
    exportMenu: document.getElementById("exportMenu"),
    exportPdfBtn: document.getElementById("exportPdfBtn"),
    exportHtmlBtn: document.getElementById("exportHtmlBtn"),
    exportMdBtn: document.getElementById("exportMdBtn"),
    finalizeReportBtn: document.getElementById("finalizeReportBtn"),
    clearTelemetryBtn: document.getElementById("clearTelemetryBtn"),
    telemetryFeed: document.getElementById("telemetryFeed"),
    telemetryCount: document.getElementById("telemetryCount"),
    metricFrames: document.getElementById("metricFrames"),
    metricObs: document.getElementById("metricObs"),
    metricEvents: document.getElementById("metricEvents"),
    metricClips: document.getElementById("metricClips"),
    mainVideoPlayer: document.getElementById("mainVideoPlayer"),
    videoPlaceholder: document.getElementById("videoPlaceholder"),
    hudCameraId: document.getElementById("hudCameraId"),
    hudFrameCounter: document.getElementById("hudFrameCounter"),
    currentTimeDisplay: document.getElementById("currentTimeDisplay"),
    durationDisplay: document.getElementById("durationDisplay"),
    seekBackBtn: document.getElementById("seekBackBtn"),
    stepBackBtn: document.getElementById("stepBackBtn"),
    playPauseBtn: document.getElementById("playPauseBtn"),
    stepFwdBtn: document.getElementById("stepFwdBtn"),
    seekFwdBtn: document.getElementById("seekFwdBtn"),
    playbackSpeedSelect: document.getElementById("playbackSpeedSelect"),
    quickClipBtn: document.getElementById("quickClipBtn"),
    sourceMetaText: document.getElementById("sourceMetaText"),
    timelineTrack: document.getElementById("timelineTrack"),
    timelineTicks: document.getElementById("timelineTicks"),
    timelineProgress: document.getElementById("timelineProgress"),
    timelineMarkersContainer: document.getElementById("timelineMarkersContainer"),
    timelineHoverTooltip: document.getElementById("timelineHoverTooltip"),
    timelineSpanLabel: document.getElementById("timelineSpanLabel"),
    mediaTabs: document.getElementById("mediaTabs"),
    clipsGalleryView: document.getElementById("clipsGalleryView"),
    clipsGrid: document.getElementById("clipsGrid"),
    clipsCount: document.getElementById("clipsCount"),
    clipsEmptyNotice: document.getElementById("clipsEmptyNotice"),
    eventSearchInput: document.getElementById("eventSearchInput"),
    eventsList: document.getElementById("eventsList"),
    countAll: document.getElementById("countAll"),
    countProposed: document.getElementById("countProposed"),
    countConfirmed: document.getElementById("countConfirmed"),
    countRejected: document.getElementById("countRejected"),
    bottomDrawer: document.getElementById("bottomDrawer"),
    drawerToggle: document.getElementById("drawerToggle"),
    drawerToggleIcon: document.getElementById("drawerToggleIcon"),
    frameGallery: document.getElementById("frameGallery"),
    framesCount: document.getElementById("framesCount"),
    obsCount: document.getElementById("obsCount"),
    assessCount: document.getElementById("assessCount"),
    observationsTable: document.getElementById("observationsTable").querySelector("tbody"),
    assessmentsTable: document.getElementById("assessmentsTable").querySelector("tbody"),
    auditTable: document.getElementById("auditTable").querySelector("tbody"),
    auditCount: document.getElementById("auditCount"),
    reportPreviewBox: document.getElementById("reportPreviewBox"),
    // Modals
    newInvModal: document.getElementById("newInvModal"),
    closeNewInvModal: document.getElementById("closeNewInvModal"),
    cancelNewInvBtn: document.getElementById("cancelNewInvBtn"),
    newInvForm: document.getElementById("newInvForm"),
    dropZone: document.getElementById("dropZone"),
    videoFileInput: document.getElementById("videoFileInput"),
    selectedFileLabel: document.getElementById("selectedFileLabel"),
    uploadSpinner: document.getElementById("uploadSpinner"),
    startInvBtn: document.getElementById("startInvBtn"),
    reviewModal: document.getElementById("reviewModal"),
    closeReviewModal: document.getElementById("closeReviewModal"),
    cancelReviewBtn: document.getElementById("cancelReviewBtn"),
    reviewForm: document.getElementById("reviewForm"),
    revEventId: document.getElementById("revEventId"),
    revReviewerInput: document.getElementById("revReviewerInput"),
    revCategoryInput: document.getElementById("revCategoryInput"),
    revStartSec: document.getElementById("revStartSec"),
    revEndSec: document.getElementById("revEndSec"),
    revDescriptionInput: document.getElementById("revDescriptionInput"),
    revNotesInput: document.getElementById("revNotesInput"),
    finalizeModal: document.getElementById("finalizeModal"),
    closeFinalizeModal: document.getElementById("closeFinalizeModal"),
    cancelFinalizeBtn: document.getElementById("cancelFinalizeBtn"),
    finalizeForm: document.getElementById("finalizeForm"),
    hotkeysModal: document.getElementById("hotkeysModal"),
    closeHotkeysModal: document.getElementById("closeHotkeysModal"),
    dismissHotkeysBtn: document.getElementById("dismissHotkeysBtn"),
    toastContainer: document.getElementById("toastContainer"),
  };

  // -------------------------------------------------------------------------
  // Notifications & Time Formatting
  // -------------------------------------------------------------------------
  function showToast(msg, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    const icon = type === "success" ? "&#x2705;" : (type === "error" ? "&#x26A0;&#xFE0F;" : "&#x2139;&#xFE0F;");
    toast.innerHTML = `<span>${icon}</span> <span>${msg}</span>`;
    el.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function formatTime(seconds) {
    if (isNaN(seconds) || seconds === null) return "00:00.00";
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(2);
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(5, "0")}`;
  }

  // -------------------------------------------------------------------------
  // API Fetch Utility
  // -------------------------------------------------------------------------
  async function apiFetch(endpoint, options = {}) {
    try {
      const res = await fetch(endpoint, options);
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errJson.detail || `Request failed with status ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      showToast(err.message, "error");
      throw err;
    }
  }

  // -------------------------------------------------------------------------
  // Investigation Lifecycle Management
  // -------------------------------------------------------------------------
  async function loadInvestigations() {
    try {
      const items = await apiFetch("/api/v1/investigations");
      state.investigations = items;
      el.invSelect.innerHTML = "";

      if (items.length === 0) {
        el.invSelect.innerHTML = `<option value="" disabled selected>No cases registered</option>`;
        updateCaseStatus("NO CASES");
        el.videoPlaceholder.classList.remove("hidden");
        return;
      }

      items.forEach((inv) => {
        const opt = document.createElement("option");
        opt.value = inv.investigation_id;
        opt.textContent = `${inv.title || inv.investigation_id} [${inv.status.toUpperCase()}]`;
        el.invSelect.appendChild(opt);
      });

      if (!state.activeInvestigationId || !items.find(i => i.investigation_id === state.activeInvestigationId)) {
        setActiveInvestigation(items[0].investigation_id);
      } else {
        el.invSelect.value = state.activeInvestigationId;
        refreshActiveCase();
      }
    } catch (err) {
      console.error("Could not load investigations:", err);
    }
  }

  function setActiveInvestigation(invId) {
    state.activeInvestigationId = invId;
    el.invSelect.value = invId;
    state.currentMediaSource = "primary";
    connectWebSocket(invId);
    refreshActiveCase();
  }

  async function loadDemoCase() {
    el.loadDemoBtn.disabled = true;
    el.loadDemoBtn.innerHTML = "<span>&#x21bb;</span> Seeding...";

    try {
      const res = await apiFetch("/api/v1/investigations/demo", { method: "POST" });
      showToast("Demo case seeded with synthetic footage, frames, audio & observations!", "success");
      await loadInvestigations();
      setActiveInvestigation(res.investigation_id);
    } catch (err) {
      showToast("Failed to load demo case: " + err.message, "error");
    } finally {
      el.loadDemoBtn.disabled = false;
      el.loadDemoBtn.innerHTML = "<span>&#x2728;</span> Demo Case";
    }
  }

  async function refreshActiveCase() {
    if (!state.activeInvestigationId) return;
    const invId = state.activeInvestigationId;

    try {
      // 1. Status
      const statusData = await apiFetch(`/api/v1/investigations/${invId}/status`);
      state.status = statusData;
      updateCaseStatus(statusData.status);

      // 2. Full investigation details
      const invData = await apiFetch(`/api/v1/investigations/${invId}`);
      if (invData.camera_id) {
        el.hudCameraId.textContent = `CAM: ${invData.camera_id.toUpperCase()}`;
      } else {
        el.hudCameraId.textContent = "CAM: PRIMARY";
      }

      // 3. Media assets
      try {
        state.mediaAssets = await apiFetch(`/api/v1/investigations/${invId}/media`);
      } catch {
        state.mediaAssets = [];
      }

      // 4. Events
      const eventsData = await apiFetch(`/api/v1/investigations/${invId}/events`);
      state.events = eventsData;
      renderEvents();
      renderTimelineMarkers();

      // 5. Observations
      try {
        state.observations = await apiFetch(`/api/v1/investigations/${invId}/observations`);
      } catch {
        state.observations = [];
      }
      renderObservations();

      // 6. Artifacts (frames, audio, clips)
      const artifactsData = await apiFetch(`/api/v1/investigations/${invId}/artifacts`);
      state.artifacts = artifactsData;
      renderArtifacts();

      // 7. Evidence assessments
      try {
        state.assessments = await apiFetch(`/api/v1/investigations/${invId}/assessments`);
      } catch {
        state.assessments = [];
      }
      renderAssessments();

      // 8. Audit logs
      const auditData = await apiFetch(`/api/v1/investigations/${invId}/audit`);
      state.auditLogs = auditData;
      renderAuditLogs();

      // 9. Video loading
      if (state.currentMediaSource === "primary") {
        loadPrimaryVideo();
      }

      // 10. Report preview
      loadReportPreview();

      // 11. Update HUD metric counters
      updateHudMetrics();

    } catch (err) {
      console.warn("Error refreshing active case:", err);
    }
  }

  function updateCaseStatus(statusStr) {
    const s = (statusStr || "UNKNOWN").toLowerCase();
    el.caseStatusBadge.textContent = s.toUpperCase();
    el.caseStatusBadge.className = `status-pill status-${s}`;
  }

  function updateHudMetrics() {
    const frames = state.artifacts.filter(a => a.media_type === "image");
    const clips = state.artifacts.filter(a => a.artifact_type in { clip: 1, subclip: 1, video_clip: 1 });

    el.metricFrames.textContent = frames.length;
    el.metricObs.textContent = state.observations.length;
    el.metricEvents.textContent = state.events.length;
    el.metricClips.textContent = clips.length;
  }

  // -------------------------------------------------------------------------
  // WebSocket Telemetry Connection
  // -------------------------------------------------------------------------
  function connectWebSocket(invId) {
    if (state.ws) {
      state.ws.close();
      state.ws = null;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/investigations/${invId}/telemetry`;

    el.wsLabel.textContent = "WS: CONNECTING...";
    el.wsIndicator.className = "ws-pill ws-disconnected";

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      el.wsLabel.textContent = "LIVE TELEMETRY: ACTIVE";
      el.wsIndicator.className = "ws-pill ws-connected";
      addTelemetryLog({ event_type: "connection", data: { message: `Telemetry link opened for case ${invId}` } });
      ws._pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
      }, 25000);
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleTelemetryMessage(payload);
      } catch (e) {
        console.error("WS Parse error", e);
      }
    };

    ws.onclose = () => {
      clearInterval(ws._pingInterval);
      el.wsLabel.textContent = "WS: DISCONNECTED";
      el.wsIndicator.className = "ws-pill ws-disconnected";
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    state.ws = ws;
  }

  function handleTelemetryMessage(msg) {
    if (msg.event_type === "pong") return;

    addTelemetryLog(msg);
    activateAgentChip(msg.event_type);

    if (
      msg.event_type === "state_changed" ||
      msg.event_type === "observation_detected" ||
      msg.event_type === "event_correlated" ||
      msg.event_type === "event_reviewed" ||
      msg.event_type === "report_finalized" ||
      msg.event_type === "investigation_completed"
    ) {
      refreshActiveCase();
    }
  }

  function activateAgentChip(msg) {
    let targetId = null;
    const evtType = typeof msg === "string" ? msg : (msg?.event_type || "");
    const data = typeof msg === "object" ? msg?.data : null;

    if (evtType === "plan_created") {
      targetId = "chip-planner";
    } else if (evtType === "task_started") {
      const taskType = data?.task_type || "";
      if (taskType === "audio_transcription") {
        targetId = "chip-audio";
      } else if (taskType === "visual_analysis" || taskType === "frame_sampling") {
        targetId = "chip-visual";
      } else if (taskType === "event_correlation") {
        targetId = "chip-temporal";
      } else if (taskType === "evidence_assessment" || taskType === "coverage_evaluation") {
        targetId = "chip-verifier";
      } else if (taskType === "report_generation") {
        targetId = "chip-reporter";
      } else {
        targetId = "chip-visual";
      }
    } else if (evtType === "observation_detected") {
      if (data?.observation?.modality === "audio") {
        targetId = "chip-audio";
      } else {
        targetId = "chip-visual";
      }
    } else if (evtType === "event_correlated") {
      targetId = "chip-temporal";
    } else if (evtType === "coverage_updated") {
      targetId = "chip-verifier";
    } else if (evtType === "report_finalized" || evtType === "investigation_completed") {
      targetId = "chip-reporter";
    }

    if (targetId) {
      const chip = document.getElementById(targetId);
      if (chip) {
        chip.classList.add("active");
        setTimeout(() => chip.classList.remove("active"), 3500);
      }
    }
  }

  function addTelemetryLog(msg) {
    if (el.telemetryFeed.querySelector(".empty-state")) {
      el.telemetryFeed.innerHTML = "";
    }

    const item = document.createElement("div");
    item.className = "telemetry-item";

    const evtType = msg.event_type || "event";
    if (evtType.includes("completed") || evtType.includes("confirmed")) item.classList.add("success");
    if (evtType.includes("error") || evtType.includes("failed") || evtType.includes("rejected")) item.classList.add("error");

    const timeStr = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    const details = msg.data ? (msg.data.message || msg.data.error || JSON.stringify(msg.data)) : "";

    item.innerHTML = `
      <div class="telemetry-meta">
        <span class="telemetry-type">${evtType.replace(/_/g, " ")}</span>
        <span>${timeStr}</span>
      </div>
      <div class="telemetry-body">${details}</div>
    `;

    el.telemetryFeed.insertBefore(item, el.telemetryFeed.firstChild);

    const total = el.telemetryFeed.children.length;
    el.telemetryCount.textContent = `${total} events`;
    if (total > 80) el.telemetryFeed.removeChild(el.telemetryFeed.lastChild);
  }

  el.clearTelemetryBtn.addEventListener("click", () => {
    el.telemetryFeed.innerHTML = '<div class="empty-state">Log cleared. Real-time telemetry will appear as agents execute.</div>';
    el.telemetryCount.textContent = "0 events";
  });

  // -------------------------------------------------------------------------
  // Video Player & Controls
  // -------------------------------------------------------------------------
  function loadPrimaryVideo() {
    state.currentMediaSource = "primary";
    const invId = state.activeInvestigationId;
    if (!invId) {
      el.videoPlaceholder.classList.remove("hidden");
      return;
    }

    const primaryUrl = `/api/v1/investigations/${invId}/media/primary/content`;
    
    // Check if player already loaded this src to prevent reloading
    if (!el.mainVideoPlayer.src.includes(primaryUrl)) {
      el.mainVideoPlayer.src = primaryUrl;
      el.mainVideoPlayer.load();
    }

    el.videoPlaceholder.classList.add("hidden");

    if (state.mediaAssets.length > 0) {
      const ma = state.mediaAssets[0];
      el.sourceMetaText.textContent = `SHA-256: ${(ma.sha256 || "verified").slice(0, 16)}... | ${ma.media_type.toUpperCase()}`;
    } else {
      el.sourceMetaText.textContent = "SHA-256: PRIMARY_FOOTAGE_STREAM";
    }
  }

  function playArtifact(artifactId) {
    state.currentMediaSource = artifactId;
    const invId = state.activeInvestigationId;
    const streamUrl = `/api/v1/investigations/${invId}/artifacts/${artifactId}/content`;

    el.mainVideoPlayer.src = streamUrl;
    el.videoPlaceholder.classList.add("hidden");
    el.mainVideoPlayer.load();
    el.mainVideoPlayer.play().catch(() => {});

    const art = state.artifacts.find(a => a.artifact_id === artifactId);
    if (art && art.sha256) {
      el.sourceMetaText.textContent = `CLIP SHA-256: ${art.sha256.slice(0, 16)}... | SUBCLIP`;
    }
    showToast(`Loaded incident clip ${artifactId}`, "info");
  }

  el.mainVideoPlayer.addEventListener("timeupdate", () => {
    const cur = el.mainVideoPlayer.currentTime;
    const dur = el.mainVideoPlayer.duration || 1;
    el.currentTimeDisplay.textContent = formatTime(cur);
    el.durationDisplay.textContent = formatTime(dur);
    el.hudFrameCounter.textContent = formatTime(cur);

    const pct = Math.min(Math.max((cur / dur) * 100, 0), 100);
    el.timelineProgress.style.width = `${pct}%`;
  });

  el.mainVideoPlayer.addEventListener("loadedmetadata", () => {
    const dur = el.mainVideoPlayer.duration;
    el.durationDisplay.textContent = formatTime(dur);
    el.timelineSpanLabel.textContent = `0s – ${dur.toFixed(1)}s`;
    renderTimelineMarkers();
  });

  el.mainVideoPlayer.addEventListener("play", () => {
    el.playPauseBtn.innerHTML = "&#x23F8; Pause";
  });

  el.mainVideoPlayer.addEventListener("pause", () => {
    el.playPauseBtn.innerHTML = "&#x25B6; Play";
  });

  el.playPauseBtn.addEventListener("click", () => {
    if (el.mainVideoPlayer.paused) {
      el.mainVideoPlayer.play().catch(e => console.warn(e));
    } else {
      el.mainVideoPlayer.pause();
    }
  });

  el.seekBackBtn.addEventListener("click", () => {
    el.mainVideoPlayer.currentTime = Math.max(0, el.mainVideoPlayer.currentTime - 2.0);
  });

  el.seekFwdBtn.addEventListener("click", () => {
    el.mainVideoPlayer.currentTime = Math.min(el.mainVideoPlayer.duration || 0, el.mainVideoPlayer.currentTime + 2.0);
  });

  el.stepBackBtn.addEventListener("click", () => {
    el.mainVideoPlayer.currentTime = Math.max(0, el.mainVideoPlayer.currentTime - 0.1);
  });

  el.stepFwdBtn.addEventListener("click", () => {
    el.mainVideoPlayer.currentTime = Math.min(el.mainVideoPlayer.duration || 0, el.mainVideoPlayer.currentTime + 0.1);
  });

  el.playbackSpeedSelect.addEventListener("change", (e) => {
    el.mainVideoPlayer.playbackRate = parseFloat(e.target.value);
  });

  el.timelineTrack.addEventListener("click", (e) => {
    const rect = el.timelineTrack.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = clickX / rect.width;
    if (el.mainVideoPlayer.duration) {
      el.mainVideoPlayer.currentTime = pct * el.mainVideoPlayer.duration;
    }
  });

  // Timeline hover tooltip
  el.timelineTrack.addEventListener("mousemove", (e) => {
    const rect = el.timelineTrack.getBoundingClientRect();
    const hoverX = e.clientX - rect.left;
    const pct = hoverX / rect.width;
    const dur = el.mainVideoPlayer.duration || 10;
    const hoverSec = pct * dur;

    el.timelineHoverTooltip.classList.remove("hidden");
    el.timelineHoverTooltip.style.left = `${hoverX}px`;
    el.timelineHoverTooltip.textContent = `${formatTime(hoverSec)} (${hoverSec.toFixed(1)}s)`;
  });

  el.timelineTrack.addEventListener("mouseleave", () => {
    el.timelineHoverTooltip.classList.add("hidden");
  });

  // Quick Cut Clip from Playhead
  el.quickClipBtn.addEventListener("click", async () => {
    const curTime = el.mainVideoPlayer.currentTime;
    const dur = el.mainVideoPlayer.duration || 10;
    const invId = state.activeInvestigationId;

    if (!invId) {
      showToast("No active case loaded.", "error");
      return;
    }

    // Check if an existing event overlaps with current playhead
    const matchingEvent = state.events.find(
      e => e.start_seconds !== null && e.end_seconds !== null && curTime >= e.start_seconds && curTime <= e.end_seconds
    );

    if (matchingEvent) {
      await sliceEventClipDirectly(matchingEvent.event_id);
    } else if (state.events.length > 0) {
      // Slice first available event or slice around playhead
      await sliceEventClipDirectly(state.events[0].event_id);
    } else {
      showToast(`Playhead at ${formatTime(curTime)}. Correlate an event to slice dedicated incident clip.`, "info");
    }
  });

  // -------------------------------------------------------------------------
  // Event Review Station & Interactive Markers (Phase 5)
  // -------------------------------------------------------------------------
  function renderTimelineMarkers() {
    el.timelineMarkersContainer.innerHTML = "";
    const duration = el.mainVideoPlayer.duration || 10.0;

    state.events.forEach((evt) => {
      if (evt.start_seconds !== null && evt.end_seconds !== null) {
        const left = Math.min((evt.start_seconds / duration) * 100, 99);
        const width = Math.max(((evt.end_seconds - evt.start_seconds) / duration) * 100, 1.8);

        const marker = document.createElement("div");
        marker.className = `timeline-marker ${evt.status}`;
        marker.style.left = `${left}%`;
        marker.style.width = `${width}%`;
        marker.title = `${evt.event_type.replace(/_/g, " ").toUpperCase()} [${evt.status.toUpperCase()}]: ${evt.start_seconds.toFixed(1)}s - ${evt.end_seconds.toFixed(1)}s`;

        marker.addEventListener("click", (e) => {
          e.stopPropagation();
          el.mainVideoPlayer.currentTime = evt.start_seconds;
        });

        el.timelineMarkersContainer.appendChild(marker);
      }
    });
  }

  function renderEvents() {
    const search = state.eventSearchQuery.toLowerCase();
    const filtered = state.events.filter((e) => {
      const matchesFilter = state.activeFilter === "all" || e.status === state.activeFilter;
      const matchesSearch = !search ||
        e.event_type.toLowerCase().includes(search) ||
        e.description.toLowerCase().includes(search) ||
        (e.reviewer && e.reviewer.toLowerCase().includes(search));
      return matchesFilter && matchesSearch;
    });

    el.countAll.textContent = state.events.length;
    el.countProposed.textContent = state.events.filter(e => e.status === "proposed" || e.status === "under_review").length;
    el.countConfirmed.textContent = state.events.filter(e => e.status === "confirmed").length;
    el.countRejected.textContent = state.events.filter(e => e.status === "rejected").length;

    el.eventsList.innerHTML = "";
    if (filtered.length === 0) {
      el.eventsList.innerHTML = `<div class="empty-state">No ${state.activeFilter} events recorded.</div>`;
      return;
    }

    filtered.forEach((evt) => {
      const card = document.createElement("div");
      card.className = `event-card ${evt.status}`;

      const timeRange = (evt.start_seconds !== null && evt.end_seconds !== null)
        ? `${evt.start_seconds.toFixed(1)}s &ndash; ${evt.end_seconds.toFixed(1)}s`
        : "-";

      let reviewNotesHtml = "";
      if (evt.reviewer || evt.review_notes) {
        reviewNotesHtml = `
          <div class="event-review-notes">
            <strong>${evt.reviewer || "Investigator"}:</strong> ${evt.review_notes || "Verified by forensic analyst"}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="event-card-head">
          <span class="event-card-type">${evt.event_type.replace(/_/g, " ").toUpperCase()}</span>
          <span class="status-pill status-${evt.status}">${evt.status}</span>
        </div>
        <div class="event-card-id">#${evt.event_id} &bull; Interval: <strong>${timeRange}</strong></div>
        <div class="event-card-desc">${evt.description}</div>
        ${reviewNotesHtml}
        <div class="event-card-actions">
          <button class="btn btn-sm btn-confirm" data-id="${evt.event_id}" title="Confirm Verified Event">&#x2714; Confirm</button>
          <button class="btn btn-sm btn-reject" data-id="${evt.event_id}" title="Dismiss as False Positive">&#x2716; Reject</button>
          <button class="btn btn-sm btn-edit" data-id="${evt.event_id}" title="Edit Interval or Add Rationale Notes">&#x270E; Edit</button>
          <button class="btn btn-sm btn-outline btn-seek" data-time="${evt.start_seconds || 0}" title="Seek Player to Start">&#x25B6; Seek</button>
          <button class="btn btn-sm btn-clip" data-id="${evt.event_id}" title="Slice H.264 video sub-clip">&#x2702; Cut Clip</button>
        </div>
      `;

      // Button handlers
      card.querySelector(".btn-confirm").addEventListener("click", () => openReviewModal(evt, "confirmed"));
      card.querySelector(".btn-reject").addEventListener("click", () => openReviewModal(evt, "rejected"));
      card.querySelector(".btn-edit").addEventListener("click", () => openReviewModal(evt, evt.status));
      card.querySelector(".btn-seek").addEventListener("click", () => {
        if (evt.start_seconds !== null) el.mainVideoPlayer.currentTime = evt.start_seconds;
      });
      card.querySelector(".btn-clip").addEventListener("click", () => sliceEventClipDirectly(evt.event_id));

      el.eventsList.appendChild(card);
    });
  }

  async function sliceEventClipDirectly(eventId) {
    const invId = state.activeInvestigationId;
    if (!invId) return;

    showToast(`Cutting incident sub-clip for event #${eventId}...`, "info");
    try {
      const artifact = await apiFetch(`/api/v1/investigations/${invId}/events/${eventId}/clip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ padding_seconds: 1.0 }),
      });

      showToast(`Incident clip ${artifact.artifact_id} sliced successfully!`, "success");
      await refreshActiveCase();
      // Switch to clips tab
      const clipTab = el.mediaTabs.querySelector('[data-tab="clips"]');
      if (clipTab) clipTab.click();
    } catch (err) {
      console.error(err);
    }
  }

  // Filter Pills & Search
  document.querySelectorAll(".filter-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.getAttribute("data-filter");
      renderEvents();
    });
  });

  el.eventSearchInput.addEventListener("input", (e) => {
    state.eventSearchQuery = e.target.value.trim();
    renderEvents();
  });

  // -------------------------------------------------------------------------
  // Review Modal Handling
  // -------------------------------------------------------------------------
  function openReviewModal(evt, targetStatus) {
    el.revEventId.value = evt.event_id;
    el.revCategoryInput.value = evt.event_type || "";
    el.revStartSec.value = evt.start_seconds !== null ? evt.start_seconds : "";
    el.revEndSec.value = evt.end_seconds !== null ? evt.end_seconds : "";
    el.revDescriptionInput.value = evt.description || "";
    el.revNotesInput.value = evt.review_notes || "";
    el.revReviewerInput.value = evt.reviewer || "Investigator";

    const radio = el.reviewForm.querySelector(`input[name="revStatus"][value="${targetStatus}"]`);
    if (radio) radio.checked = true;

    el.reviewModal.classList.remove("hidden");
  }

  el.closeReviewModal.addEventListener("click", () => el.reviewModal.classList.add("hidden"));
  el.cancelReviewBtn.addEventListener("click", () => el.reviewModal.classList.add("hidden"));

  el.reviewForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const eventId = el.revEventId.value;
    const invId = state.activeInvestigationId;
    const statusVal = el.reviewForm.querySelector('input[name="revStatus"]:checked').value;

    const payload = {
      status: statusVal,
      reviewer: el.revReviewerInput.value.trim(),
      notes: el.revNotesInput.value.trim(),
      description: el.revDescriptionInput.value.trim(),
      event_type: el.revCategoryInput.value.trim(),
      start_seconds: el.revStartSec.value ? parseFloat(el.revStartSec.value) : null,
      end_seconds: el.revEndSec.value ? parseFloat(el.revEndSec.value) : null,
    };

    try {
      await apiFetch(`/api/v1/investigations/${invId}/events/${eventId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      showToast(`Event #${eventId} marked as ${statusVal.toUpperCase()}`, "success");
      el.reviewModal.classList.add("hidden");
      refreshActiveCase();
    } catch (err) {
      console.error(err);
    }
  });

  // -------------------------------------------------------------------------
  // Artifacts & Incident Sub-clips
  // -------------------------------------------------------------------------
  function renderArtifacts() {
    const frames = state.artifacts.filter(a => a.media_type === "image");
    const audioArtifacts = state.artifacts.filter(a => a.media_type === "audio");
    const clips = state.artifacts.filter(a => a.artifact_type in { clip: 1, subclip: 1, video_clip: 1 });

    el.framesCount.textContent = frames.length;
    el.clipsCount.textContent = clips.length;

    // Render Audio Trail & Frames
    el.frameGallery.innerHTML = "";

    // Display Audio Trail if extracted
    if (audioArtifacts.length > 0) {
      audioArtifacts.forEach((aud) => {
        const audioBox = document.createElement("div");
        audioBox.className = "audio-artifact-banner";
        audioBox.style.cssText = "width:100%; display:flex; align-items:center; gap:12px; background:rgba(192, 132, 252, 0.12); border:1px solid rgba(192, 132, 252, 0.35); padding:10px 16px; border-radius:8px; margin-bottom:12px;";
        const dur = aud.source_reference?.end_seconds ? `${aud.source_reference.end_seconds.toFixed(1)}s` : "Extracted";
        audioBox.innerHTML = `
          <span style="font-size:1.5rem;">&#x1F3A7;</span>
          <div style="flex:1;">
            <div style="font-weight:600; color:#c084fc; font-size:0.85rem; letter-spacing:0.5px;">AUDIO TRAIL &bull; ${aud.artifact_id}</div>
            <div style="font-size:0.75rem; color:var(--text-dim); margin-top:2px;">Demuxed 16-bit PCM Audio Track (${dur}) &bull; Forensic Acoustic Stream</div>
          </div>
          <audio controls preload="metadata" style="height:32px; outline:none;" src="/api/v1/investigations/${state.activeInvestigationId}/artifacts/${aud.artifact_id}/content"></audio>
        `;
        el.frameGallery.appendChild(audioBox);
      });
    }

    if (frames.length === 0 && audioArtifacts.length === 0) {
      el.frameGallery.innerHTML = `<div class="gallery-empty">No frames or audio extracted yet.</div>`;
    } else {
      frames.forEach((f) => {
        const card = document.createElement("div");
        card.className = "frame-card";
        const startSec = f.source_reference?.start_seconds;
        const timecodeStr = startSec !== null && startSec !== undefined ? formatTime(startSec) : "--:--";

        card.innerHTML = `
          <img class="frame-thumb" src="/api/v1/investigations/${state.activeInvestigationId}/artifacts/${f.artifact_id}/content" alt="Frame" loading="lazy">
          <div class="frame-card-footer">
            <span>#${f.artifact_id.slice(-6)}</span>
            <span>${timecodeStr}</span>
          </div>
        `;
        card.addEventListener("click", () => {
          if (startSec !== null && startSec !== undefined) {
            el.mainVideoPlayer.currentTime = startSec;
          }
        });
        el.frameGallery.appendChild(card);
      });
    }

    // Render Clips Grid
    el.clipsGrid.innerHTML = "";
    if (clips.length === 0) {
      el.clipsEmptyNotice.classList.remove("hidden");
    } else {
      el.clipsEmptyNotice.classList.add("hidden");
      clips.forEach((c) => {
        const card = document.createElement("div");
        card.className = "clip-card";
        const sr = c.source_reference;
        const intervalStr = sr ? `${sr.start_seconds?.toFixed(1)}s &ndash; ${sr.end_seconds?.toFixed(1)}s` : "-";
        
        card.innerHTML = `
          <div class="clip-card-title">&#x1F3AC; ${c.artifact_id}</div>
          <div class="clip-card-meta">Interval: <strong>${intervalStr}</strong></div>
          <div class="clip-card-meta">SHA-256: <code>${(c.sha256 || "verified").slice(0, 12)}...</code></div>
          <div style="margin-top: 6px;">
            <button class="btn btn-sm btn-outline" style="width:100%;">&#x25B6; Play Sub-clip</button>
          </div>
        `;
        card.addEventListener("click", () => playArtifact(c.artifact_id));
        el.clipsGrid.appendChild(card);
      });
    }
  }

  // Media Tab switching
  el.mediaTabs.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      el.mediaTabs.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const tab = btn.getAttribute("data-tab");
      if (tab === "clips") {
        el.clipsGalleryView.classList.remove("hidden");
      } else {
        el.clipsGalleryView.classList.add("hidden");
        loadPrimaryVideo();
      }
    });
  });

  // -------------------------------------------------------------------------
  // Observations Drawer Table
  // -------------------------------------------------------------------------
  function renderObservations() {
    el.obsCount.textContent = state.observations.length;
    el.observationsTable.innerHTML = "";

    if (state.observations.length === 0) {
      el.observationsTable.innerHTML = `<tr><td colspan="7" style="text-align:center;">No observations recorded.</td></tr>`;
      return;
    }

    state.observations.forEach((obs) => {
      const row = document.createElement("tr");
      const sr = obs.source_references && obs.source_references.length > 0 ? obs.source_references[0] : null;
      const intervalStr = sr ? `${sr.start_seconds?.toFixed(1)}s &ndash; ${sr.end_seconds?.toFixed(1)}s` : "-";
      
      const confPct = obs.confidence !== null ? Math.round(obs.confidence * 100) : 85;
      const confHtml = `
        <div class="confidence-bar-wrap">
          <div class="confidence-bar">
            <div class="confidence-fill" style="width: ${confPct}%;"></div>
          </div>
          <span>${confPct}%</span>
        </div>
      `;

      const modClass = `modality-${obs.modality}`;
      const provName = obs.provenance ? `${obs.provenance.producer_name}` : "-";

      row.innerHTML = `
        <td><code>${obs.observation_id}</code></td>
        <td><span class="modality-badge ${modClass}">${obs.modality}</span></td>
        <td><strong>${obs.observation_type.replace(/_/g, " ")}</strong></td>
        <td>${intervalStr}</td>
        <td>${confHtml}</td>
        <td>${obs.description}</td>
        <td><small style="color:var(--text-dim);">${provName}</small></td>
      `;

      // Clicking an observation seeks to start time
      row.style.cursor = "pointer";
      row.addEventListener("click", () => {
        if (sr && sr.start_seconds !== null) {
          el.mainVideoPlayer.currentTime = sr.start_seconds;
        }
      });

      el.observationsTable.appendChild(row);
    });
  }

  // -------------------------------------------------------------------------
  // Evidence Assessments Drawer Table
  // -------------------------------------------------------------------------
  function renderAssessments() {
    el.assessCount.textContent = state.assessments.length;
    el.assessmentsTable.innerHTML = "";

    if (state.assessments.length === 0) {
      el.assessmentsTable.innerHTML = `<tr><td colspan="6" style="text-align:center;">No evidence assessments available.</td></tr>`;
      return;
    }

    state.assessments.forEach((as) => {
      const row = document.createElement("tr");
      const ratingClass = `rating-${as.rating}`;

      row.innerHTML = `
        <td><code>${as.target_id}</code></td>
        <td><span class="badge">${as.target_type}</span></td>
        <td><strong>${as.assessment_type.replace(/_/g, " ").toUpperCase()}</strong></td>
        <td><span class="rating-badge ${ratingClass}">${as.rating}</span></td>
        <td>${as.rationale}</td>
        <td><small style="color:var(--text-dim);">${as.assessed_by}</small></td>
      `;
      el.assessmentsTable.appendChild(row);
    });
  }

  // -------------------------------------------------------------------------
  // Audit Trail Drawer Table
  // -------------------------------------------------------------------------
  function renderAuditLogs() {
    el.auditCount.textContent = state.auditLogs.length;
    el.auditTable.innerHTML = "";

    if (state.auditLogs.length === 0) {
      el.auditTable.innerHTML = `<tr><td colspan="6" style="text-align:center;">No audit actions logged yet.</td></tr>`;
      return;
    }

    state.auditLogs.forEach((log) => {
      const row = document.createElement("tr");
      const timeStr = new Date(log.timestamp).toLocaleString();
      const changesStr = log.changes
        ? Object.entries(log.changes).map(([k, v]) => `${k}: ${v.old} &rarr; ${v.new}`).join(", ")
        : "-";

      row.innerHTML = `
        <td>${timeStr}</td>
        <td><strong>${log.actor}</strong></td>
        <td><code>${log.action}</code></td>
        <td>${log.target_id}</td>
        <td>${changesStr}</td>
        <td>${log.notes || "-"}</td>
      `;
      el.auditTable.appendChild(row);
    });
  }

  // -------------------------------------------------------------------------
  // Drawer Toggle & Tabs
  // -------------------------------------------------------------------------
  el.drawerToggle.addEventListener("click", () => {
    el.bottomDrawer.classList.toggle("expanded");
    el.drawerToggleIcon.innerHTML = el.bottomDrawer.classList.contains("expanded") ? "&#x25BC;" : "&#x25B2;";
  });

  document.querySelectorAll(".drawer-tab").forEach((tab) => {
    tab.addEventListener("click", (e) => {
      e.stopPropagation();
      document.querySelectorAll(".drawer-tab").forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".drawer-tab-pane").forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.getAttribute("data-target");
      document.getElementById(target).classList.add("active");
      if (!el.bottomDrawer.classList.contains("expanded")) {
        el.bottomDrawer.classList.add("expanded");
        el.drawerToggleIcon.innerHTML = "&#x25BC;";
      }
    });
  });

  // -------------------------------------------------------------------------
  // Report Preview & Finalization
  // -------------------------------------------------------------------------
  async function loadReportPreview() {
    try {
      const report = await apiFetch(`/api/v1/investigations/${state.activeInvestigationId}/report`);
      el.reportPreviewBox.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h4 style="color:#93c5fd; margin:0;">${report.title}</h4>
          <span class="status-pill status-${report.status}">v${report.version} &bull; ${report.status.toUpperCase()}</span>
        </div>
        <p style="margin-bottom: 12px; color:#e2e8f0; white-space:pre-line; line-height:1.5;">${report.summary}</p>
        <div style="display:flex; gap:10px; align-items:center; font-size:0.75rem; color:#94a3b8; border-top: 1px solid var(--border-color); padding-top: 8px;">
          <span>Generated by: <strong>${report.generated_by}</strong></span>
          <span>&bull;</span>
          <span>Finalized by: <strong>${report.finalized_by || "Pending Sign-off"}</strong></span>
          <div style="margin-left:auto; display:flex; gap:6px;">
            <button class="btn btn-sm btn-outline" id="quickExportPdfBtn">&#x1F4C4; PDF</button>
            <button class="btn btn-sm btn-outline" id="quickExportHtmlBtn">&#x1F310; HTML</button>
          </div>
        </div>
      `;

      document.getElementById("quickExportPdfBtn")?.addEventListener("click", () => {
        window.open(`/api/v1/investigations/${state.activeInvestigationId}/export/pdf`, "_blank");
      });
      document.getElementById("quickExportHtmlBtn")?.addEventListener("click", () => {
        window.open(`/api/v1/investigations/${state.activeInvestigationId}/export/html`, "_blank");
      });
    } catch {
      el.reportPreviewBox.innerHTML = `<div class="gallery-empty">Investigation still in progress or no report generated yet.</div>`;
    }
  }

  // Export Menu
  el.exportMenuBtn.addEventListener("click", () => el.exportMenu.classList.toggle("hidden"));
  document.addEventListener("click", (e) => {
    if (!el.exportMenuBtn.contains(e.target) && !el.exportMenu.contains(e.target)) {
      el.exportMenu.classList.add("hidden");
    }
  });

  el.exportPdfBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    window.open(`/api/v1/investigations/${state.activeInvestigationId}/export/pdf`, "_blank");
  });

  el.exportHtmlBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    window.open(`/api/v1/investigations/${state.activeInvestigationId}/export/html`, "_blank");
  });

  el.exportMdBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    window.open(`/api/v1/investigations/${state.activeInvestigationId}/report?format=markdown`, "_blank");
  });

  el.finalizeReportBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    el.finalizeModal.classList.remove("hidden");
  });

  el.closeFinalizeModal.addEventListener("click", () => el.finalizeModal.classList.add("hidden"));
  el.cancelFinalizeBtn.addEventListener("click", () => el.finalizeModal.classList.add("hidden"));

  el.finalizeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const invId = state.activeInvestigationId;
    const payload = {
      finalized_by: document.getElementById("finInvestigatorInput").value.trim(),
      title: document.getElementById("finTitleInput").value.trim() || undefined,
      notes: document.getElementById("finNotesInput").value.trim() || undefined,
      auto_slice_clips: document.getElementById("finAutoClips").checked,
    };

    try {
      const res = await apiFetch(`/api/v1/investigations/${invId}/report/finalize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      showToast(`Report finalized as version ${res.version}! Sliced ${res.clip_count} clips.`, "success");
      el.finalizeModal.classList.add("hidden");
      refreshActiveCase();
    } catch (err) {
      console.error(err);
    }
  });

  // -------------------------------------------------------------------------
  // New Investigation Modal & Upload
  // -------------------------------------------------------------------------
  function openNewInvModal() {
    el.newInvModal.classList.remove("hidden");
  }

  el.newInvBtn.addEventListener("click", openNewInvModal);
  el.placeholderUploadBtn.addEventListener("click", openNewInvModal);
  el.closeNewInvModal.addEventListener("click", () => el.newInvModal.classList.add("hidden"));
  el.cancelNewInvBtn.addEventListener("click", () => el.newInvModal.classList.add("hidden"));

  // Drag and Drop
  el.dropZone.addEventListener("click", () => el.videoFileInput.click());
  el.dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    el.dropZone.classList.add("dragover");
  });
  el.dropZone.addEventListener("dragleave", () => el.dropZone.classList.remove("dragover"));
  el.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    el.dropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleSelectedFile(e.dataTransfer.files[0]);
    }
  });
  el.videoFileInput.addEventListener("change", () => {
    if (el.videoFileInput.files && el.videoFileInput.files[0]) {
      handleSelectedFile(el.videoFileInput.files[0]);
    }
  });

  function handleSelectedFile(file) {
    state.selectedFile = file;
    el.selectedFileLabel.textContent = `Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
    el.selectedFileLabel.classList.remove("hidden");
  }

  el.newInvForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.selectedFile) {
      showToast("Please select a video footage file.", "error");
      return;
    }

    const formData = new FormData();
    formData.append("file", state.selectedFile);
    formData.append("title", document.getElementById("invTitleInput").value.trim() || `Investigation: ${state.selectedFile.name}`);
    formData.append("camera_id", document.getElementById("invCameraInput").value.trim() || "cam-main");
    formData.append("objective", document.getElementById("invObjectiveInput").value.trim() || "Perform complete multi-modal video and acoustic investigation.");
    formData.append("sample_interval_seconds", document.getElementById("invSampleInterval").value);
    formData.append("max_frames", document.getElementById("invMaxFrames").value);
    formData.append("extract_audio", document.getElementById("invExtractAudio").value);
    formData.append("run_async", "true");

    el.startInvBtn.disabled = true;
    el.uploadSpinner.classList.remove("hidden");

    try {
      const res = await fetch("/api/v1/investigations", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errJson.detail || "Upload failed");
      }

      const inv = await res.json();
      showToast(`Investigation ${inv.investigation_id} created and running!`, "success");
      el.newInvModal.classList.add("hidden");
      el.newInvForm.reset();
      state.selectedFile = null;
      el.selectedFileLabel.classList.add("hidden");

      await loadInvestigations();
      setActiveInvestigation(inv.investigation_id);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      el.startInvBtn.disabled = false;
      el.uploadSpinner.classList.add("hidden");
    }
  });

  // Demo Case Buttons
  el.loadDemoBtn.addEventListener("click", loadDemoCase);
  el.placeholderDemoBtn.addEventListener("click", loadDemoCase);

  // -------------------------------------------------------------------------
  // Keyboard Shortcuts & Modals
  // -------------------------------------------------------------------------
  function openHotkeysModal() {
    el.hotkeysModal.classList.remove("hidden");
  }

  el.hotkeysBtn.addEventListener("click", openHotkeysModal);
  el.closeHotkeysModal.addEventListener("click", () => el.hotkeysModal.classList.add("hidden"));
  el.dismissHotkeysBtn.addEventListener("click", () => el.hotkeysModal.classList.add("hidden"));

  document.addEventListener("keydown", (e) => {
    // Avoid interfering with form input fields
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) {
      if (e.key === "Escape") document.activeElement.blur();
      return;
    }

    switch (e.key) {
      case " ":
        e.preventDefault();
        el.playPauseBtn.click();
        break;
      case "ArrowLeft":
        e.preventDefault();
        el.seekBackBtn.click();
        break;
      case "ArrowRight":
        e.preventDefault();
        el.seekFwdBtn.click();
        break;
      case "j":
      case "J":
        el.stepBackBtn.click();
        break;
      case "l":
      case "L":
        el.stepFwdBtn.click();
        break;
      case "x":
      case "X":
        el.quickClipBtn.click();
        break;
      case "f":
      case "F":
        if (!document.fullscreenElement) {
          el.mainVideoPlayer.requestFullscreen?.().catch(() => {});
        } else {
          document.exitFullscreen?.().catch(() => {});
        }
        break;
      case "d":
      case "D":
        loadDemoCase();
        break;
      case "n":
      case "N":
        openNewInvModal();
        break;
      case "e":
      case "E":
        el.exportMenu.classList.toggle("hidden");
        break;
      case "?":
        openHotkeysModal();
        break;
      case "Escape":
        document.querySelectorAll(".modal-backdrop").forEach(m => m.classList.add("hidden"));
        el.exportMenu.classList.add("hidden");
        break;
    }
  });

  el.invSelect.addEventListener("change", (e) => setActiveInvestigation(e.target.value));
  el.refreshInvBtn.addEventListener("click", () => {
    loadInvestigations();
    showToast("Case catalog refreshed", "info");
  });

  // Initial Load
  loadInvestigations();
})();
