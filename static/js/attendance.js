/**
 * attendance.js  (Phase 2 — Premium Rebuild)
 * -------------------------------------------
 * Handles browser getUserMedia camera stream, extracts frames,
 * sends them to the server for YOLOv11n + ArcFace + MiniFASNet
 * detection, and renders bounding boxes + recognition events.
 *
 * Architecture:
 *   - processFrameLoop()  → runs every rAF, draws video + overlays
 *   - detectCurrentFrame() → throttled to CAMERA_FPS, sends to server
 *   - updateLiveStats()   → polls /api/attendance/live every 3s
 *   - addEventToLog()     → inserts a new event card into the activity log
 *   - updateLastRecognized() → updates the "Last Recognized" card
 */

'use strict';

/* ── roundRect polyfill for older browsers ───────────────────────────────── */
if (!CanvasRenderingContext2D.prototype.roundRect) {
    CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
        const radius = Math.min(r || 0, Math.abs(w) / 2, Math.abs(h) / 2);
        this.beginPath();
        this.moveTo(x + radius, y);
        this.arcTo(x + w, y, x + w, y + h, radius);
        this.arcTo(x + w, y + h, x, y + h, radius);
        this.arcTo(x, y + h, x, y, radius);
        this.arcTo(x, y, x + w, y, radius);
        this.closePath();
        return this;
    };
}

/* ── Configuration ───────────────────────────────────────────────────────── */
const FPS = window.CAMERA_FPS || 10;
const FRAME_INTERVAL_MS = 1000 / FPS;
const STATS_POLL_INTERVAL_MS = 3000;
const MAX_LOG_EVENTS = 50;

const API = {
    PROCESS_FRAME : '/api/attendance/process-frame',
    LIVE_STATS    : '/api/attendance/live',
};

/* ── State ───────────────────────────────────────────────────────────────── */
const state = {
    stream          : null,
    isActive        : false,
    isProcessing    : false,
    animationId     : null,
    lastFrameTime   : 0,
    currentDetections: [],
    // Session counters
    framesSentCount : 0,
    facesFoundCount : 0,
    markedTodayCount: 0,
    rejectedCount   : 0,
    eventCount      : 0,
    // FPS tracking
    fpsFrameCount   : 0,
    fpsLastTime     : performance.now(),
};

/* ── DOM References ──────────────────────────────────────────────────────── */
const $  = (id) => document.getElementById(id);

const startBtn          = $('startBtn');
const stopBtn           = $('stopBtn');
const cameraStatusText  = $('cameraStatusText');
const videoPlaceholder  = $('videoPlaceholder');
const liveIndicator     = $('liveIndicator');
const sessionBadge      = $('sessionBadge');
const sessionDot        = $('sessionDot');
const sessionLabel      = $('sessionLabel');

const videoEl           = $('webcamVideo');
const captureCanvas     = $('captureCanvas');
const displayCanvas     = $('displayCanvas');

const objectCount       = $('objectCount');
const currentTimeEl     = $('currentTime');
const fpsDisplay        = $('fpsDisplay');

// Footer counters
const framesSentEl      = $('framesSent');
const facesFoundEl      = $('facesFound');
const markedTodayEl     = $('markedToday');
const rejectedCountEl   = $('rejectedCount');

// Last recognized
const lastRecognizedCard = $('lastRecognizedCard');
const lrAvatar          = $('lrAvatar');
const lrName            = $('lrName');
const lrMeta            = $('lrMeta');
const lrBadge           = $('lrBadge');

// Liveness panel
const livenessPanel     = $('livenessPanel');
const livenessBar       = $('livenessBar');
const livenessVal       = $('livenessVal');
const confBar           = $('confBar');
const confVal           = $('confVal');
const spoofChip         = $('spoofChip');

// Event log
const eventLog          = $('eventLog');
const eventEmpty        = $('eventEmpty');
const eventsCount       = $('eventsCount');
const clearEventsBtn    = $('clearEventsBtn');

// Stats
const livePresentCount  = $('livePresentCount');
const liveAbsentCount   = $('liveAbsentCount');
const liveTotalCount    = $('liveTotalCount');
const liveAttPct        = $('liveAttPct');
const donutPct          = $('donutPct');
const latestAttendeesList = $('latestAttendeesList');
const refreshStatsBtn   = $('refreshStatsBtn');

/* ── Mini Donut Chart (Chart.js) ─────────────────────────────────────────── */
let donutChart = null;

