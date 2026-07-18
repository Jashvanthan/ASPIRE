/**
 * attendance.js
 * -------------
 * Handles browser getUserMedia camera stream, extracts frames,
 * sends them to the server for YOLOv11n detection, and draws
 * the resulting bounding boxes onto a canvas.
 */

'use strict';

const API = {
    PROCESS_FRAME: '/api/attendance/process-frame'
};

const FPS = window.CAMERA_FPS || 10; // Target frames per second from backend config
const FRAME_INTERVAL = 1000 / FPS;

const state = {
    stream: null,
    isProcessing: false,
    isActive: false,
    lastFrameTime: 0,
    animationId: null,
    currentDetections: [] // Store latest detections here
};

// ... (skip down to processFrameLoop) ...

/**
 * Main loop: captures a frame from video, draws to display canvas,
 * draws bounding boxes, and conditionally sends to server for detection.
 */
async function processFrameLoop(timestamp) {
    if (!state.isActive) return;
    
    const displayCtx = displayCanvas.getContext('2d');
    const w = displayCanvas.width;
    const h = displayCanvas.height;
    
    // Always draw current video frame to display canvas
    // (This keeps the video feed smooth at 30-60fps)
    displayCtx.drawImage(videoEl, 0, 0, w, h);
    
    // Draw the latest detections on top of the video frame
    if (state.currentDetections.length > 0) {
        drawDetections(state.currentDetections);
    }
    
    // Check if it's time to send a frame to the backend (throttle to target FPS)
    if (timestamp - state.lastFrameTime >= FRAME_INTERVAL && !state.isProcessing) {
        state.lastFrameTime = timestamp;
        // Do not await here so the loop isn't blocked
        detectCurrentFrame();
    }
    
    // Request next frame
    state.animationId = requestAnimationFrame(processFrameLoop);
}

/**
 * Captures frame, sends to backend, and parses result
 */
async function detectCurrentFrame() {
    state.isProcessing = true;
    
    try {
        const w = captureCanvas.width;
        const h = captureCanvas.height;
        const captureCtx = captureCanvas.getContext('2d');
        
        // Draw video frame to capture canvas
        captureCtx.drawImage(videoEl, 0, 0, w, h);
        
        // Convert to base64 JPEG
        const frameB64 = captureCanvas.toDataURL('image/jpeg', 0.8);
        
        // Send to backend
        const res = await fetch(API.PROCESS_FRAME, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ frame: frameB64 })
        });
        
        if (res.ok) {
            const data = await res.json();
            if (data.success && data.detections) {
                // Update UI count
                objectCount.textContent = data.detections.length;
                
                // Save detections to state so the render loop can draw them continuously
                state.currentDetections = data.detections;
            } else {
                state.currentDetections = [];
            }
        }
    } catch (err) {
        console.error("Detection error:", err);
    } finally {
        state.isProcessing = false;
    }
}

// DOM Elements
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const cameraStatusText = document.getElementById('cameraStatusText');
const objectCount = document.getElementById('objectCount');
const currentTimeEl = document.getElementById('currentTime');
const videoPlaceholder = document.getElementById('videoPlaceholder');
const livePresentCount = document.getElementById('livePresentCount');
const liveTotalCount = document.getElementById('liveTotalCount');
const latestAttendeesList = document.getElementById('latestAttendeesList');

const videoEl = document.getElementById('webcamVideo');
const captureCanvas = document.getElementById('captureCanvas');
const displayCanvas = document.getElementById('displayCanvas');

/**
 * Start the camera using getUserMedia
 */
async function startCamera() {
    try {
        startBtn.disabled = true;
        cameraStatusText.textContent = "Requesting camera access...";
        
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
            audio: false
        });
        
        state.stream = stream;
        videoEl.srcObject = stream;
        
        // Wait for video metadata to load to get dimensions
        videoEl.onloadedmetadata = () => {
            const w = videoEl.videoWidth;
            const h = videoEl.videoHeight;
            
            // Set canvas dimensions to match video
            captureCanvas.width = w;
            captureCanvas.height = h;
            displayCanvas.width = w;
            displayCanvas.height = h;
            
            // Update UI
            videoPlaceholder.classList.add('d-none');
            displayCanvas.classList.remove('d-none');
            
            startBtn.classList.add('d-none');
            stopBtn.classList.remove('d-none');
            cameraStatusText.textContent = "Camera active. Running YOLOv11n detection...";
            
            state.isActive = true;
            startBtn.disabled = false;
            
            // Start processing loop
            requestAnimationFrame(processFrameLoop);
        };
        
    } catch (err) {
        startBtn.disabled = false;
        console.error("Camera error:", err);
        cameraStatusText.textContent = "Camera access denied or unavailable.";
        window.SmartAttend?.error("Camera Error", "Could not access the webcam.");
    }
}

