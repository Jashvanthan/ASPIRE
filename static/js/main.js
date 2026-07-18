/**
 * main.js
 * --------
 * Global UI utilities for SmartAttend.
 * Handles: sidebar toggle, toast notifications, global search stub.
 */

/* ═══════════════════════════════════════════════════════════════════════════
   SIDEBAR TOGGLE
═══════════════════════════════════════════════════════════════════════════ */
(function initSidebar() {
  'use strict';

  const toggle   = document.getElementById('sidebarToggle');
  const sidebar  = document.getElementById('sidebar');
  const wrapper  = document.getElementById('mainWrapper');

  if (!toggle || !sidebar) return;

  // Restore collapsed state from localStorage
  if (localStorage.getItem('smartattend_sidebar') === 'collapsed') {
    document.body.classList.add('sidebar-collapsed');
  }

  toggle.addEventListener('click', () => {
    const isCollapsed = document.body.classList.toggle('sidebar-collapsed');
    localStorage.setItem(
      'smartattend_sidebar',
      isCollapsed ? 'collapsed' : 'expanded'
    );
  });

  // On mobile: clicking outside sidebar closes it
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 1024) {
      if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    }
  });

  if (window.innerWidth <= 1024) {
    toggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  }
})();


/* ═══════════════════════════════════════════════════════════════════════════
   TOAST NOTIFICATION SYSTEM
═══════════════════════════════════════════════════════════════════════════ */

/**
 * Show a toast notification.
 *
 * @param {string} title   - Short bold title
 * @param {string} message - Descriptive body text
 * @param {'success'|'error'|'warning'|'info'} type - Visual type
 * @param {number} duration - Auto-dismiss duration in ms (0 = manual only)
 */
window.SmartAttend = window.SmartAttend || {};

window.SmartAttend.toast = function (title, message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const iconMap = {
    success: 'bi-check-circle-fill',
    error:   'bi-x-circle-fill',
    warning: 'bi-exclamation-triangle-fill',
    info:    'bi-info-circle-fill',
  };

  const toast = document.createElement('div');
  toast.className = `toast-item toast--${type}`;
  toast.innerHTML = `
    <i class="bi ${iconMap[type] || iconMap.info} toast-icon"></i>
    <div class="toast-body">
      <div class="toast-title">${_escHtml(title)}</div>
      ${message ? `<div class="toast-msg">${_escHtml(message)}</div>` : ''}
    </div>
    <button class="toast-close" aria-label="Dismiss">
      <i class="bi bi-x-lg"></i>
    </button>
  `;

  container.appendChild(toast);

  // Close button
  toast.querySelector('.toast-close').addEventListener('click', () => _dismissToast(toast));

  // Auto-dismiss
  if (duration > 0) {
    setTimeout(() => _dismissToast(toast), duration);
  }
};

function _dismissToast(toast) {
  if (!toast.parentElement) return;
  toast.classList.add('hiding');
  setTimeout(() => toast.remove(), 300);
}

function _escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/* Shorthand helpers */
window.SmartAttend.success = (t, m) => window.SmartAttend.toast(t, m, 'success');
window.SmartAttend.error   = (t, m) => window.SmartAttend.toast(t, m, 'error');
window.SmartAttend.warn    = (t, m) => window.SmartAttend.toast(t, m, 'warning');
window.SmartAttend.info    = (t, m) => window.SmartAttend.toast(t, m, 'info');


/* ═══════════════════════════════════════════════════════════════════════════
   GLOBAL SEARCH (stub – Phase 1)
═══════════════════════════════════════════════════════════════════════════ */
(function initSearch() {
  const input = document.getElementById('globalSearch');
  if (!input) return;

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = input.value.trim();
      if (q) {
        window.SmartAttend.info('Search', `Search for "${q}" coming in Phase 2.`);
      }
    }
  });
})();
