/**
 * security.js
 * -----------
 * JavaScript for the SmartAttend Security Dashboard.
 * Handles live stats polling, alerts feed, settings, and log table.
 */

'use strict';

const SEC_API = {
    STATS:    '/api/security/stats',
    ALERTS:   '/api/security/alerts',
    LOGS:     '/api/security/logs',
    SETTINGS: '/api/security/settings',
};

const secState = {
    currentPage: 1,
    totalPages: 1,
};

// ─── DOM Elements ─────────────────────────────────────────────────────────────

const statTotalChecks = document.getElementById('statTotalChecks');
const statAccepted    = document.getElementById('statAccepted');
const statRejected    = document.getElementById('statRejected');
const statSpoofRate   = document.getElementById('statSpoofRate');
const spoofTypeBreakdown = document.getElementById('spoofTypeBreakdown');

const alertsFeed  = document.getElementById('alertsFeed');
const alertCount  = document.getElementById('alertCount');

const logsTableBody    = document.getElementById('logsTableBody');
const logsPaginationInfo = document.getElementById('logsPaginationInfo');
const logsPrevBtn      = document.getElementById('logsPrevBtn');
const logsNextBtn      = document.getElementById('logsNextBtn');

const filterType     = document.getElementById('filterType');
const filterDecision = document.getElementById('filterDecision');

const settingLiveness    = document.getElementById('settingLiveness');
const settingSpoof       = document.getElementById('settingSpoof');
const settingRecognition = document.getElementById('settingRecognition');
const settingLivenessVal    = document.getElementById('settingLivenessVal');
const settingSpoofVal       = document.getElementById('settingSpoofVal');
const settingRecognitionVal = document.getElementById('settingRecognitionVal');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');

// ─── Stats Polling ────────────────────────────────────────────────────────────

async function fetchStats() {
    try {
        const res = await fetch(SEC_API.STATS);
        if (!res.ok) return;
        const data = await res.json();

        statTotalChecks.textContent = data.total_checks || 0;
        statAccepted.textContent    = data.accepted || 0;
        statRejected.textContent    = data.rejected || 0;

        const total = data.total_checks || 0;
        const rate = total > 0 ? ((data.rejected / total) * 100).toFixed(1) : '0.0';
        statSpoofRate.textContent = `${rate}%`;

        // Spoof type breakdown
        const types = data.spoof_types || {};
        if (Object.keys(types).length > 0) {
            spoofTypeBreakdown.innerHTML = Object.entries(types)
                .map(([type, count]) => {
                    const icon = getSpoofIcon(type);
                    const color = getSpoofColor(type);
                    return `
                        <div class="spoof-type-row">
                            <div class="d-flex align-items-center">
                                <i class="bi ${icon} me-2" style="color: ${color};"></i>
                                <span class="spoof-type-label">${formatSpoofType(type)}</span>
                            </div>
                            <span class="spoof-type-count" style="color: ${color};">${count}</span>
                        </div>`;
                }).join('');
        } else {
            spoofTypeBreakdown.innerHTML = '<div class="text-muted small text-center py-3">No data yet.</div>';
        }
    } catch (err) {
        console.error('Failed to fetch security stats:', err);
    }
}

// ─── Alerts Feed ──────────────────────────────────────────────────────────────

async function fetchAlerts() {
    try {
        const res = await fetch(`${SEC_API.ALERTS}?limit=15`);
        if (!res.ok) return;
        const data = await res.json();
        const alerts = data.alerts || [];

        alertCount.textContent = `${alerts.length} alert${alerts.length !== 1 ? 's' : ''}`;

        if (alerts.length === 0) {
            alertsFeed.innerHTML = '<div class="text-center text-muted small py-4">No spoof attempts detected.</div>';
            return;
        }

        alertsFeed.innerHTML = alerts.map(a => {
            const icon = getSpoofIcon(a.spoof_type);
            const color = getSpoofColor(a.spoof_type);
            const time = a.timestamp ? new Date(a.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour12: false, hour: '2-digit', minute: '2-digit' }) : '—';
            const name = a.student_name || 'Unknown';

            return `
                <div class="alert-row">
                    <div class="alert-icon" style="background: ${color}20; color: ${color};">
                        <i class="bi ${icon}"></i>
                    </div>
                    <div class="alert-body">
                        <div class="alert-title">${formatSpoofType(a.spoof_type)}</div>
                        <div class="alert-meta">
                            ${name} · Liveness: ${(a.liveness_score * 100).toFixed(0)}% · ${time}
                        </div>
                    </div>
                    <span class="decision-badge rejected">Rejected</span>
                </div>`;
        }).join('');
    } catch (err) {
        console.error('Failed to fetch alerts:', err);
    }
}

// ─── Logs Table ───────────────────────────────────────────────────────────────