function initDonut() {
    const canvas = $('miniDonut');
    if (!canvas || !window.Chart) return;

    donutChart = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [0, 100],
                backgroundColor: [
                    'rgba(34, 197, 94, 0.85)',
                    'rgba(255, 255, 255, 0.06)',
                ],
                borderWidth: 0,
                hoverOffset: 0,
            }]
        },
        options: {
            cutout: '72%',
            animation: { duration: 600, easing: 'easeInOutQuart' },
            plugins: { legend: { display: false }, tooltip: { enabled: false } },
            events: [],
        }
    });
}
initDonut();

function updateDonut(present, total) {
    const absent = Math.max(0, total - present);
    const pct    = total > 0 ? Math.round((present / total) * 100) : 0;

    if (donutChart) {
        donutChart.data.datasets[0].data = [present, absent];
        donutChart.update();
    }
    if (donutPct) donutPct.textContent = `${pct}%`;
}

/* ── Camera Controls ─────────────────────────────────────────────────────── */
async function startCamera() {
    try {
        startBtn.disabled = true;
        cameraStatusText.textContent = 'Requesting camera access…';

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
            audio: false,
        });

        state.stream   = stream;
        videoEl.srcObject = stream;

        videoEl.onloadedmetadata = () => {
            const w = videoEl.videoWidth;
            const h = videoEl.videoHeight;

            captureCanvas.width  = w;
            captureCanvas.height = h;
            displayCanvas.width  = w;
            displayCanvas.height = h;

            // Show canvas, hide placeholder
            videoPlaceholder.classList.add('d-none');
            displayCanvas.classList.remove('d-none');
            liveIndicator.classList.remove('d-none');

            // Toggle buttons
            startBtn.classList.add('d-none');
            stopBtn.classList.remove('d-none');
            startBtn.disabled = false;

            // Update session indicator
            sessionBadge.classList.add('active');
            sessionDot.classList.add('active');
            sessionLabel.textContent = 'Session Active';
            cameraStatusText.innerHTML =
                '<i class="bi bi-circle-fill me-1 text-success" style="font-size:0.55rem; vertical-align:middle;"></i> Camera active – running AI detection';

            state.isActive = true;

            // Reset counters
            state.framesSentCount = state.facesFoundCount = 0;
            state.markedTodayCount = state.rejectedCount = 0;
            updateFooterCounters();

            // Start loops
            state.fpsLastTime  = performance.now();
            state.fpsFrameCount = 0;
            requestAnimationFrame(processFrameLoop);
        };

    } catch (err) {
        startBtn.disabled = false;
        console.error('Camera error:', err);
        cameraStatusText.innerHTML =
            '<i class="bi bi-exclamation-circle me-1 text-danger"></i> Camera access denied or unavailable.';
        window.SmartAttend?.error('Camera Error', 'Could not access the webcam.');
    }
}

function stopCamera() {
    state.isActive = false;

    if (state.animationId) {
        cancelAnimationFrame(state.animationId);
        state.animationId = null;
    }
    if (state.stream) {
        state.stream.getTracks().forEach(t => t.stop());
        state.stream = null;
    }

    videoEl.srcObject = null;
    displayCanvas.classList.add('d-none');
    videoPlaceholder.classList.remove('d-none');
    liveIndicator.classList.add('d-none');

    stopBtn.classList.add('d-none');
    startBtn.classList.remove('d-none');

    sessionBadge.classList.remove('active');
    sessionDot.classList.remove('active');
    sessionLabel.textContent = 'Session Offline';
    cameraStatusText.innerHTML =
        '<i class="bi bi-circle-fill me-1 text-danger" style="font-size:0.55rem; vertical-align:middle;"></i> Camera offline';
    objectCount.textContent = '0';
    fpsDisplay.textContent  = '0';

    // Clear canvas
    const ctx = displayCanvas.getContext('2d');
    ctx.clearRect(0, 0, displayCanvas.width, displayCanvas.height);

    addEventToLog({ label: 'Session ended', color: 'gray', conf: null });
}

/* ── Main Frame Loop ─────────────────────────────────────────────────────── */
function processFrameLoop(timestamp) {
    if (!state.isActive) return;

    const dCtx = displayCanvas.getContext('2d');
    const w = displayCanvas.width;
    const h = displayCanvas.height;

    // Draw video frame continuously (smooth 30-60fps display)
    dCtx.drawImage(videoEl, 0, 0, w, h);

    // Overlay latest detections
    if (state.currentDetections.length > 0) {
        drawDetections(state.currentDetections, dCtx);
    }

    // FPS counter
    state.fpsFrameCount++;
    const now = performance.now();
    if (now - state.fpsLastTime >= 1000) {
        fpsDisplay.textContent = state.fpsFrameCount;
        state.fpsFrameCount = 0;
        state.fpsLastTime = now;
    }

    // Throttle server calls to target FPS
    if (timestamp - state.lastFrameTime >= FRAME_INTERVAL_MS && !state.isProcessing) {
        state.lastFrameTime = timestamp;
        detectCurrentFrame();
    }

    state.animationId = requestAnimationFrame(processFrameLoop);
}

