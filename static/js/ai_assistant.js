document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('aiQueryBtn').addEventListener('click', sendAIQuery);
    document.getElementById('aiQueryInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendAIQuery();
    });
});

function sendChip(el) {
    document.getElementById('aiQueryInput').value = el.textContent;
    sendAIQuery();
}

function getNow() {
    const d = new Date();
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

async function sendAIQuery() {
    const inputEl = document.getElementById('aiQueryInput');
    const query = inputEl.value.trim();
    if (!query) return;

    // Clear empty state
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.remove();

    appendMessage('You', query, false);
    inputEl.value = '';

    // Show typing indicator
    const typingId = showTyping();

    try {
        const res = await fetch('/api/analytics/assistant', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const data = await res.json();
        removeTyping(typingId);

        if (data.success) {
            appendMessage('AI Assistant', data.response, true);
        } else {
            appendMessage('AI Assistant', 'Sorry, I could not process that request. Please try again.', true);
        }
    } catch (err) {
        removeTyping(typingId);
        appendMessage('AI Assistant', 'Network error. Please check your connection.', true);
    }
}

function appendMessage(sender, message, isAI) {
    const chatBox = document.getElementById('chatBox');
    const isUser = !isAI;

    const wrapper = document.createElement('div');
    wrapper.className = `chat-bubble-container ${isUser ? 'justify-content-end bubble-you' : 'justify-content-start bubble-ai'}`;
    wrapper.style.display = 'flex';
    wrapper.style.alignItems = 'flex-end';
    wrapper.style.gap = '8px';

    const avatarIcon = isAI ? 'bi-robot' : 'bi-person-fill';
    const avatarClass = isAI ? 'ai' : 'you';

    // Parse markdown for AI responses only
    let displayMessage = message;
    if (isAI && typeof marked !== 'undefined') {
        displayMessage = marked.parse(message);
    }

    const avatar = `<div class="bubble-avatar ${avatarClass}"><i class="bi ${avatarIcon}"></i></div>`;
    const bubble = `
        <div class="bubble-content">
            <span class="bubble-sender">${sender}</span>
            <div>${displayMessage}</div>
            <span class="bubble-time">${getNow()}</span>
        </div>`;

    if (isAI) {
        wrapper.innerHTML = avatar + bubble;
    } else {
        wrapper.innerHTML = bubble + avatar;
    }

    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

let _typingCounter = 0;
function showTyping() {
    const chatBox = document.getElementById('chatBox');
    const id = 'typing-' + (++_typingCounter);
    const wrapper = document.createElement('div');
    wrapper.id = id;
    wrapper.className = 'chat-bubble-container bubble-ai';
    wrapper.style.display = 'flex';
    wrapper.style.alignItems = 'flex-end';
    wrapper.style.gap = '8px';
    wrapper.innerHTML = `
        <div class="bubble-avatar ai"><i class="bi bi-robot"></i></div>
        <div class="bubble-content" style="padding: 12px 16px;">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>`;
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    return id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}
