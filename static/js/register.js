/**
 * register.js  (v2 – Browser Camera)
 * ------------------------------------
 * Uses navigator.mediaDevices.getUserMedia() for camera access.
 * The server never opens the camera — the browser does.
 * Captured frames are sent to the server as base64 JPEG images.
 */

'use strict';

/* ═══════════════════════════════════════════════════════════════════════════
   CONSTANTS
═══════════════════════════════════════════════════════════════════════════ */
const API = {
  STUDENTS:        '/api/students',
  CAPTURE_START:   '/api/capture/start',
  UPLOAD_FRAME:    '/api/capture/upload-frame',
  CAPTURE_STATUS:  '/api/capture/status',
  CAPTURE_STOP:    '/api/capture/stop',
  CAPTURE_RESET:   '/api/capture/reset',
  EMBEDDING_GEN:   '/api/embedding/generate',
};

const TOTAL_FRAMES  = 15;    // target face images to capture
const SEND_INTERVAL = 250;  // ms between frame submissions

/* ═══════════════════════════════════════════════════════════════════════════
   STATE
═══════════════════════════════════════════════════════════════════════════ */
const state = {
  studentId:       null,
  sessionId:       null,
  stream:          null,   // MediaStream from getUserMedia
  captureTimer:    null,   // setInterval handle for auto-capture
  capturing:       false,
  captureComplete: false,
  captured:        0,
};

/* ═══════════════════════════════════════════════════════════════════════════
   DOM
═══════════════════════════════════════════════════════════════════════════ */
const $ = (id) => document.getElementById(id);

const form               = $('registrationForm');
const registerBtn        = $('registerBtn');
const resetFormBtn       = $('resetFormBtn');
const openCamBtn         = $('openCamBtn');
const captureBtn         = $('captureBtn');
const retakeBtn          = $('retakeBtn');
const closeCamBtn        = $('closeCamBtn');
const webcamPlaceholder  = $('webcamPlaceholder');
const webcamOverlay      = $('webcamOverlay');
const progressSection    = $('captureProgressSection');
const progressFill       = $('progressFill');
const progressCount      = $('progressCount');
const statusArea         = $('captureStatusArea');
const resultCard         = $('resultCard');
const resultTitle        = $('resultTitle');
const resultMessage      = $('resultMessage');
const registerAnotherBtn = $('registerAnotherBtn');

// Replace the <img> webcam feed with a <video> element
const webcamPreviewContainer = $('webcamPreviewContainer');
let videoEl = null;
let canvasEl = null;

function createVideoElement() {
  // Remove old img/video if present
  const oldImg = $('webcamFeed');
  if (oldImg) oldImg.remove();
  const oldVideo = $('webcamVideo');
  if (oldVideo) oldVideo.remove();

  videoEl = document.createElement('video');
  videoEl.id = 'webcamVideo';
  videoEl.autoplay = true;
  videoEl.playsInline = true;
  videoEl.muted = true;
  videoEl.className = 'webcam-feed';
  videoEl.style.display = 'none';
  webcamPreviewContainer.appendChild(videoEl);

  canvasEl = document.createElement('canvas');
  canvasEl.style.display = 'none';
  document.body.appendChild(canvasEl);
}

/* ═══════════════════════════════════════════════════════════════════════════
   FORM VALIDATION
═══════════════════════════════════════════════════════════════════════════ */
const isValidEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
const isValidPhone = (v) => !v || /^\+?[\d\s\-()\\.]{7,15}$/.test(v);

function setFieldError(fieldName, msg) {
  const errEl = $(`err-${fieldName}`);
  const field  = form.querySelector(`[name="${fieldName}"]`);
  if (errEl) errEl.textContent = msg || '';
  if (field) {
    field.classList.toggle('is-invalid', !!msg);
    field.classList.toggle('is-valid',   !msg && field.value.trim() !== '');
  }
}

function validateField(name, value) {
  value = (value || '').trim();
  switch (name) {
    case 'student_id':
      if (!value) return 'Student ID is required.';
      if (!/^[A-Za-z0-9_\-]{3,30}$/.test(value)) return 'Student ID: 3–30 alphanumeric chars.';
      return '';
    case 'full_name':
      if (!value) return 'Full Name is required.';
      if (value.length < 2) return 'Full Name must be at least 2 characters.';
      return '';
    case 'department': return value ? '' : 'Department is required.';
    case 'year':       return value ? '' : 'Year is required.';
    case 'section':    return value ? '' : 'Section is required.';
    case 'email':
      if (!value) return 'Email is required.';
      if (!isValidEmail(value)) return 'Email is not valid.';
      return '';
    case 'phone_number':
      return isValidPhone(value) ? '' : 'Phone format is invalid.';
    default: return '';
  }
}