/* ── Frame Detection ─────────────────────────────────────────────────────── */
async function detectCurrentFrame() {
    state.isProcessing = true;
    state.framesSentCount++;
    updateFooterCounters();

    try {
        const captureCtx = captureCanvas.getContext('2d');
        captureCtx.drawImage(videoEl, 0, 0, captureCanvas.width, captureCanvas.height);
        const frameB64 = captureCanvas.toDataURL('image/jpeg', 0.75);

        const res = await fetch(API.PROCESS_FRAME, {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ frame: frameB64 }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const data = await res.json();

        if (data.success && data.detections) {
            const dets = data.detections;
            state.currentDetections = dets;

            objectCount.textContent = dets.length;

            // Count faces detected in this frame
            const faceCount = dets.filter(d => d.label !== 'No Face Visible').length;
            if (faceCount > 0) {
                state.facesFoundCount += faceCount;
            }

            // Process each detection for UI updates
            let bestDet = null;
            let bestScore = -1;

            dets.forEach(det => {
                const sc = det.similarity || 0;

                // Track events: attendance marked
                if (det.status_color === 'green' && det.student_id) {
                    addEventToLog({ label: det.label, color: 'green', conf: det.similarity });
                    if (!det.label.includes('Verifying')) {
                        state.markedTodayCount++;
                    }
                } else if (det.status_color === 'yellow' && det.student_id) {
                    // Verifying — don't spam the log
                } else if (det.status_color === 'red') {
                    addEventToLog({ label: det.label || 'Unknown / Spoof', color: 'red', conf: null });
                    state.rejectedCount++;
                }

                if (sc > bestScore) {
                    bestScore = sc;
                    bestDet = det;
                }
            });

            if (bestDet) {
                updateLastRecognized(bestDet);
            }

            updateFooterCounters();
        } else {
            state.currentDetections = [];
        }
    } catch (err) {
        console.error('Detection error:', err);
    } finally {
        state.isProcessing = false;
    }
}

/* ── Draw Detections on Canvas ───────────────────────────────────────────── */
function drawDetections(detections, ctx) {
    detections.forEach(det => {
        const [x, y, w, h] = det.bbox;

        const colorMap = {
            green  : '#22c55e',
            yellow : '#f59e0b',
            red    : '#ef4444',
            blue   : '#6366f1',
            gray   : '#9ca3af',
        };
        const colorHex = colorMap[det.status_color] || '#9ca3af';

        // ── Bounding Box ──
        ctx.strokeStyle = colorHex;
        ctx.lineWidth   = 2.5;
        ctx.shadowBlur  = 8;
        ctx.shadowColor = colorHex;
        ctx.strokeRect(x, y, w, h);
        ctx.shadowBlur  = 0;

        // ── Corner Brackets (premium feel) ──
        const cs = Math.min(w, h) * 0.18; // corner size
        ctx.strokeStyle = colorHex;
        ctx.lineWidth   = 3;
        // top-left
        ctx.beginPath(); ctx.moveTo(x, y + cs); ctx.lineTo(x, y); ctx.lineTo(x + cs, y); ctx.stroke();
        // top-right
        ctx.beginPath(); ctx.moveTo(x + w - cs, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + cs); ctx.stroke();
        // bottom-left
        ctx.beginPath(); ctx.moveTo(x, y + h - cs); ctx.lineTo(x, y + h); ctx.lineTo(x + cs, y + h); ctx.stroke();
        // bottom-right
        ctx.beginPath(); ctx.moveTo(x + w - cs, y + h); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w, y + h - cs); ctx.stroke();

        // ── Label ──
        let label = det.label || '';
        if (det.similarity) {
            label += ` · ${(det.similarity * 100).toFixed(0)}%`;
        }

        ctx.font = 'bold 12px Inter, sans-serif';
        const tw = ctx.measureText(label).width;
        const lh = 22;
        const lx = x;
        const ly = y > lh + 4 ? y - lh - 4 : y + h + 4;

        // Label background
        ctx.fillStyle = colorHex;
        ctx.beginPath();
        ctx.roundRect(lx, ly, tw + 12, lh, 4);
        ctx.fill();

        // Label text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(label, lx + 6, ly + 15);

        // ── Liveness sub-label ──
        let slY = ly === y - lh - 4 ? y + h + 4 : ly - lh - 4;
        
        if (det.liveness_score !== undefined && det.spoof_probability !== undefined) {
            const livePct  = (det.liveness_score * 100).toFixed(0);
            const subLabel = `Live: ${livePct}%`;

            ctx.font = '11px Inter, sans-serif';
            const stw = ctx.measureText(subLabel).width;

            ctx.fillStyle = 'rgba(0,0,0,0.65)';
            ctx.beginPath();
            ctx.roundRect(lx, slY, stw + 12, 18, 3);
            ctx.fill();

            const liveOk = det.liveness_score >= 0.6;
            ctx.fillStyle = liveOk ? '#4ade80' : '#f87171';
            ctx.fillText(subLabel, lx + 6, slY + 13);
            
            // Advance Y position for 2FA label if we drew this on top/bottom
            if (ly === y - lh - 4) slY += 22; // drawing below
            else slY -= 22; // drawing above
        }
        
        // ── 2FA sub-label ──
        if (det.two_factor_verified) {
            const twoFaLabel = `✅ 2FA Passed`;
            ctx.font = 'bold 11px Inter, sans-serif';
            const tfw = ctx.measureText(twoFaLabel).width;
            
            ctx.fillStyle = 'rgba(0,0,0,0.75)';
            ctx.beginPath();
            ctx.roundRect(lx, slY, tfw + 12, 18, 3);
            ctx.fill();
            
            ctx.fillStyle = '#10b981';
            ctx.fillText(twoFaLabel, lx + 6, slY + 13);
        }
    });
}

