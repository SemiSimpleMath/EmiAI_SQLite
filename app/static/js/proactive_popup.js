/**
 * Proactive Suggestion Popup
 * ==========================
 * 
 * Displays multiple proactive suggestions in a single floating popup.
 * Users can Accept, Snooze, or Dismiss each suggestion individually.
 * TTS is handled server-side via WebSocket.
 */

class ProactiveSuggestionPopup {
    constructor() {
        this.suggestions = [];  // All pending suggestions shown at once
        this.pollInterval = null;
        this.snoozeOptions = [
            { label: '15 min', value: 15 },
            { label: '30 min', value: 30 },
            { label: '1 hr', value: 60 },
            { label: '2 hr', value: 120 }
        ];
        
        this.init();
    }
    
    init() {
        this.createPopupElement();
        this.setupSocketListener();
        this.startPolling(30000);
        this.checkForSuggestions();
        console.log('ProactiveSuggestionPopup initialized');
    }
    
    setupSocketListener() {
        if (typeof socket !== 'undefined') {
            socket.on('proactive_suggestion', (data) => {
                console.log('Received proactive_suggestion:', data);
                this.handleNewSuggestion(data);
            });
            
            socket.on('proactive_suggestion_update', (data) => {
                this.checkForSuggestions();
            });
        }
    }
    
    handleNewSuggestion(suggestion) {
        // Check for duplicates
        const existingIds = new Set(this.suggestions.map(s => s.ticket_id));
        if (existingIds.has(suggestion.ticket_id)) return;
        
        this.suggestions.push(suggestion);
        this.render();
    }
    
    createPopupElement() {
        if (document.getElementById('proactive-popup')) return;
        
        const popup = document.createElement('div');
        popup.id = 'proactive-popup';
        popup.className = 'proactive-popup hidden';
        popup.innerHTML = `
            <div class="proactive-popup-header">
                <span class="proactive-popup-icon">Emi</span>
                <span class="proactive-popup-title">Suggestions</span>
                <span class="proactive-popup-count"></span>
                <button class="proactive-popup-close" title="Dismiss All">X</button>
            </div>
            <div class="proactive-popup-list"></div>
        `;
        
        document.body.appendChild(popup);
        
        // Dismiss all button
        popup.querySelector('.proactive-popup-close').addEventListener('click', () => {
            this.dismissAll();
        });
    }
    
    startPolling(intervalMs = 30000) {
        this.pollInterval = setInterval(() => this.checkForSuggestions(), intervalMs);
    }
    
    isUserInteracting() {
        // Check if user has focus on any element inside the popup
        const popup = document.getElementById('proactive-popup');
        if (!popup) return false;
        return popup.contains(document.activeElement) && document.activeElement !== popup;
    }
    
    async checkForSuggestions() {
        // Skip polling if user is actively interacting with the popup
        if (this.isUserInteracting()) {
            console.log('[ProactivePopup] Skipping poll - user is interacting');
            return;
        }
        
        try {
            const response = await fetch('/api/tickets/pending');
            const data = await response.json();
            
            console.log('[ProactivePopup] Fetched pending suggestions:', data);
            
            const serverIds = new Set((data.tickets || []).map(s => s.ticket_id));
            const existingIds = new Set(this.suggestions.map(s => s.ticket_id));
            
            // Remove suggestions that are no longer on server (expired, dismissed elsewhere, etc.)
            const removed = this.suggestions.filter(s => !serverIds.has(s.ticket_id));
            if (removed.length > 0) {
                this.suggestions = this.suggestions.filter(s => serverIds.has(s.ticket_id));
                console.log('[ProactivePopup] Removed expired/dismissed:', removed.map(s => s.ticket_id));
            }
            
            // Add new suggestions from server
            for (const suggestion of (data.tickets || [])) {
                if (!existingIds.has(suggestion.ticket_id)) {
                    this.suggestions.push(suggestion);
                    console.log('[ProactivePopup] Added suggestion:', suggestion.ticket_id);
                }
            }
            
            this.render();
        } catch (e) {
            console.error('[ProactivePopup] Error checking for suggestions:', e);
        }
    }
    
