/**
 * VIGIL Video Forensics Mission Control - Interactive Application Logic
 * Full autonomous multi-agent forensic suite frontend
 * Enhanced with:
 * - Premium Animated Landing Page Routing
 * - Session State Isolation & Cleanup (No stale footage across sessions)
 * - Readable Live Event Feed in Agent Mission Control
 * - Real-time Human Review Station (Confirmed/rejected events leave pending queue)
 * - Multi-Video Premise Correlation & Cross-Camera Timeline Switching
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
    activeFilter: "proposed", // Default to pending review queue
    eventSearchQuery: "",
    selectedFiles: [],
    selectedFeeds: [],
    currentMediaAssetId: null,
    currentMediaSource: "video", // "video" or "artifact"
    seenTelemetryKeys: new Set(),
    createdObjectUrls: [],
    notifiedReports: { ready: new Set(), failed: new Set(), empty: new Set() },
    pollTimer: null,
  };

  // DOM Elements
  const el = {
    // Top Views
    landingPage: document.getElementById("landingPage"),
    dashboardApp: document.getElementById("dashboardApp"),
    enterWorkspaceBtn: document.getElementById("enterWorkspaceBtn"),
    landingDemoBtn: document.getElementById("landingDemoBtn"),
    brandLogoBtn: document.getElementById("brandLogoBtn"),

    // Navbar
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

    // Telemetry Mission Control
    clearTelemetryBtn: document.getElementById("clearTelemetryBtn"),
    telemetryFeed: document.getElementById("telemetryFeed"),
    telemetryCount: document.getElementById("telemetryCount"),
    metricFrames: document.getElementById("metricFrames"),
    metricObs: document.getElementById("metricObs"),
    metricEvents: document.getElementById("metricEvents"),
    metricClips: document.getElementById("metricClips"),

    // Video Player & Controls
    mainVideoPlayer: document.getElementById("mainVideoPlayer"),
    videoPlaceholder: document.getElementById("videoPlaceholder"),
    videoContainer: document.getElementById("videoContainer"),
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
    cameraFeedSelect: document.getElementById("cameraFeedSelect"),
    cameraFeedPickerWrap: document.getElementById("cameraFeedPickerWrap"),

    // Timeline
    timelineTrack: document.getElementById("timelineTrack"),
    timelineTicks: document.getElementById("timelineTicks"),
    timelineProgress: document.getElementById("timelineProgress"),
    timelineMarkersContainer: document.getElementById("timelineMarkersContainer"),
    timelineHoverTooltip: document.getElementById("timelineHoverTooltip"),
    timelineSpanLabel: document.getElementById("timelineSpanLabel"),

    // Media Tabs & Clips
    mediaTabs: document.getElementById("mediaTabs"),
    clipsGalleryView: document.getElementById("clipsGalleryView"),
    clipsGrid: document.getElementById("clipsGrid"),
    clipsCount: document.getElementById("clipsCount"),
    clipsEmptyNotice: document.getElementById("clipsEmptyNotice"),

    // Human Review Station
    eventSearchInput: document.getElementById("eventSearchInput"),
    eventsList: document.getElementById("eventsList"),
    countAll: document.getElementById("countAll"),
    countProposed: document.getElementById("countProposed"),
    countConfirmed: document.getElementById("countConfirmed"),
    countRejected: document.getElementById("countRejected"),

    // Bottom Drawer
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
    browseVideosBtn: document.getElementById("browseVideosBtn"),
    addMoreVideosBtn: document.getElementById("addMoreVideosBtn"),
    clearAllVideosBtn: document.getElementById("clearAllVideosBtn"),
    selectedFeedsQueue: document.getElementById("selectedFeedsQueue"),
    selectedFeedsList: document.getElementById("selectedFeedsList"),
    selectedFeedCount: document.getElementById("selectedFeedCount"),
    invTitleInput: document.getElementById("invTitleInput"),
    invCameraInput: document.getElementById("invCameraInput"),
    invObjectiveInput: document.getElementById("invObjectiveInput"),
    invSampleInterval: document.getElementById("invSampleInterval"),
    invMaxFrames: document.getElementById("invMaxFrames"),
    invExtractAudio: document.getElementById("invExtractAudio"),
    uploadSpinner: document.getElementById("uploadSpinner"),
    startInvBtn: document.getElementById("startInvBtn"),

    // Add feed modal
    openAddFeedModalBtn: document.getElementById("openAddFeedModalBtn"),
    addFeedModal: document.getElementById("addFeedModal"),
    closeAddFeedModal: document.getElementById("closeAddFeedModal"),
    cancelAddFeedBtn: document.getElementById("cancelAddFeedBtn"),
    addFeedForm: document.getElementById("addFeedForm"),
    addFeedFileInput: document.getElementById("addFeedFileInput"),
    addFeedDropZone: document.getElementById("addFeedDropZone"),
    browseSingleFeedBtn: document.getElementById("browseSingleFeedBtn"),
    addFeedSelectedLabel: document.getElementById("addFeedSelectedLabel"),
    addFeedCameraId: document.getElementById("addFeedCameraId"),
    addFeedCameraName: document.getElementById("addFeedCameraName"),
    submitAddFeedBtn: document.getElementById("submitAddFeedBtn"),
    addFeedSpinner: document.getElementById("addFeedSpinner"),

    // Review Modal
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
    saveReviewBtn: document.getElementById("saveReviewBtn"),

    // Finalize Modal
    finalizeModal: document.getElementById("finalizeModal"),
    closeFinalizeModal: document.getElementById("closeFinalizeModal"),
    cancelFinalizeBtn: document.getElementById("cancelFinalizeBtn"),
    finalizeForm: document.getElementById("finalizeForm"),
    submitFinalizeBtn: document.getElementById("submitFinalizeBtn"),

    // Hotkeys Modal
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
    const icon = type === "success" ? "\u2705" : (type === "error" ? "\u26A0\uFE0F" : "\u2139\uFE0F");
    toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(msg)}</span>`;
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

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // -------------------------------------------------------------------------
  // API Fetch Utility
  // -------------------------------------------------------------------------
  async function apiFetch(endpoint, options = {}) {
    const silent = Boolean(options && options.silent);
    const fetchOptions = { ...options };
    delete fetchOptions.silent;
    try {
      const res = await fetch(endpoint, fetchOptions);
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errJson.detail || `Request failed with status ${res.status}`);
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      if (!silent) {
        showToast(err.message, "error");
      }
      throw err;
    }
  }

  // -------------------------------------------------------------------------
  // View Routing: Landing Page vs. Forensic Workspace (Requirement C)
  // -------------------------------------------------------------------------
  function showLandingPage() {
    if (el.landingPage) el.landingPage.classList.remove("hidden");
    if (el.dashboardApp) el.dashboardApp.classList.add("hidden");
  }

  function showDashboard() {
    if (el.landingPage) el.landingPage.classList.add("hidden");
    if (el.dashboardApp) el.dashboardApp.classList.remove("hidden");
  }

  function navigateToWorkspace(invId = null) {
    showDashboard();
    if (invId) {
      window.location.hash = `case=${encodeURIComponent(invId)}`;
      setActiveInvestigation(invId);
    } else if (state.activeInvestigationId) {
      window.location.hash = `case=${encodeURIComponent(state.activeInvestigationId)}`;
    } else {
      window.location.hash = "workspace";
    }
  }

  if (el.enterWorkspaceBtn) {
    el.enterWorkspaceBtn.addEventListener("click", () => {
      navigateToWorkspace(state.activeInvestigationId || null);
    });
  }

  if (el.landingDemoBtn) {
    el.landingDemoBtn.addEventListener("click", () => {
      showDashboard();
      window.location.hash = "workspace";
      loadDemoCase();
    });
  }

  if (el.brandLogoBtn) {
    el.brandLogoBtn.addEventListener("click", () => {
      showLandingPage();
      window.location.hash = "landing";
    });
  }

  function handleRoute() {
    const hash = window.location.hash;
    const urlParams = new URLSearchParams(window.location.search);
    const invFromQuery = urlParams.get("inv") || urlParams.get("case");

    if (hash.startsWith("#case=")) {
      const caseId = decodeURIComponent(hash.substring(6));
      showDashboard();
      loadInvestigations(caseId);
    } else if (invFromQuery) {
      showDashboard();
      loadInvestigations(invFromQuery);
    } else if (hash === "#workspace" || hash === "#dashboard") {
      showDashboard();
      loadInvestigations(state.activeInvestigationId || null);
    } else {
      // Default initial session: Show landing page!
      showLandingPage();
      // Preload cases list so dropdown is ready when entering workspace,
      // but do NOT auto-select the first investigation to avoid stale session data!
      loadInvestigations(null, false);
    }
  }

  window.addEventListener("popstate", handleRoute);

  // -------------------------------------------------------------------------
  // Investigation Lifecycle & Session State Isolation (Requirement B)
  // -------------------------------------------------------------------------
  function resetWorkspace(clearDropdown = false) {
    // 1. Revoke any browser-created object URLs
    if (state.createdObjectUrls && state.createdObjectUrls.length > 0) {
      state.createdObjectUrls.forEach(url => {
        try { URL.revokeObjectURL(url); } catch (e) { /* ignore */ }
      });
      state.createdObjectUrls = [];
    }

    // 2. Disconnect WebSocket
    if (state.ws) {
      state.ws.onclose = null;
      state.ws.close();
      state.ws = null;
    }
    el.wsLabel.textContent = "WS: DISCONNECTED";
    el.wsIndicator.className = "ws-pill ws-disconnected";

    // 3. Reset Video Player & HUD
    try {
      el.mainVideoPlayer.pause();
      el.mainVideoPlayer.removeAttribute("src");
      el.mainVideoPlayer.load();
    } catch (e) { /* ignore */ }

    el.videoPlaceholder.classList.remove("hidden");
    el.hudCameraId.textContent = "CAM: -";
    el.hudFrameCounter.textContent = "00:00.00";
    el.currentTimeDisplay.textContent = "00:00.00";
    el.durationDisplay.textContent = "00:00.00";
    el.timelineProgress.style.width = "0%";
    el.timelineSpanLabel.textContent = "0s \u2013 0s";
    el.timelineMarkersContainer.innerHTML = "";
    el.sourceMetaText.textContent = "SHA-256: -";

    // 4. Reset Lists & Tables
    state.events = [];
    state.observations = [];
    state.artifacts = [];
    state.assessments = [];
    state.auditLogs = [];
    state.mediaAssets = [];
    state.seenTelemetryKeys.clear();

    renderEvents();
    renderObservations();
    renderAssessments();
    renderAuditLogs();
    renderArtifacts();

    // Reset report preview
    el.reportPreviewBox.innerHTML = `<div class="gallery-empty">Select or load an investigation to view findings.</div>`;

    // Reset metrics HUD
    el.metricFrames.textContent = "0";
    el.metricObs.textContent = "0";
    el.metricEvents.textContent = "0";
    el.metricClips.textContent = "0";

    // Reset telemetry log
    el.telemetryFeed.innerHTML = `<div class="empty-state">Select an active investigation, ingest footage, or click "Demo Case" to monitor live forensic agents.</div>`;
    el.telemetryCount.textContent = "0 events";

    // Reset camera feed picker
    if (el.cameraFeedSelect) {
      el.cameraFeedSelect.innerHTML = `<option value="primary">Primary Camera</option>`;
    }

    if (clearDropdown) {
      el.invSelect.value = "";
      updateCaseStatus("NO CASE LOADED");
      state.activeInvestigationId = null;
    }
  }

  async function loadInvestigations(targetInvId = null, autoSelect = true) {
    try {
      const items = await apiFetch("/api/v1/investigations");
      state.investigations = items;
      el.invSelect.innerHTML = "";

      if (items.length === 0) {
        el.invSelect.innerHTML = `<option value="" disabled selected>No cases registered</option>`;
        updateCaseStatus("NO CASES");
        resetWorkspace(true);
        return;
      }

      // Default option when no case is selected
      const defaultOpt = document.createElement("option");
      defaultOpt.value = "";
      defaultOpt.textContent = "-- Select an Investigation --";
      el.invSelect.appendChild(defaultOpt);

      items.forEach((inv) => {
        const opt = document.createElement("option");
        opt.value = inv.investigation_id;
        opt.textContent = `${inv.title || inv.investigation_id} [${inv.status.toUpperCase()}]`;
        el.invSelect.appendChild(opt);
      });

      // If a specific target ID was requested or already active
      if (targetInvId && items.some(i => i.investigation_id === targetInvId)) {
        setActiveInvestigation(targetInvId);
      } else if (state.activeInvestigationId && items.some(i => i.investigation_id === state.activeInvestigationId)) {
        setActiveInvestigation(state.activeInvestigationId);
      } else if (autoSelect && window.location.hash.startsWith("#case=")) {
        const idFromHash = decodeURIComponent(window.location.hash.substring(6));
        if (items.some(i => i.investigation_id === idFromHash)) {
          setActiveInvestigation(idFromHash);
        } else {
          resetWorkspace(true);
        }
      } else {
        // Fresh session or no explicit selection: DO NOT auto-select past footage!
        resetWorkspace(true);
      }
    } catch (err) {
      console.error("Could not load investigations:", err);
    }
  }

  function setActiveInvestigation(invId) {
    if (!invId) {
      resetWorkspace(true);
      return;
    }

    // Reset state before loading new investigation
    resetWorkspace(false);

    state.activeInvestigationId = invId;
    el.invSelect.value = invId;
    state.currentMediaSource = "video";
    state.currentMediaAssetId = null;

    // Synchronize URL hash without full reload
    if (window.location.hash !== `#case=${encodeURIComponent(invId)}`) {
      window.history.replaceState(null, "", `#case=${encodeURIComponent(invId)}`);
    }

    connectWebSocket(invId);
    refreshActiveCase();
  }

  async function loadDemoCase() {
    el.loadDemoBtn.disabled = true;
    el.loadDemoBtn.innerHTML = "<span>&#x21bb;</span> Seeding...";

    try {
      const res = await apiFetch("/api/v1/investigations/demo", { method: "POST" });
      showToast("Multi-camera forensic demo case loaded with synchronized feeds!", "success");
      await loadInvestigations(res.investigation_id, true);
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
      if (state.activeInvestigationId !== invId) return; // Prevent race condition
      state.status = statusData;
      updateCaseStatus(statusData.status);
      handleReportNotifications(invId, statusData);

      // 2. Full investigation details
      const invData = await apiFetch(`/api/v1/investigations/${invId}`);
      if (state.activeInvestigationId !== invId) return;

      // 3. Media assets (multi-video premise feeds)
      try {
        state.mediaAssets = await apiFetch(`/api/v1/investigations/${invId}/media`);
      } catch {
        state.mediaAssets = [];
      }

      // Update camera feed selector dropdown
      updateCameraFeedSelector(invData);

      // Load primary footage or active camera feed
      if (state.currentMediaSource !== "artifact") {
        if (state.currentMediaAssetId && state.mediaAssets.some(m => m.media_asset_id === state.currentMediaAssetId)) {
          switchCameraFeed(state.currentMediaAssetId, false);
        } else {
          loadPrimaryVideo();
        }
      }

      // 4. Events
      try {
        state.events = await apiFetch(`/api/v1/investigations/${invId}/events`);
        renderEvents();
        renderTimelineMarkers();
      } catch {
        state.events = [];
      }

      // 5. Observations
      try {
        state.observations = await apiFetch(`/api/v1/investigations/${invId}/observations`);
      } catch {
        state.observations = [];
      }
      renderObservations();

      // 6. Artifacts (frames, audio, clips)
      try {
        state.artifacts = await apiFetch(`/api/v1/investigations/${invId}/artifacts`);
      } catch {
        state.artifacts = [];
      }
      renderArtifacts();

      // 7. Evidence assessments
      try {
        state.assessments = await apiFetch(`/api/v1/investigations/${invId}/assessments`);
      } catch {
        state.assessments = [];
      }
      renderAssessments();

      // 8. Audit logs
      try {
        state.auditLogs = await apiFetch(`/api/v1/investigations/${invId}/audit`);
      } catch {
        state.auditLogs = [];
      }
      renderAuditLogs();

      // 9. Report preview
      loadReportPreview();

      // 10. HUD metrics
      updateHudMetrics();

    } catch (err) {
      console.warn("Error refreshing active case:", err);
    }
  }

  function updateCameraFeedSelector(invData) {
    if (!el.cameraFeedSelect) return;
    el.cameraFeedSelect.innerHTML = "";

    if (state.mediaAssets && state.mediaAssets.length > 0) {
      state.mediaAssets.forEach((ma, idx) => {
        const opt = document.createElement("option");
        opt.value = ma.media_asset_id;
        const camLabel = ma.camera_id ? ma.camera_id.toUpperCase() : `CAM-${idx + 1}`;
        const fileName = ma.file_path ? ma.file_path.split(/[\\/]/).pop() : ma.media_asset_id;
        opt.textContent = `${camLabel} (${fileName})`;
        el.cameraFeedSelect.appendChild(opt);
      });

      if (!state.mediaAssets.some(m => m.media_asset_id === state.currentMediaAssetId)) {
        state.currentMediaAssetId = state.mediaAssets[0].media_asset_id;
      }
      el.cameraFeedSelect.value = state.currentMediaAssetId;
    } else {
      const opt = document.createElement("option");
      opt.value = "primary";
      opt.textContent = invData?.camera_id ? `CAM: ${invData.camera_id.toUpperCase()}` : "Primary Feed";
      el.cameraFeedSelect.appendChild(opt);
      state.currentMediaAssetId = "primary";
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
  // Agent Mission Control & Readable Live Event Feed (Requirement A)
  // -------------------------------------------------------------------------
  function interpretEvent(msg) {
    const evtType = msg.event_type || "event";
    const data = msg.data || {};
    let category = "system";
    let title = "System Notification";
    let description = data.message || "";
    let statusClass = "";

    switch (evtType) {
      case "subscription_acknowledged":
        category = "system";
        title = "Telemetry Link Established";
        description = `Connected to live agent monitoring stream for case ${data.replayed_events ? `(${data.replayed_events} events synchronized)` : ""}`;
        break;

      case "connection":
        category = "system";
        title = "Mission Console Online";
        description = data.message || "Forensic telemetry link opened.";
        break;

      case "investigation_created":
        category = "planner";
        title = "Investigation Initialized";
        description = `Case "${data.title || data.investigation_id}" registered with ${data.media_count || 1} video feed(s). Preparing multi-modal pipeline.`;
        statusClass = "success";
        break;

      case "media_added":
        category = "visual";
        title = "Footage Ingested";
        description = `Feed ${data.camera_id ? data.camera_id.toUpperCase() : "camera"} ingested (${data.frame_count || 0} frames extracted).`;
        break;

      case "state_changed":
        category = "system";
        title = `Investigation State: ${data.status ? data.status.toUpperCase() : "UPDATED"}`;
        description = `Forensic workflow state transitioned to ${data.status || "active"}.`;
        if (data.status === "completed") statusClass = "success";
        if (data.status === "failed") statusClass = "error";
        break;

      case "plan_created":
        category = "planner";
        title = "Investigation Plan Formulated";
        description = `Planner Agent generated ${data.task_count || (data.tasks ? data.tasks.length : 0)} tactical forensic inspection tasks.`;
        statusClass = "planner";
        break;

      case "task_started":
        const tStartType = data.task_type || "";
        if (tStartType === "frame_sampling") {
          category = "visual";
          title = "Frame Extraction Started";
          description = "Extracting temporal image frames from source surveillance footage.";
        } else if (tStartType === "visual_analysis") {
          category = "visual";
          title = "Visual Inspection Started";
          description = "Vision model inspecting extracted frames for anomalies and suspicious entities.";
        } else if (tStartType === "audio_transcription") {
          category = "audio";
          title = "Acoustic Demuxing & Transcription";
          description = "Demuxing PCM audio track and analyzing acoustic event signatures.";
        } else if (tStartType === "event_correlation") {
          category = "temporal";
          title = "Temporal Correlation Started";
          description = "Correlating multi-camera observations across timestamps into candidate incidents.";
        } else if (tStartType === "evidence_assessment") {
          category = "verifier";
          title = "Evidence Assessment Started";
          description = "Forensic Verifier evaluating evidence credibility, support level, and uncertainty.";
        } else if (tStartType === "coverage_evaluation") {
          category = "verifier";
          title = "Coverage Evaluation Started";
          description = "Computing temporal and spatial coverage metrics across camera feeds.";
        } else if (tStartType === "report_generation") {
          category = "reporter";
          title = "Report Synthesis Started";
          description = "Synthesizing structured forensic deliverable report.";
        } else {
          category = "system";
          title = `Task Started: ${tStartType.replace(/_/g, " ").toUpperCase()}`;
          description = data.description || "Task execution initiated.";
        }
        break;

      case "task_completed":
        const tDoneType = data.task_type || "";
        if (tDoneType === "frame_sampling") {
          category = "visual";
          title = "Frame Extraction Completed";
          description = "Surveillance frames extracted, cataloged, and verified for SHA-256 integrity.";
        } else if (tDoneType === "visual_analysis") {
          category = "visual";
          title = "Visual Analysis Completed";
          description = "Vision model analysis finished across all extracted frames.";
        } else if (tDoneType === "audio_transcription") {
          category = "audio";
          title = "Acoustic Analysis Completed";
          description = "Acoustic transcription and sound transient detection finished.";
        } else if (tDoneType === "event_correlation") {
          category = "temporal";
          title = "Temporal Correlation Completed";
          description = "Incident candidates structured and synchronized on master timeline.";
        } else if (tDoneType === "evidence_assessment") {
          category = "verifier";
          title = "Evidence Assessment Completed";
          description = "Investigative rationales and credibility scores assigned to findings.";
        } else if (tDoneType === "coverage_evaluation") {
          category = "verifier";
          title = "Coverage Verification Concluded";
          description = "Evidence coverage assessment recorded in audit log.";
        } else if (tDoneType === "report_generation") {
          category = "reporter";
          title = "Forensic Report Synthesized";
          description = "Structured deliverable report drafted and ready for review.";
        } else {
          category = "system";
          title = `Task Completed: ${tDoneType.replace(/_/g, " ").toUpperCase()}`;
          description = "Agent operation finished successfully.";
        }
        statusClass = "success";
        break;

      case "observation_detected":
        const obs = data.observation || {};
        category = obs.modality === "audio" ? "audio" : "visual";
        title = `Observation Logged [${obs.modality ? obs.modality.toUpperCase() : "DETECTION"}]`;
        description = `${obs.observation_type ? obs.observation_type.replace(/_/g, " ").toUpperCase() : "Finding"}: ${cleanObservationDesc(obs.description).slice(0, 90)}`;
        statusClass = category;
        break;

      case "event_correlated":
        const evt = data.event || {};
        category = "temporal";
        title = `Incident Correlated: ${evt.event_type ? evt.event_type.replace(/_/g, " ").toUpperCase() : "INCIDENT"}`;
        description = evt.description ? evt.description.slice(0, 110) : "Potential incident flagged for analyst review.";
        statusClass = "temporal";
        break;

      case "coverage_updated":
        category = "verifier";
        title = "Coverage Metrics Updated";
        description = "Surveillance camera timeline coverage and spatial visibility metrics updated.";
        statusClass = "verifier";
        break;

      case "event_reviewed":
        category = "system";
        title = `Event Review: ${data.status ? data.status.toUpperCase() : "RECORDED"}`;
        description = `Analyst ${data.reviewer || "Investigator"} submitted decision for Event #${data.event_id || ""}.`;
        statusClass = data.status === "confirmed" ? "success" : (data.status === "rejected" ? "error" : "warn");
        break;

      case "event_edited":
        category = "system";
        title = `Event #${data.event_id || ""} Updated`;
        description = "Event parameters, offsets, or notes modified by investigator.";
        break;

      case "report_finalized":
        category = "reporter";
        title = "Case Deliverable Finalized & Signed";
        description = `Official report locked by ${data.finalized_by || "Lead Investigator"}. ${data.clip_count ? `${data.clip_count} H.264 video sub-clips sliced.` : ""}`;
        statusClass = "success";
        break;

      case "investigation_completed":
        category = "reporter";
        title = "Investigation Concluded Successfully";
        description = data.report_title ? `Case closed with report: "${data.report_title}".` : "All autonomous forensic agent tasks completed.";
        statusClass = "success";
        break;

      case "task_failed":
        category = "error";
        title = `Task Failed: ${data.task_type ? data.task_type.replace(/_/g, " ").toUpperCase() : "Operation"}`;
        description = data.error || "An error occurred during agent execution.";
        statusClass = "error";
        break;

      case "investigation_error":
      case "investigation_failed":
        category = "error";
        title = "Investigation Processing Error";
        description = data.error || "Forensic pipeline encountered an unrecoverable issue.";
        statusClass = "error";
        break;

      default:
        category = "system";
        title = evtType.replace(/_/g, " ").toUpperCase();
        description = data.message || (typeof data === "string" ? data : JSON.stringify(data));
        break;
    }

    return {
      category,
      title,
      description,
      statusClass,
      technicalPayload: JSON.stringify(msg, null, 2),
    };
  }

  function addTelemetryLog(msg) {
    if (!el.telemetryFeed) return;

    // Deduplication check
    const dedupKey = `${msg.event_type || ""}|${msg.timestamp || ""}|${msg.data?.task_id || msg.data?.observation?.observation_id || msg.data?.event?.event_id || msg.data?.message || ""}`;
    if (state.seenTelemetryKeys.has(dedupKey)) {
      return;
    }
    state.seenTelemetryKeys.add(dedupKey);

    // Remove empty state placeholder if present
    if (el.telemetryFeed.querySelector(".empty-state")) {
      el.telemetryFeed.innerHTML = "";
    }

    const interpreted = interpretEvent(msg);
    const timeStr = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    const item = document.createElement("div");
    item.className = `telemetry-item ${interpreted.statusClass || interpreted.category}`;

    item.innerHTML = `
      <div class="telemetry-meta">
        <span class="telemetry-badge badge-${interpreted.category}">${interpreted.category}</span>
        <span class="telemetry-timestamp">${timeStr}</span>
      </div>
      <div class="telemetry-title">${escapeHtml(interpreted.title)}</div>
      <div class="telemetry-body">${escapeHtml(interpreted.description)}</div>
      <details class="telemetry-details">
        <summary>Technical Payload</summary>
        <pre>${escapeHtml(interpreted.technicalPayload)}</pre>
      </details>
    `;

    // Sensible auto-scrolling: if user is already near bottom, auto-scroll; otherwise don't disrupt reading older events
    const isNearBottom = el.telemetryFeed.scrollHeight - el.telemetryFeed.scrollTop - el.telemetryFeed.clientHeight < 60;

    el.telemetryFeed.appendChild(item);

    if (isNearBottom) {
      el.telemetryFeed.scrollTop = el.telemetryFeed.scrollHeight;
    }

    // Keep DOM bounded to 150 items
    if (el.telemetryFeed.children.length > 150) {
      el.telemetryFeed.removeChild(el.telemetryFeed.firstChild);
    }

    el.telemetryCount.textContent = `${el.telemetryFeed.children.length} events`;
  }

  el.clearTelemetryBtn.addEventListener("click", () => {
    state.seenTelemetryKeys.clear();
    el.telemetryFeed.innerHTML = '<div class="empty-state">Log cleared. Real-time telemetry will appear as agents execute.</div>';
    el.telemetryCount.textContent = "0 events";
  });

  // -------------------------------------------------------------------------

  // -------------------------------------------------------------------------
  // Report Readiness Lifecycle & Deduplication
  // -------------------------------------------------------------------------
  function handleReportNotifications(invId, statusData) {
    if (!invId || !statusData) return;
    const s = (statusData.status || "").toLowerCase();
    const hasReport = Boolean(statusData.has_report);

    if (hasReport) {
      if (!state.notifiedReports.ready.has(invId)) {
        state.notifiedReports.ready.add(invId);
        showToast("Forensic report is ready and available for review.", "success");
      }
    } else if (s === "completed") {
      if (!state.notifiedReports.empty.has(invId)) {
        state.notifiedReports.empty.add(invId);
        showToast("Investigation completed, but no report was generated.", "warning");
      }
    } else if (s === "failed") {
      if (!state.notifiedReports.failed.has(invId)) {
        state.notifiedReports.failed.add(invId);
        showToast(`Investigation failed: ${statusData.error || "Execution error"}`, "error");
      }
    }
  }

  function scheduleStatusPolling() {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(async () => {
      if (!state.activeInvestigationId) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        return;
      }
      const s = (state.status?.status || "").toLowerCase();
      if (s === "completed" || s === "failed") {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        return;
      }
      // If WebSocket is active, let WS drive real-time telemetry
      if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        return;
      }
      try {
        const statusData = await apiFetch(`/api/v1/investigations/${state.activeInvestigationId}/status`, { silent: true });
        if (statusData) {
          handleReportNotifications(state.activeInvestigationId, statusData);
          if (state.status && (statusData.status !== state.status.status || statusData.has_report !== state.status.has_report || statusData.completed_tasks !== state.status.completed_tasks)) {
            refreshActiveCase();
          }
        }
      } catch (e) {
        // Silent catch for background polling
      }
    }, 4000);
  }

  // WebSocket Telemetry Connection
  // -------------------------------------------------------------------------
  function connectWebSocket(invId) {
    if (state.ws) {
      state.ws.onclose = null;
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
      scheduleStatusPolling();
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    state.ws = ws;
  }

  function handleTelemetryMessage(msg) {
    if (msg.event_type === "pong") return;

    addTelemetryLog(msg);
    activateAgentChip(msg);

    if (msg.event_type === "investigation_completed") {
      handleReportNotifications(state.activeInvestigationId, {
        status: "completed",
        has_report: Boolean(msg.data?.report_id || true)
      });
    } else if (msg.event_type === "investigation_failed" || (msg.event_type === "task_failed" && msg.data?.fatal)) {
      handleReportNotifications(state.activeInvestigationId, {
        status: "failed",
        has_report: false,
        error: msg.data?.error || "Task failure"
      });
    }

    if (
      msg.event_type === "state_changed" ||
      msg.event_type === "observation_detected" ||
      msg.event_type === "event_correlated" ||
      msg.event_type === "event_reviewed" ||
      msg.event_type === "report_finalized" ||
      msg.event_type === "investigation_completed" ||
      msg.event_type === "investigation_failed" ||
      msg.event_type === "task_failed"
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
    } else if (evtType === "task_started" || evtType === "task_completed") {
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
      targetId = (data?.observation?.modality === "audio") ? "chip-audio" : "chip-visual";
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

  // -------------------------------------------------------------------------
  // Video Player & Camera Feed Switching
  // -------------------------------------------------------------------------
  function loadPrimaryVideo() {
    if (state.mediaAssets && state.mediaAssets.length > 0) {
      switchCameraFeed(state.mediaAssets[0].media_asset_id, false);
      return;
    }

    state.currentMediaSource = "video";
    state.currentMediaAssetId = "primary";
    const invId = state.activeInvestigationId;
    if (!invId) {
      el.videoPlaceholder.classList.remove("hidden");
      return;
    }

    const primaryUrl = `/api/v1/investigations/${invId}/media/primary/content`;
    if (!el.mainVideoPlayer.src.includes(primaryUrl)) {
      el.mainVideoPlayer.src = primaryUrl;
      el.mainVideoPlayer.load();
      el.mainVideoPlayer.addEventListener("loadeddata", function paintFirstFrame() {
        if (el.mainVideoPlayer.currentTime === 0) {
          el.mainVideoPlayer.currentTime = 0.001;
        }
      }, { once: true });
    }

    el.videoPlaceholder.classList.add("hidden");
    el.hudCameraId.textContent = "CAM: PRIMARY";
    el.sourceMetaText.textContent = "SHA-256: PRIMARY_FOOTAGE_STREAM";
  }

  function switchCameraFeed(mediaAssetId, preservePlayhead = true) {
    state.currentMediaSource = "video";
    state.currentMediaAssetId = mediaAssetId;
    const invId = state.activeInvestigationId;
    if (!invId) return;

    const streamUrl = `/api/v1/investigations/${invId}/media/${mediaAssetId}/content`;
    const curTime = preservePlayhead ? el.mainVideoPlayer.currentTime : 0;

    if (!el.mainVideoPlayer.src.includes(streamUrl)) {
      el.mainVideoPlayer.src = streamUrl;
      el.mainVideoPlayer.load();

      el.mainVideoPlayer.addEventListener("loadeddata", function paintFirstFrame() {
        if (el.mainVideoPlayer.currentTime === 0) {
          el.mainVideoPlayer.currentTime = 0.001;
        }
      }, { once: true });

      if (curTime > 0) {
        el.mainVideoPlayer.addEventListener("loadedmetadata", function seekOnLoad() {
          el.mainVideoPlayer.currentTime = curTime;
          el.mainVideoPlayer.removeEventListener("loadedmetadata", seekOnLoad);
        });
      }
    }

    el.videoPlaceholder.classList.add("hidden");

    const ma = state.mediaAssets.find(m => m.media_asset_id === mediaAssetId);
    if (ma) {
      const camId = ma.camera_id ? ma.camera_id.toUpperCase() : "CAM";
      el.hudCameraId.textContent = `CAM: ${camId}`;
      const resInfo = (ma.width && ma.height) ? ` | ${ma.width}x${ma.height}` : "";
      const fpsInfo = ma.fps ? ` @ ${ma.fps.toFixed(1)}fps` : "";
      el.sourceMetaText.textContent = `SHA-256: ${(ma.sha256 || "verified").slice(0, 16)}... | ${camId}${resInfo}${fpsInfo}`;
    }

    if (el.cameraFeedSelect && el.cameraFeedSelect.value !== mediaAssetId) {
      el.cameraFeedSelect.value = mediaAssetId;
    }
  }

  if (el.cameraFeedSelect) {
    el.cameraFeedSelect.addEventListener("change", (e) => {
      switchCameraFeed(e.target.value, true);
    });
  }

  function playArtifact(artifactId) {
    state.currentMediaSource = "artifact";
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
    el.timelineSpanLabel.textContent = `0s \u2013 ${dur.toFixed(1)}s`;
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

  el.quickClipBtn.addEventListener("click", async () => {
    const curTime = el.mainVideoPlayer.currentTime;
    const invId = state.activeInvestigationId;

    if (!invId) {
      showToast("No active case loaded.", "error");
      return;
    }

    const matchingEvent = state.events.find(
      e => e.start_seconds !== null && e.end_seconds !== null && curTime >= e.start_seconds && curTime <= e.end_seconds
    );

    if (matchingEvent) {
      await sliceEventClipDirectly(matchingEvent.event_id);
    } else if (state.events.length > 0) {
      await sliceEventClipDirectly(state.events[0].event_id);
    } else {
      showToast(`Playhead at ${formatTime(curTime)}. Correlate an event to slice dedicated incident clip.`, "info");
    }
  });

  // -------------------------------------------------------------------------
  // Human Review Station (Requirement D)
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

    // Filter events based on active tab and search query
    const filtered = state.events.filter((e) => {
      let matchesFilter = false;
      if (state.activeFilter === "all") {
        matchesFilter = true;
      } else if (state.activeFilter === "proposed") {
        // Pending queue view: shows proposed or under_review only
        matchesFilter = (e.status === "proposed" || e.status === "under_review");
      } else {
        matchesFilter = (e.status === state.activeFilter);
      }

      const matchesSearch = !search ||
        e.event_type.toLowerCase().includes(search) ||
        e.description.toLowerCase().includes(search) ||
        (e.reviewer && e.reviewer.toLowerCase().includes(search));

      return matchesFilter && matchesSearch;
    });

    // Update filter badge counters accurately
    el.countAll.textContent = state.events.length;
    el.countProposed.textContent = state.events.filter(e => e.status === "proposed" || e.status === "under_review").length;
    el.countConfirmed.textContent = state.events.filter(e => e.status === "confirmed").length;
    el.countRejected.textContent = state.events.filter(e => e.status === "rejected").length;

    el.eventsList.innerHTML = "";
    if (filtered.length === 0) {
      const filterLabel = state.activeFilter === "proposed" ? "pending review" : state.activeFilter;
      el.eventsList.innerHTML = `<div class="empty-state">No ${filterLabel} events found.</div>`;
      return;
    }

    filtered.forEach((evt) => {
      const card = document.createElement("div");
      card.className = `event-card ${evt.status}`;
      card.id = `eventCard-${evt.event_id}`;

      const timeRange = (evt.start_seconds !== null && evt.end_seconds !== null)
        ? `${evt.start_seconds.toFixed(1)}s &ndash; ${evt.end_seconds.toFixed(1)}s`
        : "-";

      let reviewNotesHtml = "";
      if (evt.reviewer || evt.review_notes) {
        reviewNotesHtml = `
          <div class="event-review-notes">
            <strong>${escapeHtml(evt.reviewer || "Investigator")}:</strong> ${escapeHtml(evt.review_notes || "Verified by forensic analyst")}
          </div>
        `;
      }

      let cameraBadgeHtml = "";
      const matchedCam = state.mediaAssets.find(ma => ma.camera_id && evt.description.toLowerCase().includes(ma.camera_id.toLowerCase()));
      if (matchedCam) {
        cameraBadgeHtml = `<span class="badge cam-badge">${matchedCam.camera_id.toUpperCase()}</span>`;
      }

      card.innerHTML = `
        <div class="event-card-head">
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="event-card-type">${escapeHtml(evt.event_type.replace(/_/g, " ").toUpperCase())}</span>
            ${cameraBadgeHtml}
          </div>
          <span class="status-pill status-${evt.status}">${evt.status}</span>
        </div>
        <div class="event-card-id">#${evt.event_id} &bull; Interval: <strong>${timeRange}</strong></div>
        <div class="event-card-desc">${escapeHtml(evt.description)}</div>
        ${reviewNotesHtml}
        <div class="event-card-actions">
          <button class="btn btn-sm btn-confirm" data-id="${evt.event_id}" title="Confirm Verified Event (Removes from pending queue)">&#x2714; Confirm</button>
          <button class="btn btn-sm btn-reject" data-id="${evt.event_id}" title="Dismiss as False Positive (Removes from pending queue)">&#x2716; Reject</button>
          <button class="btn btn-sm btn-edit" data-id="${evt.event_id}" title="Edit Interval or Rationale Notes">&#x270E; Edit</button>
          <button class="btn btn-sm btn-outline btn-seek" data-time="${evt.start_seconds || 0}" title="Seek Player to Start">&#x25B6; Seek</button>
          <button class="btn btn-sm btn-clip" data-id="${evt.event_id}" title="Slice H.264 video sub-clip">&#x2702; Cut Clip</button>
        </div>
      `;

      // Quick Confirm Action with in-flight duplicate prevention
      const confirmBtn = card.querySelector(".btn-confirm");
      confirmBtn.addEventListener("click", async () => {
        await executeEventDecision(evt, "confirmed", card);
      });

      // Quick Reject Action with in-flight duplicate prevention
      const rejectBtn = card.querySelector(".btn-reject");
      rejectBtn.addEventListener("click", async () => {
        await executeEventDecision(evt, "rejected", card);
      });

      // Edit Button opens detailed review modal
      card.querySelector(".btn-edit").addEventListener("click", () => openReviewModal(evt, evt.status));

      // Seek Player to Event Time
      card.querySelector(".btn-seek").addEventListener("click", () => {
        if (matchedCam) {
          switchCameraFeed(matchedCam.media_asset_id, false);
        }
        if (evt.start_seconds !== null) el.mainVideoPlayer.currentTime = evt.start_seconds;
      });

      // Slice Incident Clip
      card.querySelector(".btn-clip").addEventListener("click", () => sliceEventClipDirectly(evt.event_id));

      el.eventsList.appendChild(card);
    });
  }

  async function executeEventDecision(evt, targetStatus, cardElement) {
    const invId = state.activeInvestigationId;
    if (!invId) return;

    // Prevent duplicate submissions
    const actionBtns = cardElement ? cardElement.querySelectorAll(".event-card-actions button") : [];
    actionBtns.forEach(b => { b.disabled = true; });

    const payload = {
      status: targetStatus,
      reviewer: "Lead Investigator",
      notes: targetStatus === "confirmed" ? "Verified and confirmed by forensic analyst." : "Dismissed as non-incident false positive.",
      event_type: evt.event_type,
      start_seconds: evt.start_seconds,
      end_seconds: evt.end_seconds,
    };

    try {
      await apiFetch(`/api/v1/investigations/${invId}/events/${evt.event_id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      // Update local event data
      evt.status = targetStatus;
      evt.reviewer = payload.reviewer;
      evt.review_notes = payload.notes;

      showToast(`Event #${evt.event_id} marked as ${targetStatus.toUpperCase()}`, "success");

      // Re-render: if activeFilter is 'proposed', the confirmed/rejected event automatically disappears!
      renderEvents();
      renderTimelineMarkers();

      // Refresh background audit trail & metrics
      refreshActiveCase();
    } catch (err) {
      console.error(err);
      // Re-enable buttons if failed, keeping the item in the pending queue
      actionBtns.forEach(b => { b.disabled = false; });
      showToast(`Failed to update event: ${err.message}`, "error");
    }
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
    el.revReviewerInput.value = evt.reviewer || "Lead Investigator";

    const radio = el.reviewForm.querySelector(`input[name="revStatus"][value="${targetStatus}"]`);
    if (radio) radio.checked = true;

    el.saveReviewBtn.disabled = false;
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
      reviewer: el.revReviewerInput.value.trim() || "Lead Investigator",
      notes: el.revNotesInput.value.trim(),
      description: el.revDescriptionInput.value.trim(),
      event_type: el.revCategoryInput.value.trim(),
      start_seconds: el.revStartSec.value ? parseFloat(el.revStartSec.value) : null,
      end_seconds: el.revEndSec.value ? parseFloat(el.revEndSec.value) : null,
    };

    el.saveReviewBtn.disabled = true;

    try {
      await apiFetch(`/api/v1/investigations/${invId}/events/${eventId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      // Update local event
      const localEvt = state.events.find(ev => ev.event_id === eventId);
      if (localEvt) {
        localEvt.status = statusVal;
        localEvt.reviewer = payload.reviewer;
        localEvt.review_notes = payload.notes;
        localEvt.description = payload.description;
        localEvt.event_type = payload.event_type;
        localEvt.start_seconds = payload.start_seconds;
        localEvt.end_seconds = payload.end_seconds;
      }

      showToast(`Event #${eventId} marked as ${statusVal.toUpperCase()}`, "success");
      el.reviewModal.classList.add("hidden");

      renderEvents();
      renderTimelineMarkers();
      refreshActiveCase();
    } catch (err) {
      console.error(err);
      el.saveReviewBtn.disabled = false;
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

    el.frameGallery.innerHTML = "";

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
        const assetId = f.source_reference?.media_asset_id;

        card.innerHTML = `
          <img class="frame-thumb" src="/api/v1/investigations/${state.activeInvestigationId}/artifacts/${f.artifact_id}/content" alt="Frame" loading="lazy">
          <div class="frame-card-footer">
            <span>#${f.artifact_id.slice(-6)}</span>
            <span>${timecodeStr}</span>
          </div>
        `;
        card.addEventListener("click", () => {
          if (assetId && state.mediaAssets.some(m => m.media_asset_id === assetId)) {
            switchCameraFeed(assetId, false);
          }
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
        if (state.currentMediaAssetId) {
          switchCameraFeed(state.currentMediaAssetId, false);
        } else {
          loadPrimaryVideo();
        }
      }
    });
  });

  // -------------------------------------------------------------------------
  // Helper Functions for Observations & Rationale Text
  // -------------------------------------------------------------------------
  function formatSecondsToTimecode(sec) {
    if (sec === null || sec === undefined || isNaN(sec)) return "-";
    const mins = Math.floor(sec / 60);
    const secs = (sec % 60).toFixed(1);
    const padM = mins < 10 ? "0" + mins : mins;
    const padS = (sec % 60) < 10 ? "0" + secs : secs;
    return `${padM}:${padS}`;
  }

  function cleanObservationDesc(desc) {
    if (!desc) return "";
    let clean = desc.trim();
    if (clean.includes("```")) {
      clean = clean.replace(/```(?:json|markdown)?\s*([\s\S]*?)\s*```/g, "$1").trim();
    }
    if ((clean.startsWith("{") && clean.endsWith("}")) || (clean.startsWith("[") && clean.endsWith("]"))) {
      try {
        const parsed = JSON.parse(clean);
        if (typeof parsed === "object" && parsed !== null) {
          if (parsed.description) {
            clean = parsed.description;
          } else if (Array.isArray(parsed.observations) && parsed.observations.length > 0) {
            clean = parsed.observations.map(o => o.description || o.label || JSON.stringify(o)).join(" ");
          } else if (parsed.scene || parsed.summary) {
            clean = parsed.scene || parsed.summary;
          }
        }
      } catch (e) {
        // Continue with text cleaning
      }
    }
    clean = clean.replace(/^(?:based on the (?:visual|image|frame|surveillance evidence|provided image)[^,:]*[,:]\s*)/i, "");
    clean = clean.replace(/^(?:in this (?:surveillance )?(?:frame|image|scene|video)[^,:]*[,:]\s*)/i, "");
    clean = clean.replace(/^(?:the (?:provided )?(?:image|frame|surveillance video|footage) (?:shows|depicts|displays|reveals|contains)\s*)/i, "");
    clean = clean.replace(/^(?:here is the (?:visual |forensic )?analysis[^,:]*[,:]\s*)/i, "");
    clean = clean.replace(/\\"/g, '"').replace(/\\n/g, " ").replace(/\s+/g, " ").trim();
    if (clean.length > 0) {
      clean = clean.charAt(0).toUpperCase() + clean.slice(1);
    }
    return clean || "Visual features observed in frame.";
  }

  function cleanRationaleText(text) {
    if (!text) return "";
    let clean = text
      .replace(/\*\*Rating\s*:\s*[^\*]+\*\*/gi, "")
      .replace(/\*\*Rationale\s*:\s*\*\*/gi, "")
      .replace(/^Rating\s*:\s*[^\n]+\n?/gi, "")
      .replace(/^Rationale\s*:\s*/gi, "")
      .replace(/^[\s\-*•]+/g, "")
      .trim();
    return clean || text.trim();
  }

  // -------------------------------------------------------------------------
  // Observations Drawer Table
  // -------------------------------------------------------------------------
  function renderObservations() {
    el.obsCount.textContent = state.observations.length;
    el.observationsTable.innerHTML = "";

    if (state.observations.length === 0) {
      el.observationsTable.innerHTML = `<tr><td colspan="8" style="text-align:center;">No observations recorded for this investigation.</td></tr>`;
      return;
    }

    state.observations.forEach((obs) => {
      const row = document.createElement("tr");
      const sr = obs.source_references && obs.source_references.length > 0 ? obs.source_references[0] : null;
      let intervalStr = "-";
      if (sr && sr.start_seconds !== null && sr.end_seconds !== null) {
        intervalStr = `<code>${formatSecondsToTimecode(sr.start_seconds)} &ndash; ${formatSecondsToTimecode(sr.end_seconds)}</code> <small style="color:var(--text-dim)">(${sr.start_seconds.toFixed(1)}s &ndash; ${sr.end_seconds.toFixed(1)}s)</small>`;
      } else if (sr && sr.start_seconds !== null) {
        intervalStr = `<code>${formatSecondsToTimecode(sr.start_seconds)}</code> <small style="color:var(--text-dim)">(${sr.start_seconds.toFixed(1)}s)</small>`;
      }
      
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
      const cleanDesc = cleanObservationDesc(obs.description);

      let camLabel = "MAIN";
      let targetAssetId = sr?.media_asset_id || null;

      if (obs.camera_id) {
        camLabel = obs.camera_id;
      } else {
        const camPrefixMatch = cleanDesc.match(/^\[([a-zA-Z0-9_\-]+):/);
        if (camPrefixMatch) {
          camLabel = camPrefixMatch[1];
        } else if (targetAssetId) {
          const ma = state.mediaAssets.find(m => m.media_asset_id === targetAssetId);
          if (ma && ma.camera_id) camLabel = ma.camera_id;
        }
      }

      const matchedAsset = state.mediaAssets.find(m => m.camera_id && m.camera_id.toLowerCase() === camLabel.toLowerCase()) ||
                           state.mediaAssets.find(m => m.media_asset_id === targetAssetId);

      row.innerHTML = `
        <td><code>${obs.observation_id}</code></td>
        <td><span class="cam-badge">${camLabel.toUpperCase()}</span></td>
        <td><span class="modality-badge ${modClass}">${obs.modality}</span></td>
        <td><strong>${obs.observation_type.replace(/_/g, " ")}</strong></td>
        <td>${intervalStr}</td>
        <td>${confHtml}</td>
        <td>${escapeHtml(cleanDesc)}</td>
        <td><small style="color:var(--text-dim);">${provName}</small></td>
      `;

      row.style.cursor = "pointer";
      row.addEventListener("click", () => {
        if (matchedAsset) {
          switchCameraFeed(matchedAsset.media_asset_id, false);
        }
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
      el.assessmentsTable.innerHTML = `<tr><td colspan="6" style="text-align:center;">No evidence assessments available for this case.</td></tr>`;
      return;
    }

    state.assessments.forEach((as) => {
      const row = document.createElement("tr");
      const ratingClass = `rating-${as.rating}`;
      const cleanRat = cleanRationaleText(as.rationale);

      row.innerHTML = `
        <td><code>${as.target_id}</code></td>
        <td><span class="badge">${as.target_type}</span></td>
        <td><strong>${as.assessment_type.replace(/_/g, " ").toUpperCase()}</strong></td>
        <td><span class="rating-badge ${ratingClass}">${as.rating.toUpperCase()}</span></td>
        <td>${escapeHtml(cleanRat)}</td>
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
        <td><strong>${escapeHtml(log.actor)}</strong></td>
        <td><code>${escapeHtml(log.action)}</code></td>
        <td>${escapeHtml(log.target_id)}</td>
        <td>${changesStr}</td>
        <td>${escapeHtml(log.notes || "-")}</td>
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
    if (!state.activeInvestigationId) {
      el.reportPreviewBox.innerHTML = `<div class="gallery-empty">Select or load an investigation to view findings.</div>`;
      return;
    }

    const currentStatus = (state.status?.status || "").toLowerCase();
    const hasReport = Boolean(state.status?.has_report);

    // If report is not ready yet, display neutral progress or terminal message without calling /report
    if (!hasReport) {
      if (currentStatus === "running" || currentStatus === "created") {
        el.reportPreviewBox.innerHTML = `<div class="gallery-empty" style="color:var(--text-muted);"><span class="spinner" style="display:inline-block; margin-right:8px; vertical-align:middle;"></span>Investigation in progress. Structured deliverable report will be available upon completion.</div>`;
        return;
      }
      if (currentStatus === "completed") {
        el.reportPreviewBox.innerHTML = `<div class="gallery-empty" style="color:#f87171;">Investigation completed, but no final report was persisted.</div>`;
        return;
      }
      if (currentStatus === "failed") {
        el.reportPreviewBox.innerHTML = `<div class="gallery-empty" style="color:#f87171;">Investigation failed: ${escapeHtml(state.status?.error || "Task failure")}</div>`;
        return;
      }
      el.reportPreviewBox.innerHTML = `<div class="gallery-empty">Investigation still in progress or no report generated yet.</div>`;
      return;
    }

    try {
      const report = await apiFetch(`/api/v1/investigations/${state.activeInvestigationId}/report`, { silent: true });
      el.reportPreviewBox.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <h4 style="color:#93c5fd; margin:0;">${escapeHtml(report.title)}</h4>
          <span class="status-pill status-${report.status}">v${report.version} &bull; ${report.status.toUpperCase()}</span>
        </div>
        <p style="margin-bottom: 12px; color:#e2e8f0; white-space:pre-line; line-height:1.5;">${escapeHtml(report.summary)}</p>
        <div style="display:flex; gap:10px; align-items:center; font-size:0.75rem; color:#94a3b8; border-top: 1px solid var(--border-color); padding-top: 8px;">
          <span>Generated by: <strong>${escapeHtml(report.generated_by)}</strong></span>
          <span>&bull;</span>
          <span>Finalized by: <strong>${escapeHtml(report.finalized_by || "Pending Sign-off")}</strong></span>
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
    } catch (err) {
      el.reportPreviewBox.innerHTML = `<div class="gallery-empty">Unable to load report findings (${escapeHtml(err.message)}).</div>`;
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
    if (!state.activeInvestigationId) { showToast("No active case to export", "error"); return; }
    window.open(`/api/v1/investigations/${state.activeInvestigationId}/export/pdf`, "_blank");
  });

  el.exportHtmlBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    if (!state.activeInvestigationId) { showToast("No active case to export", "error"); return; }
    window.open(`/api/v1/investigations/${state.activeInvestigationId}/export/html`, "_blank");
  });

  el.exportMdBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    if (!state.activeInvestigationId) { showToast("No active case to export", "error"); return; }
    window.open(`/api/v1/investigations/${state.activeInvestigationId}/report?format=markdown`, "_blank");
  });

  el.finalizeReportBtn.addEventListener("click", () => {
    el.exportMenu.classList.add("hidden");
    if (!state.activeInvestigationId) { showToast("No active case to finalize", "error"); return; }
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

    el.submitFinalizeBtn.disabled = true;

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
    } finally {
      el.submitFinalizeBtn.disabled = false;
    }
  });

  // -------------------------------------------------------------------------
  // New Investigation Modal & Ingestion
  // -------------------------------------------------------------------------
  let isAppendingVideos = false;
  let userEditedTitle = false;

  function suggestCameraId(filename, index) {
    if (!filename) return `cam-${String(index + 1).padStart(2, "0")}`;
    const clean = filename.toLowerCase();
    const camMatch = clean.match(/(?:cam(?:era)?)[-_]?([a-zA-Z0-9]+)/);
    if (camMatch && camMatch[1]) {
      return `cam-${camMatch[1]}`;
    }
    const locMatch = clean.match(/(gate|lobby|courtyard|perimeter|north|south|east|west|hallway|entrance|exit|corridor|parking|driveway)/i);
    if (locMatch && locMatch[1]) {
      return `cam-${locMatch[1].toLowerCase()}`;
    }
    return `cam-${String(index + 1).padStart(2, "0")}`;
  }

  function openNewInvModal() {
    el.newInvModal.classList.remove("hidden");
  }

  el.newInvBtn.addEventListener("click", openNewInvModal);
  el.placeholderUploadBtn.addEventListener("click", openNewInvModal);
  el.closeNewInvModal.addEventListener("click", () => el.newInvModal.classList.add("hidden"));
  el.cancelNewInvBtn.addEventListener("click", () => el.newInvModal.classList.add("hidden"));

  if (el.invTitleInput) {
    el.invTitleInput.addEventListener("input", () => {
      userEditedTitle = el.invTitleInput.value.trim().length > 0;
    });
  }

  function syncCameraIdsSummary() {
    if (!el.invCameraInput) return;
    const ids = state.selectedFeeds.map(f => f.cameraId.trim()).filter(Boolean);
    el.invCameraInput.value = ids.join(", ");
  }

  function renderSelectedFeeds() {
    if (!el.selectedFeedsQueue || !el.selectedFeedsList) return;

    const count = state.selectedFeeds.length;
    if (el.selectedFeedCount) el.selectedFeedCount.textContent = count;

    if (count === 0) {
      el.selectedFeedsQueue.classList.add("hidden");
      if (el.addMoreVideosBtn) el.addMoreVideosBtn.classList.add("hidden");
      if (el.clearAllVideosBtn) el.clearAllVideosBtn.classList.add("hidden");
      if (el.browseVideosBtn) el.browseVideosBtn.textContent = "\uD83D\uDCC1 Select Video Files (Multiple)";
      if (!userEditedTitle && el.invTitleInput) el.invTitleInput.value = "";
      syncCameraIdsSummary();
      return;
    }

    el.selectedFeedsQueue.classList.remove("hidden");
    if (el.addMoreVideosBtn) el.addMoreVideosBtn.classList.remove("hidden");
    if (el.clearAllVideosBtn) el.clearAllVideosBtn.classList.remove("hidden");
    if (el.browseVideosBtn) el.browseVideosBtn.textContent = "\uD83D\uDD04 Replace All Files";

    el.selectedFeedsList.innerHTML = state.selectedFeeds.map((feed, idx) => `
      <div class="feed-row-item" data-feed-id="${feed.id}">
        <span class="feed-num-pill">FEED ${idx + 1}</span>
        <div class="feed-details">
          <div class="feed-file-name" title="${escapeHtml(feed.name)}">&#x1F4F9; ${escapeHtml(feed.name)}</div>
          <div class="feed-file-size">${(feed.size / (1024 * 1024)).toFixed(2)} MB</div>
        </div>
        <div class="feed-cam-assign">
          <label>CAM ID:</label>
          <input type="text" class="feed-cam-input" data-index="${idx}" value="${escapeHtml(feed.cameraId)}" placeholder="cam-${idx + 1}">
        </div>
        <button type="button" class="feed-remove-btn" data-index="${idx}" title="Remove this video feed">&times;</button>
      </div>
    `).join("");

    el.selectedFeedsList.querySelectorAll(".feed-cam-input").forEach((inp) => {
      inp.addEventListener("input", (e) => {
        const idx = parseInt(e.target.dataset.index, 10);
        if (state.selectedFeeds[idx]) {
          state.selectedFeeds[idx].cameraId = e.target.value.trim();
          syncCameraIdsSummary();
        }
      });
    });

    el.selectedFeedsList.querySelectorAll(".feed-remove-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(e.target.dataset.index, 10);
        removeSelectedFeed(idx);
      });
    });

    if (!userEditedTitle && el.invTitleInput) {
      if (count === 1) {
        el.invTitleInput.value = `Premise Investigation: ${state.selectedFeeds[0].name}`;
      } else {
        el.invTitleInput.value = `Premise Multi-Feed Investigation (${count} cameras)`;
      }
    }

    syncCameraIdsSummary();
  }

  function handleFilesSelection(fileList, append = false) {
    if (!fileList || fileList.length === 0) return;
    const newFiles = Array.from(fileList);

    if (!append) {
      state.selectedFeeds = [];
    }

    newFiles.forEach((file) => {
      const exists = state.selectedFeeds.some(f => f.name === file.name && f.size === file.size);
      if (!exists) {
        const nextIdx = state.selectedFeeds.length;
        const camId = suggestCameraId(file.name, nextIdx);
        state.selectedFeeds.push({
          id: Math.random().toString(36).slice(2, 9),
          file: file,
          name: file.name,
          size: file.size,
          cameraId: camId,
        });
      }
    });

    state.selectedFiles = state.selectedFeeds.map(f => f.file);
    renderSelectedFeeds();
  }

  function removeSelectedFeed(index) {
    if (index >= 0 && index < state.selectedFeeds.length) {
      state.selectedFeeds.splice(index, 1);
      state.selectedFiles = state.selectedFeeds.map(f => f.file);
      renderSelectedFeeds();
    }
  }

  function clearSelectedFeeds() {
    state.selectedFeeds = [];
    state.selectedFiles = [];
    if (el.videoFileInput) el.videoFileInput.value = "";
    userEditedTitle = false;
    renderSelectedFeeds();
  }

  if (el.browseVideosBtn) {
    el.browseVideosBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      isAppendingVideos = false;
      el.videoFileInput.value = "";
      el.videoFileInput.click();
    });
  }

  if (el.addMoreVideosBtn) {
    el.addMoreVideosBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      isAppendingVideos = true;
      el.videoFileInput.value = "";
      el.videoFileInput.click();
    });
  }

  if (el.clearAllVideosBtn) {
    el.clearAllVideosBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      clearSelectedFeeds();
    });
  }

  if (el.videoFileInput) {
    el.videoFileInput.addEventListener("change", () => {
      if (el.videoFileInput.files && el.videoFileInput.files.length > 0) {
        handleFilesSelection(el.videoFileInput.files, isAppendingVideos);
      }
    });
  }

  if (el.dropZone) {
    el.dropZone.addEventListener("click", (e) => {
      if (e.target.closest("button") || e.target.closest("input")) return;
      isAppendingVideos = state.selectedFeeds.length > 0;
      el.videoFileInput.value = "";
      el.videoFileInput.click();
    });
    el.dropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      el.dropZone.classList.add("dragover");
    });
    el.dropZone.addEventListener("dragleave", () => el.dropZone.classList.remove("dragover"));
    el.dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      el.dropZone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFilesSelection(e.dataTransfer.files, true);
      }
    });
  }

  el.newInvForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.selectedFeeds || state.selectedFeeds.length === 0) {
      showToast("Please select at least one video footage file.", "error");
      return;
    }

    const formData = new FormData();
    state.selectedFeeds.forEach((feed) => {
      formData.append("files", feed.file);
    });

    const titleInputVal = el.invTitleInput ? el.invTitleInput.value.trim() : "";
    const titleVal = titleInputVal || (state.selectedFeeds.length > 1
      ? `Premise Multi-Feed Investigation (${state.selectedFeeds.length} cameras)`
      : `Investigation: ${state.selectedFeeds[0].name}`);
    formData.append("title", titleVal);

    const cameraIds = state.selectedFeeds.map(f => f.cameraId.trim() || "cam-main");
    formData.append("camera_ids", cameraIds.join(", "));
    formData.append("camera_id", cameraIds[0] || "cam-main");

    formData.append("objective", document.getElementById("invObjectiveInput").value.trim() || "Perform complete multi-modal video and acoustic investigation across all premise feeds.");
    formData.append("sample_interval_seconds", document.getElementById("invSampleInterval").value);
    formData.append("max_frames", document.getElementById("invMaxFrames").value);
    formData.append("extract_audio", document.getElementById("invExtractAudio").value);
    formData.append("run_async", "true");

    el.startInvBtn.disabled = true;
    el.uploadSpinner.classList.remove("hidden");
    const count = state.selectedFeeds.length;
    showToast(`Ingesting ${count} video feed(s) sequentially & initiating cross-camera analysis...`, "info");

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
      const countMsg = inv.media_count ? ` (${inv.media_count} feeds ingested)` : "";
      showToast(`Investigation ${inv.investigation_id} created and running${countMsg}!`, "success");
      el.newInvModal.classList.add("hidden");
      el.newInvForm.reset();
      clearSelectedFeeds();

      // Switch to this new investigation
      await loadInvestigations(inv.investigation_id, true);
    } catch (err) {
        showToast(err.message, "error");
    } finally {
      el.startInvBtn.disabled = false;
      el.uploadSpinner.classList.add("hidden");
    }
  });

  // -------------------------------------------------------------------------
  // Additional Camera Feed Ingestion
  // -------------------------------------------------------------------------
  if (el.openAddFeedModalBtn) {
    el.openAddFeedModalBtn.addEventListener("click", () => {
      if (!state.activeInvestigationId) {
        showToast("Please select or load an active investigation first.", "warning");
        return;
      }
      if (el.addFeedCameraId) {
        const nextCamNum = (state.mediaAssets ? state.mediaAssets.length : 0) + 1;
        el.addFeedCameraId.value = `cam-${String(nextCamNum).padStart(2, "0")}`;
      }
      el.addFeedModal.classList.remove("hidden");
    });
  }

  if (el.closeAddFeedModal) el.closeAddFeedModal.addEventListener("click", () => el.addFeedModal.classList.add("hidden"));
  if (el.cancelAddFeedBtn) el.cancelAddFeedBtn.addEventListener("click", () => el.addFeedModal.classList.add("hidden"));

  if (el.browseSingleFeedBtn && el.addFeedFileInput) {
    el.browseSingleFeedBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      el.addFeedFileInput.click();
    });
  }

  if (el.addFeedDropZone && el.addFeedFileInput) {
    el.addFeedDropZone.addEventListener("click", (e) => {
      if (e.target.closest("button") || e.target.closest("input")) return;
      el.addFeedFileInput.click();
    });
    el.addFeedDropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      el.addFeedDropZone.classList.add("dragover");
    });
    el.addFeedDropZone.addEventListener("dragleave", () => el.addFeedDropZone.classList.remove("dragover"));
    el.addFeedDropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      el.addFeedDropZone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        el.addFeedFileInput.files = e.dataTransfer.files;
        updateAddFeedFileLabel();
      }
    });
  }

  function updateAddFeedFileLabel() {
    if (!el.addFeedFileInput || !el.addFeedSelectedLabel) return;
    if (el.addFeedFileInput.files && el.addFeedFileInput.files.length > 0) {
      const f = el.addFeedFileInput.files[0];
      el.addFeedSelectedLabel.innerHTML = `<strong>Selected:</strong> ${escapeHtml(f.name)} (${(f.size / (1024 * 1024)).toFixed(2)} MB)`;
      el.addFeedSelectedLabel.classList.remove("hidden");
      if (el.addFeedCameraId && !el.addFeedCameraId.dataset.edited) {
        el.addFeedCameraId.value = suggestCameraId(f.name, (state.mediaAssets ? state.mediaAssets.length : 0));
      }
    } else {
      el.addFeedSelectedLabel.classList.add("hidden");
    }
  }

  if (el.addFeedFileInput) {
    el.addFeedFileInput.addEventListener("change", updateAddFeedFileLabel);
  }

  if (el.addFeedCameraId) {
    el.addFeedCameraId.addEventListener("input", () => {
      el.addFeedCameraId.dataset.edited = "true";
    });
  }

  if (el.addFeedForm) {
    el.addFeedForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const invId = state.activeInvestigationId;
      if (!invId) {
        showToast("No active investigation selected.", "error");
        return;
      }

      if (!el.addFeedFileInput.files || el.addFeedFileInput.files.length === 0) {
        showToast("Please choose a video footage file.", "error");
        return;
      }

      const file = el.addFeedFileInput.files[0];
      const camId = el.addFeedCameraId.value.trim() || "cam-extra";
      const camName = el.addFeedCameraName ? el.addFeedCameraName.value.trim() : "";

      const formData = new FormData();
      formData.append("file", file);
      formData.append("camera_id", camId);
      if (camName) formData.append("camera_name", camName);
      formData.append("sample_interval_seconds", "2.0");
      formData.append("max_frames", "30");

      el.submitAddFeedBtn.disabled = true;
      if (el.addFeedSpinner) el.addFeedSpinner.classList.remove("hidden");
      showToast(`Ingesting feed ${camId}...`, "info");

      try {
        const res = await fetch(`/api/v1/investigations/${invId}/media`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || "Failed to add feed");
        }

        const data = await res.json();
        showToast(`Feed ${camId} ingested successfully! (${data.frame_count} frames extracted)`, "success");
        el.addFeedModal.classList.add("hidden");
        el.addFeedForm.reset();
        if (el.addFeedSelectedLabel) el.addFeedSelectedLabel.classList.add("hidden");
        delete el.addFeedCameraId.dataset.edited;

        await refreshActiveCase();
        if (data.media_asset_id) {
          switchCameraFeed(data.media_asset_id, false);
        }
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        el.submitAddFeedBtn.disabled = false;
        if (el.addFeedSpinner) el.addFeedSpinner.classList.add("hidden");
      }
    });
  }

  // Demo Case Buttons
  el.loadDemoBtn.addEventListener("click", loadDemoCase);
  el.placeholderDemoBtn.addEventListener("click", loadDemoCase);

  // -------------------------------------------------------------------------
  // Keyboard Shortcuts
  // -------------------------------------------------------------------------
  function openHotkeysModal() {
    el.hotkeysModal.classList.remove("hidden");
  }

  el.hotkeysBtn.addEventListener("click", openHotkeysModal);
  el.closeHotkeysModal.addEventListener("click", () => el.hotkeysModal.classList.add("hidden"));
  el.dismissHotkeysBtn.addEventListener("click", () => el.hotkeysModal.classList.add("hidden"));

  document.addEventListener("keydown", (e) => {
    // If landing page is visible
    if (!el.landingPage.classList.contains("hidden")) {
      if (e.key === "Enter") {
        e.preventDefault();
        navigateToWorkspace();
        return;
      }
      if (e.key === "d" || e.key === "D") {
        e.preventDefault();
        showDashboard();
        loadDemoCase();
        return;
      }
    }

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

  el.invSelect.addEventListener("change", (e) => {
    setActiveInvestigation(e.target.value);
  });

  el.refreshInvBtn.addEventListener("click", () => {
    loadInvestigations(state.activeInvestigationId, false);
    showToast("Case catalog refreshed", "info");
  });

  // Initialize Route
  handleRoute();
})();