/* ── Update "Last Recognized" Card ──────────────────────────────────────── */
function updateLastRecognized(det) {
    const name  = det.label || 'Unknown';
    const conf  = det.similarity ? (det.similarity * 100).toFixed(1) : null;
    const sid   = det.student_id || '—';
    const color = det.status_color || 'gray';

    // Avatar initial
    const initial = name.charAt(0).toUpperCase();
    lrAvatar.textContent = initial;

    // Color avatar
    const gradMap = {
        green  : 'linear-gradient(135deg, #16a34a, #22c55e)',
        yellow : 'linear-gradient(135deg, #b45309, #f59e0b)',
        red    : 'linear-gradient(135deg, #b91c1c, #ef4444)',
        gray   : 'linear-gradient(135deg, #374151, #6b7280)',
    };
    lrAvatar.style.background = gradMap[color] || gradMap.gray;

    lrName.textContent = name.replace(/\s*\(.*\)$/, ''); // strip status suffix
    lrMeta.textContent = `ID: ${sid}${conf ? ` · ${conf}% match` : ''}`;

    // Badge
    lrBadge.className = 'att-lr-badge';
    if (color === 'green') {
        lrBadge.textContent = '✓ Marked';
        lrBadge.classList.add('marked');
    } else if (color === 'yellow') {
        lrBadge.textContent = '⏱ Verifying';
        lrBadge.classList.add('verifying');
    } else if (color === 'red') {
        lrBadge.textContent = '✗ Rejected';
        lrBadge.classList.add('spoof');
    } else {
        lrBadge.textContent = '? Unknown';
        lrBadge.classList.add('unknown');
    }

    lastRecognizedCard.classList.remove('d-none');

    // Liveness panel
    if (det.liveness_score !== undefined) {
        const lPct   = Math.round(det.liveness_score * 100);
        const cPct   = conf ? Math.round(parseFloat(conf)) : 0;
        const isSpoof = det.status_color === 'red' && det.spoof_type && det.spoof_type !== 'unknown_face';

        livenessBar.style.width  = `${lPct}%`;
        livenessVal.textContent  = `${lPct}%`;
        confBar.style.width      = `${cPct}%`;
        confVal.textContent      = `${cPct}%`;

        if (isSpoof) {
            spoofChip.innerHTML   = '<i class="bi bi-exclamation-triangle-fill me-1"></i>Spoof';
            spoofChip.className   = 'att-spoof-chip spoof';
        } else {
            spoofChip.innerHTML   = '<i class="bi bi-check-circle-fill me-1"></i>Genuine';
            spoofChip.className   = 'att-spoof-chip';
        }

        livenessPanel.classList.remove('d-none');
    }
}

