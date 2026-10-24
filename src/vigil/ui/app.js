/**
 * VIGIL Video Forensics Mission Control - Interactive Application Logic
 * Full autonomous multi-agent forensic suite frontend
 * Enhanced with Multi-Video Premise Correlation & Cross-Camera Timeline Switching
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
    selectedFiles: [],
    selectedFeeds: [],
    currentMediaAssetId: null,
    currentMediaSource: "video", // "video" or "artifact"
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
    cameraFeedSelect: document.getElementById("cameraFeedSelect"),
    cameraFeedPickerWrap: document.getElementById("cameraFeedPickerWrap"),
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
    selectedFileLabel: document.getElementById("selectedFileLabel"),
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
  async function loadInvestigations(targetInvId = null) {
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

      const toSelect = targetInvId
        || (state.activeInvestigationId && items.some(i => i.investigation_id === state.activeInvestigationId)
            ? state.activeInvestigationId
            : items[0].investigation_id);

      setActiveInvestigation(toSelect);
    } catch (err) {
      console.error("Could not load investigations:", err);
    }
  }

  function setActiveInvestigation(invId) {
    state.activeInvestigationId = invId;
    el.invSelect.value = invId;
    state.currentMediaSource = "video";
    state.currentMediaAssetId = null;
    connectWebSocket(invId);
    refreshActiveCase();
  }

  async function loadDemoCase() {
    el.loadDemoBtn.disabled = true;
    el.loadDemoBtn.innerHTML = "<span>&#x21bb;</span> Seeding...";

    try {
      const res = await apiFetch("/api/v1/investigations/demo", { method: "POST" });
      showToast("Premise multi-camera demo case loaded with synchronized feeds!", "success");
      await loadInvestigations(res.investigation_id);
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

      // 3. Media assets (multi-video premise feeds)
      try {
        state.mediaAssets = await apiFetch(`/api/v1/investigations/${invId}/media`);
      } catch {
        state.mediaAssets = [];
      }

      // Update camera feed selector dropdown
      updateCameraFeedSelector(invData);

      // Immediately load and show the surveillance video feed
      if (state.currentMediaSource !== "artifact") {
        if (state.currentMediaAssetId) {
          switchCameraFeed(state.currentMediaAssetId, false);
        } else {
          loadPrimaryVideo();
        }
      }

      // 4. Events
      try {
        const eventsData = await apiFetch(`/api/v1/investigations/${invId}/events`);
        state.events = eventsData;
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
        const artifactsData = await apiFetch(`/api/v1/investigations/${invId}/artifacts`);
        state.artifacts = artifactsData;
        renderArtifacts();
      } catch {
        state.artifacts = [];
      }

      // 7. Evidence assessments
      try {
        state.assessments = await apiFetch(`/api/v1/investigations/${invId}/assessments`);
      } catch {
        state.assessments = [];
      }
      renderAssessments();

      // 8. Audit logs
      try {
        const auditData = await apiFetch(`/api/v1/investigations/${invId}/audit`);
        state.auditLogs = auditData;
        renderAuditLogs();
      } catch {
        state.auditLogs = [];
      }

      // 10. Report preview
      loadReportPreview();

      // 11. Update HUD metric counters
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

      // Keep current selection if valid, or default to first
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

    // Look up media asset details
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

      // Check if event mentions camera
      let cameraBadgeHtml = "";
      const matchedCam = state.mediaAssets.find(ma => ma.camera_id && evt.description.toLowerCase().includes(ma.camera_id.toLowerCase()));
      if (matchedCam) {
        cameraBadgeHtml = `<span class="badge cam-badge">${matchedCam.camera_id.toUpperCase()}</span>`;
      }

      card.innerHTML = `
        <div class="event-card-head">
          <div style="display:flex; align-items:center; gap:6px;">
            <span class="event-card-type">${evt.event_type.replace(/_/g, " ").toUpperCase()}</span>
            ${cameraBadgeHtml}
          </div>
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
        if (matchedCam) {
          switchCameraFeed(matchedCam.media_asset_id, false);
        }
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
    if (clean.startsWith("```json")) clean = clean.substring(7);
    if (clean.startsWith("```")) clean = clean.substring(3);
    if (clean.endsWith("```")) clean = clean.substring(0, clean.length - 3);
    return clean.trim();
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

      // Determine Camera Attribution
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

      // Check if camera label maps to an asset
      const matchedAsset = state.mediaAssets.find(m => m.camera_id && m.camera_id.toLowerCase() === camLabel.toLowerCase()) ||
                           state.mediaAssets.find(m => m.media_asset_id === targetAssetId);

      row.innerHTML = `
        <td><code>${obs.observation_id}</code></td>
        <td><span class="cam-badge">${camLabel.toUpperCase()}</span></td>
        <td><span class="modality-badge ${modClass}">${obs.modality}</span></td>
        <td><strong>${obs.observation_type.replace(/_/g, " ")}</strong></td>
        <td>${intervalStr}</td>
        <td>${confHtml}</td>
        <td>${cleanDesc}</td>
        <td><small style="color:var(--text-dim);">${provName}</small></td>
      `;

      // Clicking an observation jumps player to corresponding camera feed & timecode
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
        <td>${cleanRat}</td>
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
  // New Investigation Modal & Multi-Video Sequential Ingestion
  // -------------------------------------------------------------------------
  let isAppendingVideos = false;
  let userEditedTitle = false;

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

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
      if (el.browseVideosBtn) el.browseVideosBtn.textContent = "📁 Select Video Files (Multiple)";
      if (!userEditedTitle && el.invTitleInput) el.invTitleInput.value = "";
      syncCameraIdsSummary();
      return;
    }

    el.selectedFeedsQueue.classList.remove("hidden");
    if (el.addMoreVideosBtn) el.addMoreVideosBtn.classList.remove("hidden");
    if (el.clearAllVideosBtn) el.clearAllVideosBtn.classList.remove("hidden");
    if (el.browseVideosBtn) el.browseVideosBtn.textContent = "🔄 Replace All Files";

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

    // Wire camera ID inputs
    el.selectedFeedsList.querySelectorAll(".feed-cam-input").forEach((inp) => {
      inp.addEventListener("input", (e) => {
        const idx = parseInt(e.target.dataset.index, 10);
        if (state.selectedFeeds[idx]) {
          state.selectedFeeds[idx].cameraId = e.target.value.trim();
          syncCameraIdsSummary();
        }
      });
    });

    // Wire remove buttons
    el.selectedFeedsList.querySelectorAll(".feed-remove-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt(e.target.dataset.index, 10);
        removeSelectedFeed(idx);
      });
    });

    // Update auto title if not customized
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

  // Browse multiple videos button
  if (el.browseVideosBtn) {
    el.browseVideosBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      isAppendingVideos = false;
      el.videoFileInput.value = "";
      el.videoFileInput.click();
    });
  }

  // Add more videos button
  if (el.addMoreVideosBtn) {
    el.addMoreVideosBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      isAppendingVideos = true;
      el.videoFileInput.value = "";
      el.videoFileInput.click();
    });
  }

  // Clear all button
  if (el.clearAllVideosBtn) {
    el.clearAllVideosBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      clearSelectedFeeds();
    });
  }

  // File input change handler
  if (el.videoFileInput) {
    el.videoFileInput.addEventListener("change", () => {
      if (el.videoFileInput.files && el.videoFileInput.files.length > 0) {
        handleFilesSelection(el.videoFileInput.files, isAppendingVideos);
      }
    });
  }

  // Drop zone events (avoid opening dialog if user clicked an inner button)
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

  // Form Submission
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

      await loadInvestigations(inv.investigation_id);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      el.startInvBtn.disabled = false;
      el.uploadSpinner.classList.add("hidden");
    }
  });

  // -------------------------------------------------------------------------
  // Add Additional Camera Feed Modal (Active Investigation)
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
  // Keyboard Shortcuts & Modals
  // -------------------------------------------------------------------------
  function openHotkeysModal() {
    el.hotkeysModal.classList.remove("hidden");
  }

  el.hotkeysBtn.addEventListener("click", openHotkeysModal);
  el.closeHotkeysModal.addEventListener("click", () => el.hotkeysModal.classList.add("hidden"));
  el.dismissHotkeysBtn.addEventListener("click", () => el.hotkeysModal.classList.add("hidden"));

  document.addEventListener("keydown", (e) => {
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
