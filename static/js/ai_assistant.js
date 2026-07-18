document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('aiQueryBtn').addEventListener('click', sendAIQuery);
    document.getElementById('aiQueryInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendAIQuery();
    });
});

async function sendAIQuery() {
    const inputEl = document.getElementById('aiQueryInput');
    const query = inputEl.value.trim();
    if (!query) return;
    
    appendChatMessage('You', query, 'text-primary');
    inputEl.value = '';
    
    try {
        const res = await fetch('/api/analytics/assistant', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });
        
        const data = await res.json();
        if (data.success) {
            appendChatMessage('AI Assistant', data.response, 'text-success');
        } else {
            appendChatMessage('System Error', 'Failed to process query.', 'text-danger');
        }
    } catch (err) {
        appendChatMessage('System Error', 'Network error.', 'text-danger');
    }
}

function appendChatMessage(sender, message, colorClass) {
    const chatBox = document.getElementById('chatBox');
    
    // Remove the placeholder message if it's the first message
    const placeholders = chatBox.querySelectorAll('.text-center');
    placeholders.forEach(el => el.remove());

    const msgDiv = document.createElement('div');
    msgDiv.className = 'mb-3 pb-3 border-bottom border-secondary';
    msgDiv.innerHTML = `<strong class="${colorClass}">${sender}</strong><br><span class="text-light mt-1 d-inline-block">${message}</span>`;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}
