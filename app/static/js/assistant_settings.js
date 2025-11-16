// Assistant Settings

document.addEventListener('DOMContentLoaded', function() {
    // Load current settings
    loadAssistantSettings();
    
    // Relationship type change
    document.getElementById('relationship_type').addEventListener('change', function() {
        const descGroup = document.getElementById('relationship_description_group');
        const descField = document.getElementById('relationship_description');
        
        const defaults = {
            friend: "You've known each other for years, so you're casual and genuine with each other.",
            boss: "You're professional and efficient, focusing on productivity and results.",
            collaborator: "You work together as equals, bouncing ideas off each other.",
            custom: ""
        };
        
        if (this.value) {
            descGroup.style.display = 'block';
            descField.value = defaults[this.value] || '';
        } else {
            descGroup.style.display = 'none';
        }
    });
    
    // Communication style change
    document.querySelectorAll('input[name="communication_style"]').forEach(radio => {
        radio.addEventListener('change', updateChatGuidelines);
    });
    
    // Form submit
    document.getElementById('assistantSettingsForm').addEventListener('submit', saveAssistantSettings);
});

async function loadAssistantSettings() {
    try {
        // Load personality
        const personalityRes = await fetch('/api/assistant-personality');
        if (personalityRes.ok) {
            const personality = await personalityRes.json();
            if (personality.success && personality.data) {
                document.getElementById('assistant_name').value = personality.data.name || 'Emi';
                document.getElementById('assistant_personality').value = personality.data.personality || '';
                document.getElementById('assistant_backstory').value = personality.data.backstory || '';
            }
        }
        
        // Load relationship config
        const relationshipRes = await fetch('/api/assistant-relationship');
        if (relationshipRes.ok) {
            const relationship = await relationshipRes.json();
            if (relationship.success && relationship.data) {
                document.getElementById('relationship_type').value = relationship.data.type || 'friend';
                document.getElementById('relationship_description').value = relationship.data.description || '';
                document.getElementById('assistant_role').value = relationship.data.role || '';
                
                // Trigger relationship type change to show/hide description
                if (relationship.data.type) {
                    document.getElementById('relationship_type').dispatchEvent(new Event('change'));
                }
            }
        }
        
        // Load chat guidelines
        const guidelinesRes = await fetch('/api/chat-guidelines');
        if (guidelinesRes.ok) {
            const guidelines = await guidelinesRes.json();
            if (guidelines.success && guidelines.data) {
                const style = guidelines.data.style || 'direct';
                document.querySelector(`input[name="communication_style"][value="${style}"]`).checked = true;
                document.getElementById('chat_guidelines').value = guidelines.data.guidelines || '';
            }
        }
    } catch (error) {
        console.error('Error loading assistant settings:', error);
        showError('Failed to load settings');
    }
}

function updateChatGuidelines() {
    const style = document.querySelector('input[name="communication_style"]:checked').value;
    const guidelines = document.getElementById('chat_guidelines');
    
    const defaults = {
        direct: `Guidelines for chat:
- Don't try to drive conversation forward with questions unless it's natural
- Don't keep offering help unprompted
- No closing sentences like "I am here to help" or "Let me know if you need anything"
- Eliminate phrases like "just let me know"

Example:
User: Just working today.
Wrong: Nice, hope work's not too crazy today. If you need anything, just let me know!
Correct: Nice, hope work's not too crazy today.`,
        
        warm: `Guidelines for chat:
- Be empathetic and check in on wellbeing
- Offer help proactively when appropriate
- Use warm, supportive language
- Ask follow-up questions to show you care`,
        
        professional: `Guidelines for chat:
- Maintain professional boundaries
- Focus on efficiency and task completion
- Use structured, organized responses
- Confirm understanding and next steps clearly`,
        
        custom: ''
    };
    
    // Only populate if current value is empty
    if (!guidelines.value.trim()) {
        guidelines.value = defaults[style] || '';
    }
}

async function saveAssistantSettings(e) {
    e.preventDefault();
    
    const formData = {
        personality: {
            name: document.getElementById('assistant_name').value.trim(),
            personality: document.getElementById('assistant_personality').value.trim() || null,
            backstory: document.getElementById('assistant_backstory').value.trim() || null
        },
        relationship: {
            type: document.getElementById('relationship_type').value,
            description: document.getElementById('relationship_description').value.trim() || '',
            role: document.getElementById('assistant_role').value.trim()
        },
        chat_guidelines: {
            style: document.querySelector('input[name="communication_style"]:checked').value,
            guidelines: document.getElementById('chat_guidelines').value.trim()
        }
    };
    
    document.getElementById('loading').style.display = 'block';
    
    try {
        // Save all three endpoints
        const results = await Promise.all([
            fetch('/api/assistant-personality', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData.personality)
            }),
            fetch('/api/assistant-relationship', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData.relationship)
            }),
            fetch('/api/chat-guidelines', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData.chat_guidelines)
            })
        ]);
        
        const allSuccessful = results.every(r => r.ok);
        
        if (allSuccessful) {
            showSuccess('Assistant settings saved successfully!');
        } else {
            throw new Error('Some settings failed to save');
        }
    } catch (error) {
        console.error('Save error:', error);
        showError('Failed to save: ' + error.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

function showSuccess(message) {
    const successDiv = document.getElementById('success-message');
    successDiv.textContent = message;
    successDiv.style.display = 'block';
    
    setTimeout(() => {
        successDiv.style.display = 'none';
    }, 3000);
}