/**
 * Stop the camera and halt processing
 */
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
    
    // Reset UI
    displayCanvas.classList.add('d-none');
    videoPlaceholder.classList.remove('d-none');
    
    stopBtn.classList.add('d-none');
    startBtn.classList.remove('d-none');
    
    cameraStatusText.textContent = "Camera is offline";
    objectCount.textContent = "0";
    
    // Clear display canvas
    const ctx = displayCanvas.getContext('2d');
    ctx.clearRect(0, 0, displayCanvas.width, displayCanvas.height);
}


/**
 * Fetch and update live stats from the server
 */
async function updateLiveStats() {
    if (!state.isActive) return;
    
    try {
        const res = await fetch('/api/attendance/live');
        if (res.ok) {
            const data = await res.json();
            livePresentCount.textContent = data.present || 0;
            liveTotalCount.textContent = data.total || 0;
            
            if (data.latest && data.latest.length > 0) {
                latestAttendeesList.innerHTML = data.latest.map(record => `
                    <div class="d-flex align-items-center mb-3 p-2 rounded" style="background: rgba(255,255,255,0.02); border-left: 3px solid #22c55e;">
                        <div class="rounded-circle bg-success text-white d-flex justify-content-center align-items-center me-3" style="width: 40px; height: 40px; font-weight: bold;">
                            ${record.student_name.charAt(0)}
                        </div>
                        <div>
                            <div class="fw-bold" style="font-size: 0.9rem;">${record.student_name}</div>
                            <div class="text-muted" style="font-size: 0.75rem;">ID: ${record.student_id} • Time: ${record.time}</div>
                        </div>
                    </div>
                `).join('');
            } else {
                latestAttendeesList.innerHTML = `<div class="text-center text-muted small py-4">No attendance recorded today yet.</div>`;
            }
        }
    } catch (err) {
        console.error("Failed to fetch live stats", err);
    }
}

// Start live stats polling
setInterval(updateLiveStats, 2000);

// Update local clock every second
setInterval(() => {
    if (currentTimeEl) {
        currentTimeEl.textContent = new Date().toLocaleTimeString('en-US', { hour12: false });
    }
}, 1000);

/**
 * Draw bounding boxes over the display canvas
 */
function drawDetections(detections) {
    const ctx = displayCanvas.getContext('2d');
    
    detections.forEach(det => {
        const [x, y, w, h] = det.bbox;
        
        // Use status color provided by backend, default to green if missing
        const statusColor = det.status_color || 'green';
        
        let colorHex;
        if (statusColor === 'red') colorHex = '#ef4444';
        else if (statusColor === 'yellow') colorHex = '#f59e0b';
        else colorHex = '#22c55e'; // Green
        
        // Build label text
        let labelText = `${det.label}`;
        if (det.similarity) {
            labelText += ` (${(det.similarity * 100).toFixed(0)}%)`;
        }
        
        // Box styling
        ctx.strokeStyle = colorHex;
        ctx.lineWidth = 3;
        ctx.strokeRect(x, y, w, h);
        
        // Label background
        ctx.fillStyle = colorHex;
        ctx.font = '13px Inter, sans-serif';
        const textWidth = ctx.measureText(labelText).width;
        ctx.fillRect(x, y - 25, textWidth + 10, 25);
        
        // Label text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(labelText, x + 5, y - 7);
        
        // Liveness sub-label (below the bounding box)
        if (det.liveness_score !== undefined) {
            const livePct = (det.liveness_score * 100).toFixed(0);
            const spoofPct = (det.spoof_probability * 100).toFixed(0);
            const livenessText = `Live: ${livePct}% | Spoof: ${spoofPct}%`;
            
            const liveColor = det.liveness_score >= 0.6 ? '#22c55e' : '#ef4444';
            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.font = '12px Inter, sans-serif'; // Set font FIRST before measuring!
            const liveTextWidth = ctx.measureText(livenessText).width;
            
            // Prevent text from being cut off at the bottom of the screen
            const canvasHeight = displayCanvas.height;
            let labelY = y + h;
            if (labelY + 22 > canvasHeight) {
                labelY = canvasHeight - 25; // Push it up into the screen
            }
            
            // Draw background slightly larger than text
            ctx.fillRect(x, labelY, liveTextWidth + 12, 22);
            
            ctx.fillStyle = liveColor;
            ctx.fillText(livenessText, x + 6, labelY + 15);
        }
    });
}

// Event Listeners
startBtn.addEventListener('click', startCamera);
stopBtn.addEventListener('click', stopCamera);

// Clean up on page unload
window.addEventListener('beforeunload', stopCamera);