async function fetchLogs(page = 1) {
    try {
        const typeFilter     = filterType.value;
        const decisionFilter = filterDecision.value;

        let url = `${SEC_API.LOGS}?page=${page}&per_page=15`;
        if (typeFilter)     url += `&type=${typeFilter}`;
        if (decisionFilter) url += `&decision=${decisionFilter}`;

        const res = await fetch(url);
        if (!res.ok) return;
        const data = await res.json();

        secState.currentPage = data.page;
        secState.totalPages  = data.pages;

        logsPaginationInfo.textContent = `Page ${data.page} of ${data.pages || 1} (${data.total} records)`;
        logsPrevBtn.disabled = data.page <= 1;
        logsNextBtn.disabled = data.page >= data.pages;

        const logs = data.logs || [];
        if (logs.length === 0) {
            logsTableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No logs found.</td></tr>';
            return;
        }

        logsTableBody.innerHTML = logs.map(log => {
            const time = log.timestamp ? new Date(log.timestamp).toLocaleString('en-US', {
                month: 'short', day: 'numeric', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
            }) : '—';
            const name = log.student_name || log.student_id || 'Unknown';
            const typeColor = getSpoofColor(log.spoof_type);
            const decClass = log.decision === 'accepted' ? 'accepted' : 'rejected';
            
            let snapshotHtml = '<span class="text-muted small">—</span>';
            if (log.snapshot_path) {
                // Fix Windows backslashes which can cause invalid escape sequence errors in JS event handlers
                const safePath = log.snapshot_path.replace(/\\/g, '/');
                snapshotHtml = `<img src="/api/security/uploads/${safePath}" alt="Snapshot" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px; cursor: pointer;" onerror="this.onerror=null; this.outerHTML='<span class=\\'text-muted small\\' title=\\'Image deleted\\'>—</span>';" onclick="window.open('/api/security/uploads/${safePath}', '_blank')">`;
            }

            return `
                <tr>
                    <td>${time}</td>
                    <td>${snapshotHtml}</td>
                    <td>${name}</td>
                    <td><span style="color: ${typeColor};">${formatSpoofType(log.spoof_type)}</span></td>
                    <td>${(log.liveness_score * 100).toFixed(0)}%</td>
                    <td>${(log.spoof_probability * 100).toFixed(0)}%</td>
                    <td><span class="decision-badge ${decClass}">${log.decision}</span></td>
                </tr>`;
        }).join('');
    } catch (err) {
        console.error('Failed to fetch logs:', err);
    }
}

// ─── Settings ─────────────────────────────────────────────────────────────────

async function loadSettings() {
    try {
        const res = await fetch(SEC_API.SETTINGS);
        if (!res.ok) return;
        const data = await res.json();

        settingLiveness.value    = Math.round((data.liveness_threshold || 0.6) * 100);
        settingSpoof.value       = Math.round((data.spoof_threshold || 0.4) * 100);
        settingRecognition.value = Math.round((data.recognition_threshold || 0.5) * 100);

        updateSliderLabels();
    } catch (err) {
        console.error('Failed to load settings:', err);
    }
}

function updateSliderLabels() {
    settingLivenessVal.textContent    = (settingLiveness.value / 100).toFixed(2);
    settingSpoofVal.textContent       = (settingSpoof.value / 100).toFixed(2);
    settingRecognitionVal.textContent = (settingRecognition.value / 100).toFixed(2);
}

async function saveSettings() {
    try {
        const body = {
            liveness_threshold:    settingLiveness.value / 100,
            spoof_threshold:       settingSpoof.value / 100,
            recognition_threshold: settingRecognition.value / 100,
        };

        const res = await fetch(SEC_API.SETTINGS, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (res.ok) {
            window.SmartAttend?.success('Settings Saved', 'Anti-spoof thresholds updated.');
        } else {
            window.SmartAttend?.error('Error', 'Failed to save settings.');
        }
    } catch (err) {
        console.error('Settings save error:', err);
    }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatSpoofType(type) {
    const map = {
        'genuine':       'Genuine',
        'printed_photo': 'Printed Photo',
        'screen_replay': 'Screen Replay',
        'static_image':  'Static Image',
        'occlusion':     'Occlusion',
        'unknown':       'Unknown',
        'unknown_face':  'Unknown Face',
        'invalid_crop':  'Invalid Crop',
        'invalid_input': 'Invalid Input',
        'face_too_small':'Face Too Small',
    };
    return map[type] || type;
}

function getSpoofIcon(type) {
    const map = {
        'genuine':       'bi-check-circle-fill',
        'printed_photo': 'bi-image-fill',
        'screen_replay': 'bi-display-fill',
        'static_image':  'bi-pause-circle-fill',
        'occlusion':     'bi-eye-slash-fill',
        'unknown_face':  'bi-person-bounding-box',
    };
    return map[type] || 'bi-question-circle-fill';
}

function getSpoofColor(type) {
    const map = {
        'genuine':       '#22c55e',
        'printed_photo': '#ef4444',
        'screen_replay': '#f59e0b',
        'static_image':  '#a855f7',
        'occlusion':     '#f97316',
        'unknown_face':  '#3b82f6',
    };
    return map[type] || '#64748b';
}

// ─── Event Listeners ──────────────────────────────────────────────────────────

settingLiveness.addEventListener('input', updateSliderLabels);
settingSpoof.addEventListener('input', updateSliderLabels);
settingRecognition.addEventListener('input', updateSliderLabels);
saveSettingsBtn.addEventListener('click', saveSettings);

filterType.addEventListener('change', () => fetchLogs(1));
filterDecision.addEventListener('change', () => fetchLogs(1));
logsPrevBtn.addEventListener('click', () => fetchLogs(secState.currentPage - 1));
logsNextBtn.addEventListener('click', () => fetchLogs(secState.currentPage + 1));

// ─── Init ─────────────────────────────────────────────────────────────────────

loadSettings();
fetchStats();
fetchAlerts();
fetchLogs(1);

// Poll every 3 seconds
setInterval(() => {
    fetchStats();
    fetchAlerts();
    fetchLogs(secState.currentPage);
}, 3000);
