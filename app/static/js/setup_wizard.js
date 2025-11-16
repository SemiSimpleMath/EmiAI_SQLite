// Setup Wizard
let currentStep = 1;
let peopleCount = 0;
const totalSteps = 7;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    console.log('Setup wizard loaded');
    
    // Add Person button
    document.getElementById('add-person-btn').addEventListener('click', addPerson);
    
    // Navigation buttons
    document.getElementById('nextBtn').addEventListener('click', nextStep);
    document.getElementById('prevBtn').addEventListener('click', prevStep);
    document.getElementById('submitBtn').addEventListener('click', submitSetup);
    
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
    
    // Google OAuth button
    const googleOAuthBtn = document.getElementById('google-oauth-btn');
    if (googleOAuthBtn) {
        googleOAuthBtn.addEventListener('click', handleGoogleOAuth);
    }
    
    // Check OAuth status on page load
    checkGoogleOAuthStatus();
    
    // Check for OAuth success message in URL
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('oauth_success') === 'true') {
        showGoogleOAuthSuccess();
    }
    
    // Integration toggles (removed - no longer needed)
    // document.getElementById('enable_google').addEventListener('change', function() {
    //     document.getElementById('google_fields').style.display = this.checked ? 'block' : 'none';
    // });
    
    // Initialize with one person
    addPerson();
    
    // Set initial chat guidelines
    updateChatGuidelines();
});

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
    
    // Populate with default for the selected style
    // User can always edit regardless of which style is chosen
    guidelines.value = defaults[style] || '';
}

function showStep(step) {
    // Hide all steps
    document.querySelectorAll('.setup-step').forEach(s => s.classList.remove('active'));
    
    // Show current step
    const currentStepEl = document.querySelector(`.setup-step[data-step="${step}"]`);
    if (currentStepEl) {
        currentStepEl.classList.add('active');
    }
    
    // Update progress bar
    document.querySelectorAll('.progress-step').forEach((s, index) => {
        if (index < step) {
            s.classList.add('active');
        } else {
            s.classList.remove('active');
        }
    });
    
    // Update navigation buttons
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const submitBtn = document.getElementById('submitBtn');
    
    prevBtn.style.display = step === 1 ? 'none' : 'inline-block';
    
    if (step === 7) {
        nextBtn.style.display = 'none';
        submitBtn.style.display = 'inline-block';
        
        // Update completion message
        const firstName = document.getElementById('first_name').value || document.getElementById('preferred_name').value;
        const assistantName = document.getElementById('assistant_name').value;
        document.getElementById('completion-name').textContent = firstName;
        document.getElementById('completion-assistant').textContent = assistantName;
    } else {
        nextBtn.style.display = 'inline-block';
        submitBtn.style.display = 'none';
    }
}

function nextStep() {
    console.log('Next button clicked, current step:', currentStep);
    
    if (validateStep(currentStep)) {
        if (currentStep < totalSteps) {
            currentStep++;
            showStep(currentStep);
        }
    }
}

function prevStep() {
    if (currentStep > 1) {
        currentStep--;
        showStep(currentStep);
    }
}

function validateStep(step) {
    const currentStepEl = document.querySelector(`.setup-step[data-step="${step}"]`);
    const inputs = currentStepEl.querySelectorAll('input[required], select[required]');
    
    for (let input of inputs) {
        if (!input.value.trim()) {
            showError(`Please fill in all required fields`);
            input.focus();
            return false;
        }
        
        if (input.id === 'openai_api_key' && !input.value.startsWith('sk-')) {
            showError('OpenAI API key must start with "sk-"');
            input.focus();
            return false;
        }
    }
    
    // Step 2: Validate people
    if (step === 2) {
        const peopleEntries = document.querySelectorAll('.person-entry');
        if (peopleEntries.length > 0) {
            for (let entry of peopleEntries) {
                const name = entry.querySelector('.person-name').value.trim();
                const relationship = entry.querySelector('.person-relationship').value.trim();
                
                if (!name || !relationship) {
                    showError('Please fill in name and relationship for all people');
                    return false;
                }
            }
        }
    }
    
    return true;
}

function addPerson() {
    console.log('Adding person');
    peopleCount++;
    
    const template = document.getElementById('person-template');
    const clone = template.content.cloneNode(true);
    
    const personEntry = clone.querySelector('.person-entry');
    personEntry.dataset.personIndex = peopleCount;
    clone.querySelector('.person-number').textContent = peopleCount;
    
    const removeBtn = clone.querySelector('.remove-person-btn');
    removeBtn.addEventListener('click', function() {
        const entry = this.closest('.person-entry');
        removePerson(entry);
    });
    
    document.getElementById('people-list').appendChild(clone);
}

function removePerson(personEntry) {
    const peopleList = document.getElementById('people-list');
    const entries = peopleList.querySelectorAll('.person-entry');
    
    if (entries.length > 1) {
        personEntry.remove();
        renumberPeople();
    } else {
        showError('You must have at least one person entry');
    }
}

function renumberPeople() {
    const entries = document.querySelectorAll('.person-entry');
    entries.forEach((entry, index) => {
        entry.querySelector('.person-number').textContent = index + 1;
        entry.dataset.personIndex = index + 1;
    });
    peopleCount = entries.length;
}

