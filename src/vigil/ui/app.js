/**
 * VIGIL Video Forensics Mission Control - Interactive Application Logic
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
    mediaAsset: null,
    ws: null,
    activeFilter: "all",
    selectedFile: null,
  };

  // DOM Elements
  const el = {
    invSelect: document.getElementById("invSelect"),
    refreshInvBtn: document.getElementById("refreshInvBtn"),
    caseStatusBadge: document.getElementById("caseStatusBadge"),
    wsIndicator: document.getElementById("wsIndicator"),
    wsLabel: document.getElementById("wsLabel"),
    newInvBtn: document.getElementById("newInvBtn"),
    placeholderUploadBtn: document.getElementById("placeholderUploadBtn"),
    exportMenuBtn: document.getElementById("exportMenuBtn"),
    exportMenu: document.getElementById("exportMenu"),
    exportPdfBtn: document.getElementById("exportPdfBtn"),
    exportHtmlBtn: document.getElementById("exportHtmlBtn"),
    exportMdBtn: document.getElementById("exportMdBtn"),
    finalizeReportBtn: document.getElementById("finalizeReportBtn"),
    telemetryFeed: document.getElementById("telemetryFeed"),
    telemetryCount: document.getElementById("telemetryCount"),
    mainVideoPlayer: document.getElementById("mainVideoPlayer"),
    videoPlaceholder: document.getElementById("videoPlaceholder"),
    currentTimeDisplay: document.getElementById("currentTimeDisplay"),
    durationDisplay: document.getElementById("durationDisplay"),
    seekBackBtn: document.getElementById("seekBackBtn"),
    playPauseBtn: document.getElementById("playPauseBtn"),
    seekFwdBtn: document.getElementById("seekFwdBtn"),
    sourceMetaText: document.getElementById("sourceMetaText"),
    timelineTrack: document.getElementById("timelineTrack"),
    timelineProgress: document.getElementById("timelineProgress"),
    timelineMarkersContainer: document.getElementById("timelineMarkersContainer"),
    timelineSpanLabel: document.getElementById("timelineSpanLabel"),
    mediaTabs: document.getElementById("mediaTabs"),
    clipsGalleryView: document.getElementById("clipsGalleryView"),
    clipsGrid: document.getElementById("clipsGrid"),
    clipsCount: document.getElementById("clipsCount"),
    clipsEmptyNotice: document.getElementById("clipsEmptyNotice"),
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
    toastContainer: document.getElementById("toastContainer"),
  };

  // -------------------------------------------------------------------------
  // Notifications & Utilities
  // -------------------------------------------------------------------------
  function showToast(msg, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    el.toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  function formatTime(seconds) {
    if (isNaN(seconds) || seconds === null) return "00:00.00";
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(2);
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(5, "0")}`;
  }

  // -------------------------------------------------------------------------
  // API Fetch Utilities
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
  // Investigation Management
  // -------------------------------------------------------------------------
  async function loadInvestigations() {
    try {
      const items = await apiFetch("/api/v1/investigations");
      state.investigations = items;
      el.invSelect.innerHTML = "";

      if (items.length === 0) {
        el.invSelect.innerHTML = `<option value="" disabled selected>No investigations registered</option>`;
        updateCaseStatus("NO CASES");
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
    connectWebSocket(invId);
    refreshActiveCase();
  }

  async function refreshActiveCase() {
    if (!state.activeInvestigationId) return;
    const invId = state.activeInvestigationId;

    try {
      // 1. Fetch status
      const statusData = await apiFetch(`/api/v1/investigations/${invId}/status`);
      state.status = statusData;
      updateCaseStatus(statusData.status);

      // 2. Fetch full investigation details
      const invData = await apiFetch(`/api/v1/investigations/${invId}`);
      if (invData.media_asset_ids && invData.media_asset_ids.length > 0) {
        state.mediaAsset = { id: invData.media_asset_ids[0] };
      }

      // 3. Fetch events
      const eventsData = await apiFetch(`/api/v1/investigations/${invId}/events`);
      state.events = eventsData;
      renderEvents();
      renderTimelineMarkers();

      // 4. Fetch artifacts (frames and clips)
      const artifactsData = await apiFetch(`/api/v1/investigations/${invId}/artifacts`);
      state.artifacts = artifactsData;
      renderArtifacts();

      // 5. Fetch audit logs
      const auditData = await apiFetch(`/api/v1/investigations/${invId}/audit`);
      state.auditLogs = auditData;
      renderAuditLogs();

      // 6. Fetch evidence assessments
      renderAssessments();

      // 7. Load video in player if primary asset exists
      loadPrimaryVideo();

      // 8. Load report preview if available
      loadReportPreview();

    } catch (err) {
      console.warn("Error refreshing active case:", err);
    }
  }

  function updateCaseStatus(statusStr) {
    const s = (statusStr || "UNKNOWN").toLowerCase();
    el.caseStatusBadge.textContent = s.toUpperCase();
    el.caseStatusBadge.className = `status-pill status-${s}`;
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
      // Heartbeat ping every 25s
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

    // Refresh state on key milestones
    if (
      msg.event_type === "state_changed" ||
      msg.event_type === "event_correlated" ||
      msg.event_type === "event_reviewed" ||
      msg.event_type === "report_finalized" ||
      msg.event_type === "investigation_completed"
    ) {
      refreshActiveCase();
    }
  }

  function activateAgentChip(eventType) {
    const chips = {
      plan_created: "chip-planner",
      task_started: "chip-visual",
      observation_detected: "chip-visual",
      event_correlated: "chip-temporal",
      coverage_updated: "chip-verifier",
      report_finalized: "chip-reporter",
      investigation_completed: "chip-reporter",
    };

    const targetId = chips[eventType];
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

    // Keep log manageable
    const total = el.telemetryFeed.children.length;
    el.telemetryCount.textContent = `${total} events`;
    if (total > 60) el.telemetryFeed.removeChild(el.telemetryFeed.lastChild);
  }

  // -------------------------------------------------------------------------
  // Video Player & Controls
  // -------------------------------------------------------------------------
  function loadPrimaryVideo() {
    // Check if any video artifact exists
    const videoArtifact = state.artifacts.find(a => a.media_type === "video");
    if (videoArtifact) {
      playArtifact(videoArtifact.artifact_id);
    } else {
      el.videoPlaceholder.classList.remove("hidden");
    }
  }

  function playArtifact(artifactId) {
    const invId = state.activeInvestigationId;
    const streamUrl = `/api/v1/investigations/${invId}/artifacts/${artifactId}/content`;

    el.mainVideoPlayer.src = streamUrl;
    el.videoPlaceholder.classList.add("hidden");
    el.mainVideoPlayer.load();

    const art = state.artifacts.find(a => a.artifact_id === artifactId);
    if (art && art.sha256) {
      el.sourceMetaText.textContent = `SHA-256: ${art.sha256.slice(0, 16)}... | ${art.artifact_type.toUpperCase()}`;
    }
  }

  el.mainVideoPlayer.addEventListener("timeupdate", () => {
    const cur = el.mainVideoPlayer.currentTime;
    const dur = el.mainVideoPlayer.duration || 1;
    el.currentTimeDisplay.textContent = formatTime(cur);
    el.durationDisplay.textContent = formatTime(dur);

    const pct = Math.min(Math.max((cur / dur) * 100, 0), 100);
    el.timelineProgress.style.width = `${pct}%`;
  });

  el.mainVideoPlayer.addEventListener("loadedmetadata", () => {
    const dur = el.mainVideoPlayer.duration;
    el.durationDisplay.textContent = formatTime(dur);
    el.timelineSpanLabel.textContent = `0s – ${dur.toFixed(1)}s`;
    renderTimelineMarkers();
  });

  el.playPauseBtn.addEventListener("click", () => {
    if (el.mainVideoPlayer.paused) {
      el.mainVideoPlayer.play();
      el.playPauseBtn.innerHTML = "&#x23F8; Pause";
    } else {
      el.mainVideoPlayer.pause();
      el.playPauseBtn.innerHTML = "&#x25B6; Play";
    }
  });

  el.seekBackBtn.addEventListener("click", () => {
    el.mainVideoPlayer.currentTime = Math.max(0, el.mainVideoPlayer.currentTime - 2.0);
  });

  el.seekFwdBtn.addEventListener("click", () => {
    el.mainVideoPlayer.currentTime = Math.min(el.mainVideoPlayer.duration || 0, el.mainVideoPlayer.currentTime + 2.0);
  });

  el.timelineTrack.addEventListener("click", (e) => {
    const rect = el.timelineTrack.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = clickX / rect.width;
    if (el.mainVideoPlayer.duration) {
      el.mainVideoPlayer.currentTime = pct * el.mainVideoPlayer.duration;
    }
  });

  // -------------------------------------------------------------------------
  // Event Review Station & Timeline Markers (Phase 5)
  // -------------------------------------------------------------------------
  function renderTimelineMarkers() {
    el.timelineMarkersContainer.innerHTML = "";
    const duration = el.mainVideoPlayer.duration || 60.0;

    state.events.forEach((evt) => {
      if (evt.start_seconds !== null && evt.end_seconds !== null) {
        const left = (evt.start_seconds / duration) * 100;
        const width = Math.max(((evt.end_seconds - evt.start_seconds) / duration) * 100, 1.5);

        const marker = document.createElement("div");
        marker.className = `timeline-marker ${evt.status}`;
        marker.style.left = `${left}%`;
        marker.style.width = `${width}%`;
        marker.title = `${evt.event_type}: ${evt.description} (${evt.status.toUpperCase()})`;

        marker.addEventListener("click", (e) => {
          e.stopPropagation();
          el.mainVideoPlayer.currentTime = evt.start_seconds;
        });

        el.timelineMarkersContainer.appendChild(marker);
      }
    });
  }

  function renderEvents() {
    const filtered = state.events.filter((e) => {
      if (state.activeFilter === "all") return true;
      return e.status === state.activeFilter;
    });

    // Update counts
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
        ? `${evt.start_seconds.toFixed(1)}s – ${evt.end_seconds.toFixed(1)}s`
        : "-";

      let reviewNotesHtml = "";
      if (evt.reviewer || evt.review_notes) {
        reviewNotesHtml = `
          <div class="event-review-notes">
            <strong>${evt.reviewer || "Reviewer"}:</strong> ${evt.review_notes || "-"}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="event-card-head">
          <span class="event-card-type">${evt.event_type.replace(/_/g, " ").toUpperCase()}</span>
          <span class="status-pill status-${evt.status}">${evt.status}</span>
        </div>
        <div class="event-card-id">#${evt.event_id} &bull; Footage Interval: ${timeRange}</div>
        <div class="event-card-desc">${evt.description}</div>
        ${reviewNotesHtml}
        <div class="event-card-actions">
          <button class="btn btn-sm btn-confirm" data-id="${evt.event_id}">&#x2714; Confirm</button>
          <button class="btn btn-sm btn-reject" data-id="${evt.event_id}">&#x2716; Reject</button>
          <button class="btn btn-sm btn-edit" data-id="${evt.event_id}">&#x270E; Edit</button>
          <button class="btn btn-sm btn-outline btn-seek" data-time="${evt.start_seconds || 0}">&#x25B6; Jump</button>
        </div>
      `;

      // Button handlers
      card.querySelector(".btn-confirm").addEventListener("click", () => openReviewModal(evt, "confirmed"));
      card.querySelector(".btn-reject").addEventListener("click", () => openReviewModal(evt, "rejected"));
      card.querySelector(".btn-edit").addEventListener("click", () => openReviewModal(evt, evt.status));
      card.querySelector(".btn-seek").addEventListener("click", () => {
        if (evt.start_seconds !== null) el.mainVideoPlayer.currentTime = evt.start_seconds;
      });

      el.eventsList.appendChild(card);
    });
  }

  // Filter pills
  document.querySelectorAll(".filter-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.getAttribute("data-filter");
      renderEvents();
    });
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
    const clips = state.artifacts.filter(a => a.artifact_type in { clip: 1, subclip: 1, video_clip: 1 });

    el.framesCount.textContent = frames.length;
    el.clipsCount.textContent = clips.length;

    // Render Frames
    el.frameGallery.innerHTML = "";
    if (frames.length === 0) {
      el.frameGallery.innerHTML = `<div class="gallery-empty">No frames extracted yet.</div>`;
    } else {
      frames.forEach((f) => {
        const img = document.createElement("img");
        img.className = "frame-thumb";
        img.src = `/api/v1/investigations/${state.activeInvestigationId}/artifacts/${f.artifact_id}/content`;
        img.title = `Frame: ${f.artifact_id} (${f.source_reference.start_seconds}s)`;
        img.addEventListener("click", () => {
          if (f.source_reference.start_seconds !== null) {
            el.mainVideoPlayer.currentTime = f.source_reference.start_seconds;
          }
        });
        el.frameGallery.appendChild(img);
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
        card.innerHTML = `
          <div class="clip-card-title">&#x1F3AC; ${c.artifact_id}</div>
          <div class="clip-card-meta">Interval: ${sr.start_seconds?.toFixed(1)}s &ndash; ${sr.end_seconds?.toFixed(1)}s</div>
          <div class="clip-card-meta">SHA-256: <code>${(c.sha256 || "N/A").slice(0, 12)}...</code></div>
        `;
        card.addEventListener("click", () => playArtifact(c.artifact_id));
        el.clipsGrid.appendChild(card);
      });
    }
  }

  // Media tabs
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
  // Drawer & Tables (Assessments, Audit, Report)
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
      const changesStr = log.changes ? Object.entries(log.changes).map(([k, v]) => `${k}: ${v.old} &rarr; ${v.new}`).join(", ") : "-";
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

  async function renderAssessments() {
    try {
      const assessments = await apiFetch(`/api/v1/investigations/${state.activeInvestigationId}/coverage`);
      // Use as placeholder or query assessments
      el.assessmentsTable.innerHTML = `<tr><td colspan="5" style="text-align:center;">Coverage evaluated across ${assessments.length} segments.</td></tr>`;
    } catch {
      // Ignored
    }
  }

  async function loadReportPreview() {
    try {
      const report = await apiFetch(`/api/v1/investigations/${state.activeInvestigationId}/report`);
      el.reportPreviewBox.innerHTML = `
        <h4 style="color:#93c5fd; margin-bottom: 8px;">${report.title} (v${report.version} - ${report.status.toUpperCase()})</h4>
        <p style="margin-bottom: 8px; color:#e2e8f0; white-space:pre-line;">${report.summary}</p>
        <div style="font-size:0.75rem; color:#94a3b8;">
          <span>Generated by: ${report.generated_by} &bull; Finalized by: ${report.finalized_by || "Pending"}</span>
        </div>
      `;
    } catch {
      el.reportPreviewBox.innerHTML = `<div class="gallery-empty">Investigation still in progress or no report generated yet.</div>`;
    }
  }

  // -------------------------------------------------------------------------
  // Report Finalization & Deliverables Export (Phase 5)
  // -------------------------------------------------------------------------
  el.exportMenuBtn.addEventListener("click", () => el.exportMenu.classList.toggle("hidden"));
  document.addEventListener("click", (e) => {
    if (!el.exportDropdownWrap?.contains(e.target) && !el.exportMenuBtn.contains(e.target)) {
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

  el.invSelect.addEventListener("change", (e) => setActiveInvestigation(e.target.value));
  el.refreshInvBtn.addEventListener("click", () => {
    loadInvestigations();
    showToast("Case catalog refreshed");
  });

  // Initial Load
  loadInvestigations();
})();