/* ── Event Log ───────────────────────────────────────────────────────────── */
function addEventToLog({ label, color = 'gray', conf = null }) {
    // Throttle: don't add duplicate verifying events
    const existing = eventLog.querySelector('.att-event-item');
    if (existing) {
        const lastLabel = existing.querySelector('.att-ev-label')?.textContent;
        if (lastLabel === label && color === 'yellow') return;
    }

    state.eventCount++;

    // Remove empty state
    eventEmpty?.remove();

    const confText = conf !== null ? `${(conf * 100).toFixed(0)}%` : '';
    const now      = new Date().toLocaleTimeString('en-US', { hour12: false });

    const item = document.createElement('div');
    item.className = `att-event-item ev-${color}`;
    item.innerHTML = `
      <div class="att-ev-dot"></div>
      <div class="att-ev-body">
        <div class="att-ev-label">${escHtml(label)}</div>
        <div class="att-ev-time">${now}</div>
      </div>
      ${confText ? `<div class="att-ev-conf">${confText}</div>` : ''}
    `;

    // Prepend (newest on top)
    eventLog.insertBefore(item, eventLog.firstChild);

    // Trim log
    const items = eventLog.querySelectorAll('.att-event-item');
    if (items.length > MAX_LOG_EVENTS) {
        items[items.length - 1].remove();
    }

    eventsCount.textContent = `${state.eventCount} events`;
}

function clearEvents() {
    eventLog.innerHTML = `
      <div class="att-event-empty" id="eventEmpty">
        <i class="bi bi-hourglass"></i>
        <p>Waiting for detections…</p>
      </div>
    `;
    state.eventCount = 0;
    eventsCount.textContent = '0 events';
}

/* ── Footer Counters ─────────────────────────────────────────────────────── */
function updateFooterCounters() {
    if (framesSentEl)   framesSentEl.textContent   = state.framesSentCount;
    if (facesFoundEl)   facesFoundEl.textContent   = state.facesFoundCount;
    if (markedTodayEl)  markedTodayEl.textContent  = state.markedTodayCount;
    if (rejectedCountEl) rejectedCountEl.textContent = state.rejectedCount;
}

/* ── Live Stats Polling ──────────────────────────────────────────────────── */
async function updateLiveStats() {
    try {
        const res = await fetch(API.LIVE_STATS);
        if (!res.ok) return;
        const data = await res.json();

        const present = data.present || 0;
        const total   = data.total   || 0;
        const absent  = Math.max(0, total - present);
        const pct     = total > 0 ? Math.round((present / total) * 100) : 0;

        if (livePresentCount) livePresentCount.textContent = present;
        if (liveAbsentCount)  liveAbsentCount.textContent  = absent;
        if (liveTotalCount)   liveTotalCount.textContent   = total;
        if (liveAttPct)       liveAttPct.textContent       = `${pct}%`;

        updateDonut(present, total);

        // Present list
        if (data.latest && data.latest.length > 0) {
            latestAttendeesList.innerHTML = data.latest.map(r => `
              <div class="att-present-item">
                <div class="att-pi-avatar">${(r.student_name || '?').charAt(0)}</div>
                <div>
                  <div class="att-pi-name">${escHtml(r.student_name || '—')}</div>
                  <div class="att-pi-meta">${escHtml(r.student_id || '—')}</div>
                </div>
                <div class="att-pi-time">${r.time || '—'}</div>
              </div>
            `).join('');
        } else {
            latestAttendeesList.innerHTML = `
              <div class="att-event-empty">
                <i class="bi bi-person-check"></i>
                <p>No attendance recorded yet.</p>
              </div>
            `;
        }
    } catch (err) {
        console.error('Stats fetch failed:', err);
    }
}

/* ── Utility: HTML Escape ────────────────────────────────────────────────── */
function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

/* ── Clock ───────────────────────────────────────────────────────────────── */
function updateClock() {
    if (currentTimeEl) {
        currentTimeEl.textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
    }
}

/* ── Event Listeners ─────────────────────────────────────────────────────── */
startBtn?.addEventListener('click', startCamera);
stopBtn?.addEventListener('click', stopCamera);
clearEventsBtn?.addEventListener('click', clearEvents);
refreshStatsBtn?.addEventListener('click', updateLiveStats);
window.addEventListener('beforeunload', stopCamera);

/* ── Start polling + clock ───────────────────────────────────────────────── */
updateLiveStats(); // initial load
setInterval(updateLiveStats, STATS_POLL_INTERVAL_MS);
setInterval(updateClock, 1000);