function collectFormData() {
    // Collect people
    const people = [];
    document.querySelectorAll('.person-entry').forEach(entry => {
        const name = entry.querySelector('.person-name').value.trim();
        const relationship = entry.querySelector('.person-relationship').value.trim();
        const birthdate = entry.querySelector('.person-birthdate').value;
        
        if (name && relationship) {
            people.push({ name, relationship, birthdate: birthdate || null });
        }
    });
    
    // Build full name
    const firstName = document.getElementById('first_name').value.trim();
    const middleName = document.getElementById('middle_name').value.trim();
    const lastName = document.getElementById('last_name').value.trim();
    const fullName = [firstName, middleName, lastName].filter(n => n).join(' ');
    
    return {
        // Step 1
        first_name: firstName,
        middle_name: middleName || null,
        last_name: lastName,
        preferred_name: document.getElementById('preferred_name').value.trim() || null,
        full_name: fullName,
        birthdate: document.getElementById('birthdate').value || null,
        pronouns: document.getElementById('pronouns').value,
        
        // Step 2
        important_people: people,
        
        // Step 3
        job: document.getElementById('job').value.trim() || null,
        additional_context: document.getElementById('additional_context').value.trim() || null,
        
        // Step 4
        assistant_name: document.getElementById('assistant_name').value.trim(),
        relationship_type: document.getElementById('relationship_type').value,
        relationship_description: document.getElementById('relationship_description').value.trim() || null,
        assistant_role: document.getElementById('assistant_role').value.trim(),
        assistant_personality: document.getElementById('assistant_personality').value.trim() || null,
        assistant_backstory: document.getElementById('assistant_backstory').value.trim() || null,
        
        // Step 5
        communication_style: document.querySelector('input[name="communication_style"]:checked').value,
        chat_guidelines: document.getElementById('chat_guidelines').value.trim(),
        
        // Step 6
        openai_api_key: document.getElementById('openai_api_key').value.trim(),
        timezone: document.getElementById('timezone').value
        // Removed: enable_google, gmail_address, gmail_app_password (now using OAuth)
    };
}

async function submitSetup() {
    const formData = collectFormData();
    
    document.getElementById('loading').style.display = 'block';
    document.getElementById('submitBtn').disabled = true;
    
    try {
        // Submit setup data
        const response = await fetch('/api/setup/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            window.location.href = result.redirect || '/chat_bot';
        } else {
            throw new Error(result.error || 'Setup failed');
        }
    } catch (error) {
        console.error('Setup error:', error);
        showError('Setup failed: ' + error.message);
        document.getElementById('loading').style.display = 'none';
        document.getElementById('submitBtn').disabled = false;
    }
}

function showError(message) {
    const errorDiv = document.getElementById('error-message');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
    
    errorDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Google OAuth Functions
async function checkGoogleOAuthStatus() {
    try {
        const response = await fetch('/api/oauth/google/status');
        const data = await response.json();
        
        if (data.success && data.configured) {
            showGoogleOAuthSuccess();
        }
    } catch (error) {
        console.error('Error checking OAuth status:', error);
    }
}

async function handleGoogleOAuth() {
    const btn = document.getElementById('google-oauth-btn');
    const statusDiv = document.getElementById('google-oauth-status');
    const messageSpan = document.getElementById('google-oauth-message');
    
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting OAuth...';
    
    try {
        const response = await fetch('/api/oauth/google/start?redirect_to=setup');
        const data = await response.json();
        
        if (data.success && data.authorization_url) {
            // Open OAuth flow in new window
            const width = 600;
            const height = 700;
            const left = (screen.width / 2) - (width / 2);
            const top = (screen.height / 2) - (height / 2);
            
            window.open(
                data.authorization_url,
                'Google OAuth',
                `width=${width},height=${height},left=${left},top=${top}`
            );
            
            statusDiv.style.display = 'block';
            statusDiv.style.backgroundColor = '#e3f2fd';
            statusDiv.style.border = '1px solid #2196f3';
            messageSpan.innerHTML = '<i class="fas fa-info-circle"></i> Please complete authentication in the popup window...';
        } else {
            throw new Error(data.error || 'Failed to start OAuth');
        }
    } catch (error) {
        console.error('OAuth error:', error);
        statusDiv.style.display = 'block';
        statusDiv.style.backgroundColor = '#ffebee';
        statusDiv.style.border = '1px solid #f44336';
        messageSpan.innerHTML = `<i class="fas fa-exclamation-circle"></i> Error: ${error.message}`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fab fa-google"></i> Authenticate with Google';
    }
}

function showGoogleOAuthSuccess() {
    const statusDiv = document.getElementById('google-oauth-status');
    const messageSpan = document.getElementById('google-oauth-message');
    const btn = document.getElementById('google-oauth-btn');
    
    if (statusDiv && messageSpan) {
        statusDiv.style.display = 'block';
        statusDiv.style.backgroundColor = '#e8f5e9';
        statusDiv.style.border = '1px solid #4caf50';
        messageSpan.innerHTML = '<i class="fas fa-check-circle"></i> ✓ Google services connected successfully!';
        
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-check"></i> Connected';
            btn.style.backgroundColor = '#4caf50';
        }
    }
}