    render() {
        const popup = document.getElementById('proactive-popup');
        if (!popup) return;
        
        const listContainer = popup.querySelector('.proactive-popup-list');
        const countEl = popup.querySelector('.proactive-popup-count');
        
        if (this.suggestions.length === 0) {
            popup.classList.add('hidden');
            return;
        }
        
        // Update count
        countEl.textContent = `(${this.suggestions.length})`;
        
        // Capture current text input values before re-rendering (to prevent text loss during polling)
        const userTextInputs = listContainer.querySelectorAll('.proactive-user-text');
        const userTextValues = {};
        userTextInputs.forEach(input => {
            const ticketId = input.closest('.proactive-item').dataset.ticketId;
            if (input.value) {
                userTextValues[ticketId] = input.value;
            }
        });
        
        // Build list HTML
        listContainer.innerHTML = this.suggestions.map((s, idx) => {
            // Tool approvals don't get snooze option or text box - just Accept/Reject
            const isToolApproval = s.suggestion_type === 'tool_approval' || 
                                   (s.action_type && s.action_type.startsWith('tool_'));
            // Advice layout: for suggestions not tied to tracked activities
            const isAdvice = !isToolApproval && s.button_layout === 'advice';
            
            let buttonHtml;
            if (isToolApproval) {
                buttonHtml = `
                    <button class="proactive-btn-sm proactive-btn-accept" data-idx="${idx}">Allow</button>
                    <button class="proactive-btn-sm proactive-btn-dismiss" data-idx="${idx}">Deny</button>
                `;
            } else if (isAdvice) {
                // Advice layout: Acknowledge, Will Do, No, Later
                buttonHtml = `
                    <div class="proactive-text-container">
                        <input type="text" 
                               class="proactive-user-text" 
                               data-idx="${idx}"
                               placeholder="Optional: Add a note"
                               maxlength="200">
                    </div>
                    <div class="proactive-actions-row">
                        <button class="proactive-btn-sm proactive-btn-acknowledge" data-idx="${idx}" title="Got it, will consider">👍 Acknowledge</button>
                        <button class="proactive-btn-sm proactive-btn-willdo" data-idx="${idx}" title="I'll do this now">✓ Will Do</button>
                        <button class="proactive-btn-sm proactive-btn-no" data-idx="${idx}" title="Not applicable">✗ No</button>
                        <select class="proactive-snooze-select" data-idx="${idx}">
                            ${this.snoozeOptions.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
                        </select>
                        <button class="proactive-btn-sm proactive-btn-later" data-idx="${idx}">⏰ Later</button>
                    </div>
                `;
            } else {
                // Activity layout: Done, Skip, Later (original)
                buttonHtml = `
                    <div class="proactive-text-container">
                        <input type="text" 
                               class="proactive-user-text" 
                               data-idx="${idx}"
                               placeholder="Optional: Add details (e.g., 'Had 2 glasses')"
                               maxlength="200">
                    </div>
                    <div class="proactive-actions-row">
                        <button class="proactive-btn-sm proactive-btn-done" data-idx="${idx}">✓ Done</button>
                        <button class="proactive-btn-sm proactive-btn-skip" data-idx="${idx}">✗ Skip</button>
                        <select class="proactive-snooze-select" data-idx="${idx}">
                            ${this.snoozeOptions.map(o => `<option value="${o.value}">${o.label}</option>`).join('')}
                        </select>
                        <button class="proactive-btn-sm proactive-btn-later" data-idx="${idx}">⏰ Later</button>
                    </div>
                `;
            }
            
            return `
                <div class="proactive-item ${isToolApproval ? 'tool-approval' : ''}" data-ticket-id="${s.ticket_id}">
                    <div class="proactive-item-content">
                        <div class="proactive-item-title">${this.escapeHtml(s.title || 'Suggestion')}</div>
                        <div class="proactive-item-message">${this.escapeHtml(s.message || '')}</div>
                        <div class="proactive-item-meta">${isToolApproval ? '🔐 Tool Approval' : (s.suggestion_type || '')}</div>
                    </div>
                    <div class="proactive-item-actions">
                        ${buttonHtml}
                    </div>
                </div>
            `;
        }).join('');
        
        // Restore text input values after re-rendering
        listContainer.querySelectorAll('.proactive-user-text').forEach(input => {
            const ticketId = input.closest('.proactive-item').dataset.ticketId;
            if (userTextValues[ticketId]) {
                input.value = userTextValues[ticketId];
            }
        });
        
        // Bind action buttons
        listContainer.querySelectorAll('.proactive-btn-accept').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'accept'));
        });
        listContainer.querySelectorAll('.proactive-btn-done').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'done'));
        });
        listContainer.querySelectorAll('.proactive-btn-skip').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'skip'));
        });
        listContainer.querySelectorAll('.proactive-btn-later').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'later'));
        });
        listContainer.querySelectorAll('.proactive-btn-dismiss').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'dismiss'));
        });
        // Advice layout buttons
        listContainer.querySelectorAll('.proactive-btn-acknowledge').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'acknowledge'));
        });
        listContainer.querySelectorAll('.proactive-btn-willdo').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'willdo'));
        });
        listContainer.querySelectorAll('.proactive-btn-no').forEach(btn => {
            btn.addEventListener('click', () => this.respond(parseInt(btn.dataset.idx), 'no'));
        });
        
        popup.classList.remove('hidden');
    }
    
    async respond(idx, action) {
        const suggestion = this.suggestions[idx];
        if (!suggestion) return;
        
        // Prevent double-clicks - mark as processing immediately
        const ticketId = suggestion.ticket_id;
        if (suggestion._processing) return;
        suggestion._processing = true;
        
        // Get user text from input box (before removing from DOM)
        const popup = document.getElementById('proactive-popup');
        const textInput = popup.querySelector(`.proactive-user-text[data-idx="${idx}"]`);
        const userText = textInput ? textInput.value.trim() : '';
        
        // Get snooze value if applicable
        const selectEl = popup.querySelector(`.proactive-snooze-select[data-idx="${idx}"]`);
        const snoozeMinutes = selectEl ? parseInt(selectEl.value) : 30;
        
        // Remove from UI immediately (optimistic update)
        this.suggestions.splice(idx, 1);
        this.render();
        
        try {
            const response = await fetch('/api/tickets/respond', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ticket_id: ticketId,
                    action: action,
                    user_text: userText,
                    snooze_minutes: snoozeMinutes
                })
            });
            
            if (!response.ok) {
                console.error('Error responding to suggestion:', await response.text());
                // Re-add on error (rollback optimistic update)
                this.suggestions.splice(idx, 0, suggestion);
                this.render();
            }
        } catch (e) {
            console.error('Error responding to suggestion:', e);
            // Re-add on error
            this.suggestions.splice(idx, 0, suggestion);
            this.render();
        }
    }
    
    async dismissAll() {
        for (const suggestion of [...this.suggestions]) {
            try {
                await fetch('/api/tickets/respond', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        ticket_id: suggestion.ticket_id,
                        action: 'skip',
                        user_text: '',
                        snooze_minutes: 30
                    })
                });
            } catch (e) {
                console.error('Error dismissing:', e);
            }
        }
        this.suggestions = [];
        this.render();
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.proactivePopup = new ProactiveSuggestionPopup();
});