function validateAll() {
  const required = ['student_id', 'full_name', 'department', 'year', 'section', 'email'];
  let valid = true;
  for (const name of required) {
    const field = form.querySelector(`[name="${name}"]`);
    const err = validateField(name, field ? field.value : '');
    setFieldError(name, err);
    if (err) valid = false;
  }
  return valid;
}

function updateRegisterBtnState() {
  const required = ['student_id', 'full_name', 'department', 'year', 'section', 'email'];
  const allFilled = required.every((n) => {
    const f = form.querySelector(`[name="${n}"]`);
    return f && f.value.trim() !== '';
  });
  registerBtn.disabled = !allFilled;
}

form.addEventListener('input',  (e) => { if (e.target.name) setFieldError(e.target.name, validateField(e.target.name, e.target.value)); updateRegisterBtnState(); });
form.addEventListener('change', (e) => { if (e.target.name) setFieldError(e.target.name, validateField(e.target.name, e.target.value)); updateRegisterBtnState(); });

/* ═══════════════════════════════════════════════════════════════════════════
   STATUS MESSAGES
═══════════════════════════════════════════════════════════════════════════ */
const STATUS_ICONS = { info: 'bi-info-circle-fill', success: 'bi-check-circle-fill', error: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill' };

function showStatus(msg, type = 'info') {
  if (!statusArea) return;
  statusArea.innerHTML = `<div class="status-msg status-msg--${type}"><i class="bi ${STATUS_ICONS[type]}"></i><span>${esc(msg)}</span></div>`;
}
function clearStatus() { if (statusArea) statusArea.innerHTML = ''; }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

/* ═══════════════════════════════════════════════════════════════════════════
   PROGRESS UI
═══════════════════════════════════════════════════════════════════════════ */
function updateProgressUI(captured, total) {
  if (!progressSection) return;
  progressSection.style.display = 'block';
  const pct = Math.min((captured / total) * 100, 100);
  progressFill.style.width = `${pct}%`;
  progressCount.textContent = `${captured} / ${total}`;
  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const dot = $(`dot-${i}`);
    if (!dot) continue;
    dot.classList.remove('captured', 'active');
    if (i < captured)                    dot.classList.add('captured');
    else if (i === captured && captured < total) dot.classList.add('active');
  }
}

function resetProgressUI() {
  if (!progressSection) return;
  progressSection.style.display = 'none';
  progressFill.style.width = '0%';
  progressCount.textContent = `0 / ${TOTAL_FRAMES}`;
  for (let i = 0; i < TOTAL_FRAMES; i++) {
    const dot = $(`dot-${i}`);
    if (dot) dot.classList.remove('captured', 'active');
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   API HELPERS
═══════════════════════════════════════════════════════════════════════════ */
async function apiPost(url, payload = {}) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}
async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

/* ═══════════════════════════════════════════════════════════════════════════
   STEP 1 – REGISTER STUDENT
═══════════════════════════════════════════════════════════════════════════ */
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!validateAll()) { window.SmartAttend.warn('Validation Error', 'Fix highlighted fields.'); return; }

  setLoading(registerBtn, true);
  const payload = {};
  for (const [k, v] of new FormData(form).entries()) payload[k] = v;

  const { ok, data } = await apiPost(API.STUDENTS, payload);
  setLoading(registerBtn, false);

  if (!ok) {
    const errors = data.errors || [data.error || 'Registration failed.'];
    errors.forEach((err) => showStatus(err, 'error'));
    window.SmartAttend.error('Registration Failed', errors[0]);
    return;
  }

  state.studentId = data.student.student_id;
  window.SmartAttend.success('Student Saved', data.message);
  registerBtn.disabled = true;
  openCamBtn.disabled  = false;
  showStatus('✅ Student saved! Now click "Open Camera" to capture your face.', 'success');
});

function setLoading(btn, loading) {
  btn.querySelector('.btn-text')?.classList.toggle('d-none', loading);
  btn.querySelector('.btn-spinner')?.classList.toggle('d-none', !loading);
  btn.disabled = loading;
}

/* ═══════════════════════════════════════════════════════════════════════════
   STEP 2 – OPEN CAMERA (browser getUserMedia)
═══════════════════════════════════════════════════════════════════════════ */
openCamBtn.addEventListener('click', async () => {
  if (!state.studentId) {
    window.SmartAttend.warn('Save First', 'Register the student before opening the camera.');
    return;
  }

  openCamBtn.disabled = true;
  showStatus('Requesting camera access…', 'info');

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: false,
    });

    state.stream = stream;

    // Create video element and attach stream
    createVideoElement();
    videoEl.srcObject = stream;
    videoEl.style.display = 'block';
    webcamPlaceholder.classList.add('d-none');
    webcamOverlay.classList.remove('d-none');

    // Update buttons
    openCamBtn.classList.add('d-none');
    captureBtn.classList.remove('d-none');
    closeCamBtn.classList.remove('d-none');

    showStatus('Camera ready! Click "Capture Face" to begin.', 'success');
    window.SmartAttend.success('Camera Ready', 'Click "Capture Face" to start.');

  } catch (err) {
    openCamBtn.disabled = false;
    let msg = 'Camera access denied.';
    if (err.name === 'NotFoundError')      msg = 'No camera found on this device.';
    if (err.name === 'NotAllowedError')    msg = 'Camera permission denied. Allow camera access in your browser.';
    if (err.name === 'NotReadableError')   msg = 'Camera is in use by another application. Close it and try again.';
    if (err.name === 'OverconstrainedError') msg = 'Camera constraints not met. Try a different camera.';
    showStatus(msg, 'error');
    window.SmartAttend.error('Camera Error', msg);
  }
});

/* ═══════════════════════════════════════════════════════════════════════════
   STEP 3 – CAPTURE FACE (auto-send frames to server)
═══════════════════════════════════════════════════════════════════════════ */
captureBtn.addEventListener('click', async () => {
  if (state.capturing) return;

  captureBtn.disabled = true;
  showStatus('Starting capture session…', 'info');

  // Create server-side session
  const { ok, data } = await apiPost(API.CAPTURE_START, { student_id: state.studentId });
  if (!ok) {
    showStatus(data.error || 'Could not start session.', 'error');
    captureBtn.disabled = false;
    return;
  }

  state.sessionId       = data.session_id;
  state.capturing       = true;
  state.captureComplete = false;
  state.captured        = 0;
  state.isUploading     = false;

  resetProgressUI();
  showStatus('Look at the camera. Capturing frames…', 'info');

  // Loop manually to avoid concurrent overlapping requests that deadlock the server
  captureLoop();
});

async function captureLoop() {
  if (!state.capturing || state.captureComplete) return;
  
  if (!state.isUploading) {
    await sendFrame();
  }
  
  if (state.capturing && !state.captureComplete) {
    state.captureTimer = setTimeout(captureLoop, SEND_INTERVAL);
  }
}

async function sendFrame() {
  if (!videoEl || !canvasEl || !state.capturing || state.captureComplete) return;

  state.isUploading = true;
  
  try {
    // Draw current video frame to canvas
    const w = videoEl.videoWidth  || 640;
    const h = videoEl.videoHeight || 480;
    canvasEl.width  = w;
    canvasEl.height = h;
    const ctx = canvasEl.getContext('2d');
    ctx.drawImage(videoEl, 0, 0, w, h);

    // Get base64 JPEG
    const base64 = canvasEl.toDataURL('image/jpeg', 0.85);

    const { ok, data } = await apiPost(API.UPLOAD_FRAME, {
      session_id: state.sessionId,
      frame: base64,
    });

    if (!ok) return;

    const captured = data.captured ?? state.captured;
    const target   = data.target   ?? TOTAL_FRAMES;
    state.captured = captured;

    updateProgressUI(captured, target);

    if (data.status === 'skip') {
      const reason = data.reason === 'no_face'        ? 'No face detected — look at the camera…'
                   : data.reason === 'multiple_faces' ? 'Multiple faces! Only one person should be visible.'
                   : 'Adjusting…';
      showStatus(reason, 'warning');
      return;
    }

    if (data.status === 'saved') {
      showStatus(`Captured ${captured} of ${target} frames…`, 'info');
    }

    if (data.complete || data.status === 'complete') {
      if (state.captureTimer) clearTimeout(state.captureTimer);
      state.captureTimer    = null;
      state.capturing       = false;
      state.captureComplete = true;

      updateProgressUI(target, target);
      showStatus(`✅ ${target} frames captured! Generating face embedding…`, 'success');
      window.SmartAttend.success('Capture Complete', `${target} face images captured.`);

      captureBtn.classList.add('d-none');
      retakeBtn.classList.remove('d-none');

      await generateEmbedding();
    }
  } catch (err) {
    console.error('Frame upload error:', err);
  } finally {
    state.isUploading = false;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   STEP 4 – GENERATE EMBEDDING
═══════════════════════════════════════════════════════════════════════════ */
async function generateEmbedding() {
  const { ok, data } = await apiPost(API.EMBEDDING_GEN, {
    student_id: state.studentId,
    session_id: state.sessionId,
  });

  if (!ok) {
    showStatus(data.error || 'Embedding generation failed.', 'error');
    window.SmartAttend.error('Embedding Failed', data.error);
    return;
  }

  // Success — stop camera
  stopStream();
  showStatus('Face registered!', 'success');
  window.SmartAttend.success('Done!', data.message);

  resultTitle.textContent   = '🎉 Registration Complete!';
  resultMessage.textContent = data.message;
  resultCard.classList.remove('d-none');

  captureBtn.classList.add('d-none');
  retakeBtn.classList.add('d-none');
  closeCamBtn.classList.add('d-none');
}

/* ═══════════════════════════════════════════════════════════════════════════
   RETAKE
═══════════════════════════════════════════════════════════════════════════ */
retakeBtn.addEventListener('click', async () => {
  if (state.captureTimer) clearTimeout(state.captureTimer);
  state.captureTimer    = null;
  state.capturing       = false;
  state.captureComplete = false;
  state.captured        = 0;
  state.sessionId       = null;

  await apiPost(API.CAPTURE_RESET);

  resetProgressUI();
  clearStatus();
  captureBtn.disabled = false;
  captureBtn.classList.remove('d-none');
  retakeBtn.classList.add('d-none');

  showStatus('Reset. Click "Capture Face" to try again.', 'warning');
  window.SmartAttend.warn('Retake', 'Ready to try again.');
});

/* ═══════════════════════════════════════════════════════════════════════════
   CLOSE CAMERA
═══════════════════════════════════════════════════════════════════════════ */
closeCamBtn.addEventListener('click', () => {
  if (state.captureTimer) clearTimeout(state.captureTimer);
  state.captureTimer = null;
  state.capturing    = false;
  stopStream();

  openCamBtn.classList.remove('d-none');
  openCamBtn.disabled = false;
  captureBtn.classList.add('d-none');
  retakeBtn.classList.add('d-none');
  closeCamBtn.classList.add('d-none');

  resetProgressUI();
  clearStatus();
  window.SmartAttend.info('Camera Closed', 'Webcam released.');
});

function stopStream() {
  if (state.stream) {
    state.stream.getTracks().forEach((t) => t.stop());
    state.stream = null;
  }
  if (videoEl) {
    videoEl.srcObject = null;
    videoEl.style.display = 'none';
  }
  webcamPlaceholder.classList.remove('d-none');
  webcamOverlay.classList.add('d-none');
}

/* ═══════════════════════════════════════════════════════════════════════════
   RESET FORM
═══════════════════════════════════════════════════════════════════════════ */
resetFormBtn.addEventListener('click', () => {
  if (state.captureTimer) clearTimeout(state.captureTimer);
  stopStream();

  form.reset();
  form.querySelectorAll('.is-invalid,.is-valid').forEach((el) => el.classList.remove('is-invalid','is-valid'));
  form.querySelectorAll('.field-error').forEach((el) => (el.textContent = ''));

  Object.assign(state, { studentId: null, sessionId: null, stream: null,
    captureTimer: null, capturing: false, captureComplete: false, captured: 0 });

  openCamBtn.classList.remove('d-none');
  openCamBtn.disabled  = true;
  captureBtn.classList.add('d-none');
  retakeBtn.classList.add('d-none');
  closeCamBtn.classList.add('d-none');
  registerBtn.disabled = true;

  resetProgressUI();
  clearStatus();
  resultCard.classList.add('d-none');
  window.SmartAttend.info('Reset', 'Form cleared.');
});

registerAnotherBtn.addEventListener('click', () => resetFormBtn.click());

/* ═══════════════════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════════════════ */
(function init() {
  registerBtn.disabled = true;
  openCamBtn.disabled  = true;

  // Check browser camera support
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showStatus('Your browser does not support camera access. Use Chrome or Firefox.', 'error');
    openCamBtn.disabled = true;
  }
})();
