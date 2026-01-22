// ==================== Global Variables ====================
let audioChunks = [];
let isRecording = false;
let mediaRecorder;
let mediaStream;
let socket = io.connect(`${window.location.protocol}//${document.domain}:${location.port}`);
let audioQueue = [];
let isAudioPlaying = false;
let mute = false;
let lastReceivedResponse = "";
let lastInteractionTime = 0;
let ttsAudioQueue = [];
let isTTSPlaying = false;
let speakingMode = false;

// Chat mode state management
let chatMode = 'normal'; // 'normal', 'test', 'memo'

// Mode management functions
function toggleTestMode() {
    chatMode = chatMode === 'test' ? 'normal' : 'test';
    updateModeIndicator();
    showModeNotification(`Test mode ${chatMode === 'test' ? 'ON' : 'OFF'}`);
    return chatMode;
}

function toggleMemoMode() {
    chatMode = chatMode === 'memo' ? 'normal' : 'memo';
    updateModeIndicator();
    showModeNotification(`Memo mode ${chatMode === 'memo' ? 'ON' : 'OFF'}`);
    return chatMode;
}

// Parse commands and return mode and text
function parseCommand(message) {
    if (message.startsWith('/test')) {
        toggleTestMode();
        return { mode: 'command', text: message }; // Return original for command detection
    }
    if (message.startsWith('/memo')) {
        toggleMemoMode();
        return { mode: 'command', text: message }; // Return original for command detection
    }
    if (message.startsWith('/normal')) {
        chatMode = 'normal';
        updateModeIndicator();
        showModeNotification('Normal mode ON');
        return { mode: 'command', text: message };
    }
    return { mode: 'normal', text: message };
}

// Update visual mode indicator
function updateModeIndicator() {
    const indicator = document.getElementById('mode-indicator');
    if (!indicator) return;
    
    switch(chatMode) {
        case 'test':
            indicator.textContent = 'TEST MODE';
            indicator.className = 'mode-indicator test-mode';
            break;
        case 'memo':
            indicator.textContent = 'MEMO MODE';
            indicator.className = 'mode-indicator memo-mode';
            break;
        default:
            indicator.textContent = '';
            indicator.className = 'mode-indicator';
    }
}

// Show mode change notification
function showModeNotification(message) {
    // Create or update notification element
    let notification = document.getElementById('mode-notification');
    if (!notification) {
        notification = document.createElement('div');
        notification.id = 'mode-notification';
        notification.className = 'mode-notification';
        document.body.appendChild(notification);
    }
    
    notification.textContent = message;
    notification.style.display = 'block';
    
    // Hide after 3 seconds
    setTimeout(() => {
        notification.style.display = 'none';
    }, 3000);
}

let idleTimeout = null; // Reference to the timeout function
let idleThreshold = 1 * 60 * 1000; // 1 minute
let idleInterval = null; // Reference to the recurring interval function
let idleCheckInterval = 1 * 60 * 1000; // 1 minute

// Array of sound file paths
const randomSoundFiles = [
    "/static/sounds/notifications/bellding-254774.mp3",
    "/static/sounds/notifications/ding-sound-246413.mp3",
    "/static/sounds/notifications/notification-5-158190.mp3",
    "/static/sounds/notifications/notification-beep-229154.mp3",
];

let soundLib = {
    reminder: "/static/sounds/notifications/reminder-tone.mp3",
    drink_water_temp_disabled: "/static/sounds/notifications/drink_water.mp3",
    stretch_fingers: "/static/sounds/notifications/bellding-254774.mp3",
    job_done: "/static/sounds/notifications/jobs-done_1.mp3",
    ding: "/static/sounds/notifications/ding-sound-246413.mp3",
    default_sound: "/static/sounds/notifications/notification-beep-229154.mp3"
};

// at top of emi.js
let audioPlayer;  // declare in outer scope

document.addEventListener('DOMContentLoaded', () => {
  const speakBtn = document.getElementById('speak-mode-btn');
  audioPlayer = document.getElementById('chat-bot-audio');

  let audioUnlocked = false;
  const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";

  function unlockAudio(reason) {
    if (audioUnlocked || !audioPlayer) return;

    audioPlayer.src = SILENT;
    audioPlayer.play()
      .then(() => {
        audioPlayer.pause();
        audioPlayer.src = "";
        audioUnlocked = true;
        console.log(`🔓 Audio unlocked (${reason})`);
      })
      .catch(e => console.warn(`🔒 Unlock failed (${reason})`, e));
  }

  // Speak mode toggle button
  if (speakBtn) {
    speakBtn.addEventListener('click', () => {
      speakingMode = !speakingMode;
      speakBtn.textContent = speakingMode
        ? 'Speak Mode On'
        : 'Speak Mode Off';
      speakBtn.setAttribute('aria-pressed', speakingMode);
      speakBtn.classList.toggle('active', speakingMode);

      // Try unlocking on button click (works on iOS)
      if (/iP(hone|ad|od)/.test(navigator.userAgent)) {
        unlockAudio("Speak Mode toggle");
      }
    });
  }

  // Fallback: unlock on first touch anywhere
  if (/iP(hone|ad|od)/.test(navigator.userAgent)) {
    const touchUnlock = () => {
      unlockAudio("first touch");
      document.removeEventListener("touchend", touchUnlock, true);
    };
    document.addEventListener("touchend", touchUnlock, true);
  }
});


/**
Boot up routine
*/

async function fetchRepoData() {
    console.log("📦 Fetching repo data from /render_repo_route...");
    try {
        const response = await fetch('/render_repo_route', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });

        if (!response.ok) {
            console.error(`❌ HTTP error fetching repo data! Status: ${response.status}`);
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();
        console.log("📦 Repo data response:", data);

        if (data.success && data.repo_data) {
            const itemCount = data.repo_data.widget_data ? data.repo_data.widget_data.length : 0;
            console.log(`✅ Processing ${itemCount} repo items`);
            processRepoData(data.repo_data);
        } else {
            console.warn("⚠️ Repo data response was not successful or missing repo_data:", data);
            if (data.message) {
                console.error("   Server message:", data.message);
            }
        }
    } catch (error) {
        console.error("🛑 Error fetching repo data:", error);
        console.error("   This may indicate the backend is not running or there's a database issue.");
    }
}

async function sendAskUserResponse(question_id, answer) {
    console.log("At ask_user_answer route");
    try {
        const response = await fetch('/ask_user_answer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question_id, answer })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();
        console.log("Response from ask_user_answer:", data);
        // Optionally process data from the route if needed

    } catch (error) {
        console.error("Error sending ask user response:", error);
    }
}


function processRepoData(repoData) {
    console.log("Processing Repo Data");

    try {
        // Ensure widget_data exists and is an array
        if (Array.isArray(repoData.widget_data) && repoData.widget_data.length > 0) {
            const widgetsByType = {};

            // Categorize widgets by type
            repoData.widget_data.forEach(widgetItem => {
                if (!widgetItem.data_type || typeof widgetItem.data_type !== 'string') {
                    console.warn("Widget item missing or invalid 'data_type':", widgetItem);
                    handleGenericWidget([widgetItem]); // Handle unknown widgets safely
                    return;
                }

                const widgetType = widgetItem.data_type.trim().toLowerCase();

                if (!widgetsByType[widgetType]) {
                    widgetsByType[widgetType] = [];
                }

                widgetsByType[widgetType].push(widgetItem);
            });

            // Process each widget type with its respective handler
            Object.entries(widgetsByType).forEach(([widgetType, widgetItems]) => {
                console.log(`Processing repo widget type: ${widgetType} with ${widgetItems.length} item(s)`);
                const handler = widgetHandlers[widgetType] || handleGenericWidget;

                try {
                    handler(widgetItems); // Call the appropriate handler
                } catch (widgetError) {
                    console.error(`Error processing repo widget type: ${widgetType}`, widgetError);
                }
            });
        } else {
            console.warn("No repo widget data received or not in array format.");
        }
    } catch (error) {
        console.error("Unexpected error processing Repo Data:", error);
    }
}



/**
 * Plays a random notification sound from the randomSoundFiles array.
 */
function playRandomNotificationSound() {
    if (mute) return;

    // **Correction Applied: Changed 'soundFiles' to 'randomSoundFiles'**
    if (!randomSoundFiles || randomSoundFiles.length === 0) { // Corrected variable
        console.warn("No sound files available to play.");
        return;
    }

    const randomIndex = Math.floor(Math.random() * randomSoundFiles.length);
    const selectedSound = randomSoundFiles[randomIndex];
    console.log(`Playing random notification sound: ${selectedSound}`);

    playSound(selectedSound);
}

// Initialize an empty array to store user preferences
let preferenceList = [];

/**
 * Adds or updates a preference in the preferenceList.
 * @param {string} category - The category of the content (e.g., 'news').
 * @param {string} title - The title of the news item.
 * @param {string} body - The body or summary of the news item.
 * @param {string} preference - The preference type ('like' or 'dislike').
 * @param {string} id - The unique identifier for the news item (e.g., URL or ID).
 */
function addOrUpdatePreference(category, title, body, preference, id) {
    // Check if the preference for this id already exists
    const existingIndex = preferenceList.findIndex(pref => pref.id === id);

    if (existingIndex !== -1) {
        // Update the existing preference
        preferenceList[existingIndex] = {
            category,
            title,
            body,
            preference,
            id
        };
        console.log(`Preference updated for ID ${id}:`, preferenceList[existingIndex]);
    } else {
        // Add a new preference
        const preferenceRecord = {
            category,
            title,
            body,
            preference,
            id
        };
        preferenceList.push(preferenceRecord);
        console.log('Preference added:', preferenceRecord);
    }
    console.log('Current preferenceList:', preferenceList);
}

/**
 * Removes a preference from the preferenceList.
 * @param {string} id - The unique identifier for the news item (e.g., URL or ID).
 */
function removePreference(id) {
    const initialLength = preferenceList.length;
    preferenceList = preferenceList.filter(pref => pref.id !== id);
    if (preferenceList.length < initialLength) {
        console.log(`Preference removed for ID ${id}.`);
    } else {
        console.log(`No preference found for ID ${id} to remove.`);
    }
    console.log('Current preferenceList:', preferenceList);
}

// **Correction Applied: Removed initial event listeners referencing undefined functions**
/*
document.querySelectorAll('.like-button').forEach(button => {
    button.addEventListener('click', () => {
        const newsItem = getNewsItem(button); // Undefined function
        addPreference('news', newsItem.title, newsItem.body, 'like'); // Undefined function
    });
});

document.querySelectorAll('.dislike-button').forEach(button => {
    button.addEventListener('click', () => {
        const newsItem = getNewsItem(button); // Undefined function
        addPreference('news', newsItem.title, newsItem.body, 'dislike'); // Undefined function
    });
});
*/

/**
 * Handles thumbs-up or thumbs-down actions.
 * @param {string} action - 'up' or 'down'.
 * @param {Event} event - The event triggered by the button click.
 */
function handleThumbs(action, event) {
    console.log(`handleThumbs called with action: ${action}`, event);
    
    // Get the actual button element, even if the click was on the icon inside
    const button = event.target.closest('button') || event.target;
    console.log('Button element:', button);
    
    const parent = button.closest(".news-actions");
    console.log('Parent news-actions:', parent);
    
    const siblingButton = parent.querySelector(
        action === "up" ? ".thumbs-down" : ".thumbs-up"
    );
    console.log('Sibling button:', siblingButton);

    // Get the unique ID from data-id attribute
    const newsId = button.dataset.id;
    console.log('News ID:', newsId);

    // Traverse the DOM to find the parent news item container
    const newsItemContainer = button.closest('.news-item');
    if (!newsItemContainer) {
        console.error("News item container not found.");
        return;
    }
    console.log('News item container:', newsItemContainer);

    // Extract title and body from the news item
    const titleElement = newsItemContainer.querySelector('h3 a'); // Assuming the title is within an <a> tag inside <h3>
    const summaryElement = newsItemContainer.querySelector('p'); // Assuming the summary is within a <p> tag

    const title = titleElement ? titleElement.textContent.trim() : "Unknown Title";
    const body = summaryElement ? summaryElement.textContent.trim() : "No Summary Available";
    console.log('Title:', title);
    console.log('Body:', body);

    // Toggle active state
    if (button.classList.contains("active")) {
        button.classList.remove("active");
        console.log(`Removed ${action} vote for:`, newsId);
        // Remove the preference from the list
        removePreference(newsId);
    } else {
        button.classList.add("active");
        console.log(`Added ${action} vote for:`, newsId);

        // Ensure the other button is not active
        if (siblingButton) {
            siblingButton.classList.remove("active");
            // Remove the previous preference if exists
            const siblingId = siblingButton.dataset.id;
            if (siblingId) {
                removePreference(siblingId);
            }
        }

        // Add or update the preference in the list
        const preferenceType = action === "up" ? "like" : "dislike";
        addOrUpdatePreference('news', title, body, preferenceType, newsId);
    }
}

// ==================== Calendar Variables ====================
let currentCalendarDate = new Date(); // Tracks the currently displayed date
const calendarEventsByDate = {}; // Stores events grouped by date in 'YYYY-MM-DD' format

// ==================== Utility Functions ====================

/**
 * Formats a Date object to 'YYYY-MM-DD' based on local time.
 * @param {Date} date - The date to format.
 * @returns {string} - Formatted date string.
 */
function getFormattedDate(date) {
    const year = date.getFullYear();
    const month = (`0${date.getMonth() + 1}`).slice(-2); // Months are zero-based
    const day = (`0${date.getDate()}`).slice(-2);
    return `${year}-${month}-${day}`;
}

/**
 * Formats a key string for display by replacing underscores with spaces and capitalizing each word.
 * @param {string} key - The key string to format.
 * @returns {string} - The formatted key string.
 */
function formatKeyForDisplay(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
}

/**
 * Formats the value based on the key.
 * @param {string} key - The key corresponding to the value.
 * @param {*} value - The value to format.
 * @returns {string} - The formatted value string.
 */
function formatValue(key, value) {
    // Handle date and time formatting
    const dateKeys = ['start_time', 'end_time', 'start', 'end', 'start_dateTime', 'end_dateTime'];
    if (dateKeys.includes(key) && value) {
        return new Date(value).toLocaleString();
    }

    // Handle link formatting
    if (key.toLowerCase().includes('link') && value) {
        return `<a href="${value}" target="_blank">${value}</a>`;
    }

    // Handle participants or similar arrays
    if (Array.isArray(value)) {
        return value.join(', ');
    }

    // For other types, return as is
    return value;
}

/**
 * Scrolls the chat box to the bottom.
 */
function scrollToBottom() {
    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
        chatBox.scrollTop = chatBox.scrollHeight;
    } else {
        console.error("Chat box element with ID 'chat-box' not found.");
    }
}


/**
 * Plays the next audio in the audioQueue.
 */
function playNextAudio() {
    if (audioQueue.length > 0) {
        const audioUrl = audioQueue.shift();
        const audio = document.getElementById('chat-bot-audio'); // Updated ID
        if (audio) {
            audio.src = audioUrl;
            audio.play()
                .then(() => {
                    isAudioPlaying = true;
                })
                .catch(error => {
                    console.error('Error playing audio:', error);
                });

            audio.onended = () => {
                isAudioPlaying = false;
                playNextAudio();
            };
        } else {
            console.error("Audio element with ID 'chat-bot-audio' not found.");
        }
    }
}

/**
 * Plays the next TTS audio in the ttsAudioQueue.
 */
function playNextTTSAudio() {
    if (ttsAudioQueue.length > 0) {
        isTTSPlaying = true;
        const audioUrl = ttsAudioQueue.shift();
        audioPlayer.src = audioUrl;
        audioPlayer.play()
            .catch(error => {
                console.error('Error playing TTS audio:', error);
                isTTSPlaying = false;
            });

        audioPlayer.onended = () => {
            isTTSPlaying = false;
            playNextTTSAudio();
        };
    }
}


/**
 * Resets the idle timer whenever user activity is detected.
 */
function resetIdleTimer() {
    if (idleTimeout) {
        clearTimeout(idleTimeout);
        idleTimeout = null; // Reset the reference after clearing
    }

    if (idleInterval) {
        clearInterval(idleInterval);
        idleInterval = null; // Reset the reference after clearing
    }

    // Set up a new timeout
    idleTimeout = setTimeout(() => {
        console.log("Idle timeout reached. Invoking idle route...");
        invokeIdleRoute();

        // Set up recurring idle checks
        idleInterval = setInterval(() => {
            console.log("Recurring idle interval reached. Invoking idle route again...");
            invokeIdleRoute();
        }, idleCheckInterval);
        console.log("Set up idleInterval with check every " + (idleCheckInterval / 60000) + " minutes.");
    }, idleThreshold);
}


/**
 * Invokes the idle route on the server when the user is idle.
 */
function invokeIdleRoute() {
    const socketId = socket.id; // Get the current Socket.IO session ID
    console.log("Evoking idle route!!!!!!!!")
    console.log("preferences: ", preferenceList)

    fetch('/handle_idle_route', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ socket_id: socketId, timestamp: Date.now(), preferences: preferenceList}),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log("Idle route invoked successfully:", data.message);
            // **Clear the preferences after successful send**
            preferenceList = [];
            console.log('preferenceList has been cleared:', preferenceList);

        } else {
            console.error("Error invoking idle route:", data.message);
        }
    })
    .catch(error => {
        console.error("Failed to invoke idle route:", error);
    });

    // Reset audio chunks after sending
    audioChunks = [];
}

/**
 * Attaches event listeners to detect user activity and reset the idle timer.
 */
function attachIdleListeners() {
    const activityEvents = ['mousemove', 'mousedown', 'keypress', 'keydown', 'wheel', 'touchstart'];

    activityEvents.forEach(eventType => {
        document.addEventListener(eventType, resetIdleTimer);
    });

    console.log("Idle listeners attached. Timer will reset on user activity.");
}

// ==================== Chat Bubble Functions ====================

/**
 * Creates a new bot chat bubble with the given text.
 * @param {string} text - The bot's message.
 */
function createBotBubble(text) {
    console.log("Creating bot bubble with text:", text); // Debug log
    const bubble = document.createElement("div");
    const p = document.createElement("p");
    p.innerHTML = text;
    bubble.appendChild(p);
    bubble.className = "bot-bubble";
    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
        chatBox.appendChild(bubble);
        scrollToBottom();
    } else {
        console.error("Chat box element with ID 'chat-box' not found.");
    }
}

/**
 * Creates a new user chat bubble.
 * @param {string} message - The user's message.
 */
function createUserBubble(message) {
    console.log("Creating user bubble with message:", message); // Debug log
    const bubble = document.createElement("div");
    const p = document.createElement("p");
    p.innerHTML = message;
    bubble.appendChild(p);
    bubble.className = "user-bubble";
    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
        chatBox.appendChild(bubble);
        scrollToBottom();
    } else {
        console.error("Chat box element with ID 'chat-box' not found.");
    }
}

/**
 * Creates a new code chat bubble for displaying code snippets.
 */
function createCodeBubble() {
    console.log("Creating code bubble.");
    const chatBox = document.getElementById("chat-box");
    if (chatBox) {
        const bubble = document.createElement("div");
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.className = "language-python"; // Adjust language as needed

        pre.appendChild(code);
        bubble.appendChild(pre);
        bubble.className = "chat-box-code-bubble";

        chatBox.appendChild(bubble);
        scrollToBottom();
        return code;
    } else {
        console.error("Chat box element with ID 'chat-box' not found.");
    }
}

/**
 * Closes the last active bot bubble by marking it as done.
 * Currently unused in the revised approach.
 */
function closeLastBubble() {
    console.log("Closing last bot bubble if exists.");
    // If you decide to use activeBotBubble, implement the logic here
}

// ==================== Data Preparation and Sending ====================

/**
 * Prepares and sends the user data to the server.
 * @param {string} message - The user's message.
 * @param {Blob|null} audioBlob - The recorded audio blob.
 */
function prepareDataToBeSent(message, audioBlob) {
    console.log("In prepareDataToBeSent, lastInteractionTime:", lastInteractionTime);

    // Parse commands and handle mode toggles
    const { mode, text } = parseCommand(message);
    
    // If it's a command, don't send as a message
    if (mode !== 'normal' && text === message) {
        return; // Command was processed, don't send message
    }

    const formData = new FormData();
    if (audioBlob) {
        formData.append('audio', audioBlob, 'recording.webm'); // Append the audio blob
    }

    formData.append('socket_id', socket.id);
    formData.append('text', text); // Use parsed text (may be different from original message)

    // Add mode flags
    if (chatMode === 'test') {
        formData.append('test', 'true');
    } else if (chatMode === 'memo') {
        formData.append('memo', 'true');
    }

    // Calculate elapsed time
    let elapsedSeconds = 0;
    if (lastInteractionTime !== 0) {
        const currentTime = Date.now();
        elapsedSeconds = Math.floor((currentTime - lastInteractionTime) / 1000);
        lastInteractionTime = 0;
    }
    formData.append('elapsed_time', elapsedSeconds);
    formData.append('speaking_mode', speakingMode);

    // Determine the route based on whether audio is present
    const route = audioBlob ? '/process_audio' : '/process_request';

    fetch(route, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            console.error('Error from server:', data.error);
            // Optionally, display the error to the user
            alert(`Error: ${data.error}`);
        } else if (data.transcribed_text) {
            console.log('Transcribed Text Received:', data.transcribed_text); // Debug log
            // Display the transcribed text as a user message
            createUserBubble(data.transcribed_text);
            prepareDataToBeSent(data.transcribed_text, null);
        } else {
            console.log('Data received:', data);
        }

    })
    .catch(error => {
        console.error('Error sending data:', error);
        // Optionally, display the error to the user
        alert('An error occurred while sending your message. Please try again.');
    });

    // Reset audio chunks after sending
    audioChunks = [];
}

// ==================== Audio Recording Functions ====================

/**
 * Toggles audio recording on or off.
 */
function toggleAudioRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        // Stop recording
        mediaRecorder.stop();
        isRecording = false;
        console.log('Recording stopped.');
    } else {
        // Start recording
        if (mediaStream) {
            startRecording(mediaStream);
        } else {
            // Request microphone access
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(stream => {
                    mediaStream = stream;
                    startRecording(mediaStream);
                })
                .catch(error => {
                    console.error('Error accessing microphone:', error);
                    alert('Microphone access is required to record audio.');
                });
        }
    }
}

/**
 * Initializes and starts the MediaRecorder.
 * @param {MediaStream} stream - The audio stream from the microphone.
 */
function startRecording(stream) {
  audioChunks = [];

  const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent);

  // Explicit codec strings
  const mp4Codec = 'audio/mp4;codecs=mp4a.40.2';
  const webmOpus = 'audio/webm;codecs=opus';

  let mimeType = '';
  if (isIOS && MediaRecorder.isTypeSupported(mp4Codec)) {
    mimeType = mp4Codec;
  } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
    mimeType = 'audio/mp4';
  } else if (MediaRecorder.isTypeSupported(webmOpus)) {
    mimeType = webmOpus;
  }

  const opts = mimeType ? { mimeType } : {};
  try {
    mediaRecorder = new MediaRecorder(stream, opts);
  } catch (err) {
    console.warn("MediaRecorder fallback init", err);
    mediaRecorder = new MediaRecorder(stream);
  }

  console.log("▶️ Recording started with", mediaRecorder.mimeType);

  mediaRecorder.ondataavailable = e => {
    if (e.data && e.data.size > 0) {
      audioChunks.push(e.data);
    }
  };

  mediaRecorder.onstop = () => {
    console.log("⏹️ Recording stopped; chunks:", audioChunks.length);
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });

    // Debug info
    console.log("📦 Blob size (bytes):", blob.size);
    const test = new Audio(URL.createObjectURL(blob));
    test.onloadedmetadata = () => console.log("🕒 Blob duration:", test.duration, "s");

    const input = document.getElementById("chat-input");
    const msg = input?.value.trim() || "";
    if (msg) {
      createUserBubble(msg);
      prepareDataToBeSent(msg, blob);
      input.value = "";
    } else {
      prepareDataToBeSent("", blob);
    }
  };

  // 🔒 Only non-iOS browsers can handle timesliced recording
  if (isIOS) {
    mediaRecorder.start();
  } else {
    mediaRecorder.start(250);  // enables partial data flush on other platforms
  }
}






// ==================== Text-to-Speech Functions ====================

/**
 * Enqueues a TTS audio URL for playback.
 * @param {string} audioUrl - The URL of the TTS audio.
 */
function playTTSAudio(audioUrl) {
    ttsAudioQueue.push(audioUrl);
    if (!isTTSPlaying) {
        playNextTTSAudio();
    }
}

/**
 * Plays a sound from the given URL.
 * @param {string} soundUrl - The URL of the sound file.
 */
function playSound(soundUrl) {
    if (mute) return;

    if (!soundUrl || typeof soundUrl !== 'string' || soundUrl.trim() === '') {
        console.warn('No valid sound URL provided. Skipping audio playback.');
        return;
    }

  audioPlayer.src = soundUrl;
  audioPlayer.volume = 1.2;
  audioPlayer.play().catch(e=>{
    console.error("Error playing sound:", e);
  });
}

// ==================== Widget Handlers Mapping ====================

const widgetHandlers = {
    'email': handleEmailWidget,
    'calendar': handleCalendarWidget,
    'scheduler': handleSchedulerWidget,
    'news': renderNewsWidget, // Add news handler
    'weather': updateWeatherWidget, // Add weather handler
    'todo_task': handleTodoWidget,
    'ask_user': showAskUserModal,
    'notify_user': showNotifyUserModal
    // Add more dedicated widget handlers here
    // For dynamic or unknown widget types, use handleGenericWidget
};

// ==================== Dedicated Widget Handlers ====================

/**
 * Handles generic widgets that don't match predefined types.
 * @param {Array<Object>} widgetDataList - An array of widget data objects.
 */
function handleGenericWidget(widgetDataList) {
    widgetDataList.forEach(widgetData => {
        console.warn("Handling generic widget:", widgetData);

        // Implement your generic widget handling logic here
        const container = document.getElementById("generic-widgets");
        if (!container) {
            console.error("Generic widgets container with ID 'generic-widgets' not found.");
            return;
        }

        const widgetElement = document.createElement("div");
        widgetElement.className = "generic-widget";
        widgetElement.textContent = JSON.stringify(widgetData, null, 2); // Display data as JSON for debugging
        container.prepend(widgetElement);
    });
}

/**
 * Handles 'todo_task' widgets by performing a full refresh of the To-Do List.
 * @param {Array<Object>} todoDataList - An array of To-Do task data objects.
 */
function handleTodoWidget(todoDataList) {
    const todoListContainer = document.getElementById('todo-list');
    if (!todoListContainer) {
        console.error("To-Do list container with ID 'todo-list' not found.");
        return;
    }

    // Optional: sort by due date
    todoDataList.sort((a, b) => {
        const aDue = new Date(a.data.due || 0).getTime();
        const bDue = new Date(b.data.due || 0).getTime();
        return aDue - bDue;
    });


    // Clear existing To-Do items
    todoListContainer.innerHTML = "";
    console.log("To-Do list cleared for full refresh.");

    // Ensure UI updates with "No tasks available"
    if (!Array.isArray(todoDataList) || todoDataList.length === 0) {
        console.warn("No To-Do data provided to handleTodoWidget.");
        todoListContainer.innerHTML = "<li class='todo-empty'>No tasks available.</li>";
        return;
    }

    // Add each To-Do task
    todoDataList.forEach(todoData => {
        addTodoItem(todoData);
    });

    console.log(`To-Do list refreshed with ${todoDataList.length} task(s).`);
}

/**
 * Adds a single task to the To-Do List.
 * @param {Object} taskData - The task data object.
 */
function addTodoItem(taskData) {
    console.log("taskData", taskData);
    taskData = taskData.data;
    const todoListContainer = document.getElementById('todo-list');
    const todoTemplate = document.getElementById('todo-item-template');

    if (!todoListContainer || !todoTemplate) {
        console.error("Todo list container or template not found.");
        return;
    }

    const taskId = taskData.id;
    if (!taskId) {
        console.error("Task data missing unique 'id':", taskData);
        return;
    }

    const existingTask = Array.from(todoListContainer.children).some(
        item => item.dataset.taskId === taskId
    );
    if (existingTask) {
        console.log(`Task with ID ${taskId} already exists. Skipping duplicate.`);
        return;
    }

    const taskElement = todoTemplate.content.cloneNode(true);
    const listItem = taskElement.querySelector('.todo-item');
    const checkbox = listItem.querySelector('input[type="checkbox"]');
    const taskText = listItem.querySelector('.todo-task');
    const dueText = listItem.querySelector('.todo-due');
    const notesText = listItem.querySelector('.todo-notes');

    // Assign unique ID and link label to checkbox
    checkbox.id = `task-${taskId}`;
    listItem.querySelector('label').setAttribute('for', checkbox.id);

    taskText.textContent = taskData.title || 'No Title';
    listItem.dataset.taskId = taskId;

    const isCompleted = taskData.status === "completed";
    if (isCompleted) {
        checkbox.checked = true;
        taskText.classList.add('completed');
        listItem.classList.add('completed-task');
    }

    // Optional due date
    if (taskData.due) {
        dueText.textContent = `Due: ${new Date(taskData.due).toLocaleDateString()}`;
    }

    // Optional notes
    if (taskData.notes) {
        notesText.textContent = taskData.notes;
    }

    // Append based on status
    if (isCompleted) {
        todoListContainer.appendChild(listItem);
    } else {
        todoListContainer.prepend(listItem);
    }

    console.log(`Added task with ID ${taskId}: "${taskData.title || 'No Title'}"`);

    attachTodoCheckboxHandlers()
}

function attachTodoCheckboxHandlers() {
    document.querySelectorAll('.todo-item input[type="checkbox"]').forEach(checkbox => {
        if (checkbox.dataset.handlerAttached === "true") return; // already attached

        checkbox.addEventListener('change', async () => {
            const listItem = checkbox.closest('.todo-item');
            const taskId = listItem.dataset.taskId;
            const taskText = listItem.querySelector('.todo-task');
            const isChecked = checkbox.checked;
            const taskTitle = taskText?.textContent?.trim() || "Untitled";

            // Visual update
            taskText.classList.toggle('completed', isChecked);
            listItem.classList.toggle('completed-task', isChecked);

            const payload = {
                data_type: "ui_tool_request",
                tool_name: "update_todo_task",
                action: "update todo task",
                meta_data: {
                    title: taskTitle,
                    marked_as: isChecked ? "done" : "needs to be done"
                },

                arguments: {
                    task_id: taskId,
                    completed: isChecked ? true : false
                }
            };

            try {
                const response = await callToolRoute("ToDoTool", "update_todo_task", payload);
                if (response?.agent_response) {
                    addFeedItem(response.agent_response);
                }
            } catch (err) {
                console.error("Error calling tool route:", err);
            }
        });

        checkbox.dataset.handlerAttached = "true"; // mark as handled
    });
}


/**
 * Handles 'calendar' widgets by performing a full refresh of the Calendar.
 * @param {Array<Object>} calendarDataList - An array of calendar event data objects.
 */
function handleCalendarWidget(calendarDataList) {
    const calendarList = document.getElementById("calendar-list");
    if (!calendarList) {
        console.error("Calendar list element with ID 'calendar-list' not found.");
        return;
    }

    // Clear the UI container.
    calendarList.innerHTML = "";

    // Flush the internal storage (calendarEventsByDate).
    for (const key in calendarEventsByDate) {
        if (calendarEventsByDate.hasOwnProperty(key)) {
            delete calendarEventsByDate[key];
        }
    }

    if (!Array.isArray(calendarDataList) || calendarDataList.length === 0) {
        console.warn("No calendar data provided to handleCalendarWidget.");
        calendarList.innerHTML = "<li>No calendar events.</li>";
        return;
    }

    // Repopulate the internal storage using the incoming data.
    calendarDataList.forEach(calendarData => {
        addCalendarItem(calendarData);
    });

    console.log(`Calendar refreshed with ${calendarDataList.length} event(s).`);

    // Render events for the currently selected day without changing currentCalendarDate.
    renderCalendarEvents();
}

/**
 * Adds a calendar event to the calendarEventsByDate map, ensuring no duplicates.
 * @param {Object} calendarData - The calendar event data object.
 */
function addCalendarItem(calendarData) {
    const data = calendarData.data;

    const eventTitle = data.event_name || data.summary || "No Title";

    let eventDate;
    if (typeof data.start === 'string') {
        eventDate = new Date(data.start); // New backend sends start as flat UTC ISO string
    } else {
        console.error("Calendar event 'start' field is missing or invalid:", data);
        return;
    }

    const dateKey = getFormattedDate(eventDate); // e.g. '2025-03-25'
    const eventId = data.id;

    if (!eventId) {
        console.error("Calendar event missing unique 'id':", data);
        return;
    }

    // Initialize array for the date if needed
    calendarEventsByDate[dateKey] ||= [];

    const alreadyExists = calendarEventsByDate[dateKey].some(event => event.id === eventId);
    if (alreadyExists) {
        console.log(`Duplicate calendar event "${eventTitle}" skipped for dateKey "${dateKey}"`);
        return;
    }

    calendarEventsByDate[dateKey].push(data);
    console.log(`Event "${eventTitle}" added to "${dateKey}"`);

    if (dateKey === getFormattedDate(currentCalendarDate)) {
        renderCalendarEvents(); // safe to re-render if it matches
    }
}




/**
 * Handles 'email' widgets by performing a full refresh of the Email list.
 * @param {Array<Object>} emailDataList - An array of email data objects.
 */
function handleEmailWidget(emailDataList) {
    const emailList = document.getElementById("email-list");
    const emailTemplate = document.getElementById("email-item-template");

    if (!emailList || !emailTemplate) {
        console.error("Email list container or template not found.");
        return;
    }

    // Clear existing email items
    emailList.innerHTML = "";
    console.log("Email list cleared for full refresh.");

    if (!Array.isArray(emailDataList) || emailDataList.length === 0) {
        console.warn("No email data provided to handleEmailWidget.");
        emailList.innerHTML = "<li>No emails.</li>";
        return;
    }

    // Add each email item
    emailDataList.forEach(emailData => {
        addEmailItem(emailData);
    });

    console.log('Email list refreshed with ${emailDataList.length} email(s).');
}

/**
 * Adds an email item to the Email widget.
 * @param {Object} emailData - The email data object.
 */
function addEmailItem(emailData) {
    emailData = emailData.data
    const emailList = document.getElementById("email-list");
    if (!emailList) {
        console.error("Email list element with ID 'email-list' not found.");
        return;
    }

    // Ensure each email has a unique identifier (using 'uid' instead of 'id')
    const emailUid = emailData.uid;
    if (!emailUid) {
        console.error("Email data missing unique 'uid':", emailData);
        return;
    }

    // Check if the email already exists in the list
    const existingItems = Array.from(emailList.children);
    const alreadyExists = existingItems.some(item => item.dataset.emailUid === emailUid);

    if (alreadyExists) {
        console.log(`Email with UID ${emailUid} already exists. Skipping.`);
        return;
    }

    // Clone the template
    const template = document.getElementById("email-item-template");
    if (!template) {
        console.error("Email item template with ID 'email-item-template' not found.");
        return;
    }

    const emailItem = template.content.cloneNode(true);

    // Add a unique data attribute to track this email
    const emailElement = emailItem.querySelector(".email__item");
    if (emailElement) {
        emailElement.dataset.emailUid = emailUid;
    } else {
        console.error(".email__item not found in template.");
    }

    // Populate the minimal view
    const minimalSender = emailItem.querySelector(".email__sender");
    const minimalSubject = emailItem.querySelector(".email__subject");
    const minimalDate = emailItem.querySelector(".email__date");

    if (minimalSender) minimalSender.textContent = emailData.sender || "Unknown Sender";
    else console.error(".email__sender not found in template.");

    if (minimalSubject) minimalSubject.textContent = emailData.subject || "No Subject";
    else console.error(".email__subject not found in template.");

    if (minimalDate) {
        minimalDate.textContent = emailData.date
            ? new Date(emailData.date).toLocaleString()
            : "";
    } else {
        console.error(".email__date not found in template.");
    }

    // Populate the detailed view dynamically (if needed)
    const detailsView = emailItem.querySelector(".email__item--details");
    if (detailsView) {
        detailsView.classList.add("hidden"); // Hide details by default

        Object.entries(emailData).forEach(([key, value]) => {
            if (!value || key === "uid") return; // Exclude 'uid' from details

            const formattedKey = formatKeyForDisplay(key);
            const formattedValue = formatValue(key, value);

            const detailLine = document.createElement("p");
            detailLine.innerHTML = `<strong>${formattedKey}:</strong> ${formattedValue}`;
            detailsView.appendChild(detailLine);
        });
    } else {
        console.error(".email__item--details not found in template.");
    }

    // Add toggle functionality
    const minimalView = emailItem.querySelector(".email__item--minimal");
    if (minimalView && detailsView) {
        minimalView.addEventListener("click", () => {
            detailsView.classList.toggle("hidden");
        });
    } else {
        console.error("Minimal view or details view elements not found in email item.");
    }

    // Prepend the new email item to the list
    emailList.prepend(emailItem);
}


/**
 * Helper function to format a value for display.
 * @param {string} key - The key associated with the value.
 * @param {string} value - The value to format.
 * @returns {string} The formatted value.
 */
function formatValue(key, value) {
    if (key === "date") {
        return new Date(value).toLocaleString();
    }
    return value;
}


// ==================== Scheduler (Reminders) Variables ====================
let currentSchedulerDate = new Date(); // Tracks the currently displayed date
const schedulerEventsByDate = {}; // Stores scheduler events grouped by date

/**
 * Handles 'scheduler' widgets by performing a full refresh of the Scheduler (Reminders).
 * @param {Array<Object>} schedulerDataList - An array of scheduler event data objects.
 */
function handleSchedulerWidget(schedulerDataList) {
    const schedulerList = document.getElementById("scheduler-list");
    if (!schedulerList) {
        console.error("Scheduler list element with ID 'scheduler-list' not found.");
        return;
    }

    // Clear existing scheduler items
    schedulerList.innerHTML = "";
    console.log("Scheduler list cleared for full refresh.");

    for (const key in schedulerEventsByDate) {
        if (schedulerEventsByDate.hasOwnProperty(key)) {
            delete schedulerEventsByDate[key];
        }
    }


    if (!Array.isArray(schedulerDataList) || schedulerDataList.length === 0) {
        console.warn("No scheduler data provided to handleSchedulerWidget.");
        schedulerList.innerHTML = "<li>No scheduled reminders.</li>";
        return;
    }

    // Add each scheduler event
    schedulerDataList.forEach(schedulerData => {
        addSchedulerItem(schedulerData);
    });

    console.log(`Scheduler refreshed with ${schedulerDataList.length} event(s).`);
    renderSchedulerEvents();
}

function addSchedulerItem(schedulerData) {
    schedulerData = schedulerData.data;
    const eventTitle = schedulerData.title || "No Title";

    // Determine the event date:
    // - Use `occurrence` for recurring events
    // - Use `start_date` for one-time events
    let eventDate;
    if (schedulerData.event_type === "interval" && schedulerData.occurrence) {
        eventDate = new Date(schedulerData.occurrence);
    } else if (schedulerData.start_date) {
        eventDate = new Date(schedulerData.start_date);
    } else {
        console.error("Scheduler event missing 'start_date' or 'occurrence':", schedulerData);
        return;
    }

    // Convert to local time
    const localEventDate = new Date(eventDate.getTime());
    const dateKey = getFormattedDate(localEventDate);
    console.log(`Adding scheduler event "${eventTitle}" to dateKey "${dateKey}"`);

    // Initialize the array for this dateKey if it doesn't exist
    if (!schedulerEventsByDate[dateKey]) {
        schedulerEventsByDate[dateKey] = [];
    }

    // Deduplication: Check if event with the same 'event_id' already exists
    const eventId = schedulerData.event_id;
    if (!eventId) {
        console.error("Scheduler event missing unique 'event_id':", schedulerData);
        return;
    }

    const existingEvent = schedulerEventsByDate[dateKey].find(event => event.event_id === eventId);
    if (existingEvent) {
        console.log(`Event with ID ${eventId} already exists for date ${dateKey}. Skipping duplicate.`);
        return;
    }

    schedulerEventsByDate[dateKey].push(schedulerData);
    console.log(`Event with ID ${eventId} added successfully.`);

    if (dateKey === getFormattedDate(currentSchedulerDate)) {
        renderSchedulerEvents();
    }
}

/**
 * Renders the scheduler (reminder) events for the currentSchedulerDate.
 */
function renderSchedulerEvents() {
    const schedulerList = document.getElementById("scheduler-list");
    if (!schedulerList) {
        console.error("Scheduler list element not found.");
        return;
    }
    const currentDateKey = getFormattedDate(currentSchedulerDate);
    const events = schedulerEventsByDate[currentDateKey] || [];

    console.log(`Rendering scheduler events for dateKey "${currentDateKey}" with ${events.length} event(s).`);

    // Update the current date display
    const currentDateDisplay = document.getElementById("scheduler-current-date");
    if (currentDateDisplay) {
        currentDateDisplay.textContent = currentSchedulerDate.toDateString();
    } else {
        console.error("Element with ID 'scheduler-current-date' not found.");
    }

    // Clear existing events
    schedulerList.innerHTML = '';

    if (events.length === 0) {
        schedulerList.innerHTML = '<li>No reminders for this day.</li>';
        return;
    }

    // Sort events by actual start time:
    // - Use `occurrence` for recurring events
    // - Use `start_date` for one-time events
    events.sort((a, b) => {
        const timeA = a.occurrence
            ? new Date(a.occurrence).getTime()
            : (a.start_date ? new Date(a.start_date).getTime() : Infinity);
        const timeB = b.occurrence
            ? new Date(b.occurrence).getTime()
            : (b.start_date ? new Date(b.start_date).getTime() : Infinity);
        return timeA - timeB;
    });

    // Add each event to the scheduler list
    events.forEach(event => {
        const template = document.getElementById("scheduler-item-template");
        if (!template) {
            console.error("Scheduler item template with ID 'scheduler-item-template' not found.");
            return;
        }

        const schedulerItem = template.content.cloneNode(true);

        // Populate minimal view
        const minimalTitle = schedulerItem.querySelector(".scheduler__task-title");
        if (minimalTitle) {
            minimalTitle.textContent = event.title || "No Title";
        }

        const minimalDeadline = schedulerItem.querySelector(".scheduler__task-deadline");
        if (minimalDeadline) {
            let eventTime;
            if (event.occurrence) {
                eventTime = new Date(event.occurrence).toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit"
                });
            } else if (event.start_date) {
                eventTime = new Date(event.start_date).toLocaleTimeString([], {
                    hour: "numeric",
                    minute: "2-digit"
                });
            } else {
                console.error("No valid start time found for event:", event);
                eventTime = "No Time";
            }
            minimalDeadline.textContent = eventTime;
        }


        // Populate detailed view dynamically
        const detailsView = schedulerItem.querySelector(".scheduler__item--details");
        if (detailsView) {
            detailsView.classList.add("hidden"); // Hide details by default
            Object.entries(event).forEach(([key, value]) => {
                if (!value || key === "event_id" || key === "occurrence") return;
                const formattedKey = formatKeyForDisplay(key);
                const formattedValue = formatValue(key, value);
                const detailLine = document.createElement("p");
                detailLine.innerHTML = `<strong>${formattedKey}:</strong> ${formattedValue}`;
                detailsView.appendChild(detailLine);
            });
        }

        // Add toggle functionality for details
        const minimalView = schedulerItem.querySelector(".scheduler__item--minimal");
        if (minimalView && detailsView) {
            minimalView.addEventListener("click", () => {
                detailsView.classList.toggle("hidden");
            });
        }

        schedulerList.appendChild(schedulerItem);
    });
}

/**
 * Sets up event listeners for scheduler navigation.
 */
function setupSchedulerNavigation() {
    const prevBtn = document.getElementById("scheduler-prev-btn");
    const nextBtn = document.getElementById("scheduler-next-btn");

    if (prevBtn && nextBtn) {
        // Add the shared styling class to match calendar arrows
        prevBtn.classList.add('arrow-btn');
        nextBtn.classList.add('arrow-btn');

        prevBtn.addEventListener("click", () => {
            currentSchedulerDate.setDate(currentSchedulerDate.getDate() - 1);
            renderSchedulerEvents();
        });

        nextBtn.addEventListener("click", () => {
            currentSchedulerDate.setDate(currentSchedulerDate.getDate() + 1);
            renderSchedulerEvents();
        });
    } else {
        console.error("Scheduler navigation buttons not found.");
    }
}

/**
 * Renders content for generic widgets based on result_type.
 * @param {string} resultType - The type of the widget.
 * @param {Object} data - The data object for the widget.
 * @param {HTMLElement} container - The container to render content into.
 */
function renderGenericWidgetContent(resultType, data, container) {
    switch (resultType.toLowerCase()) {
        case 'weather':
            // **Correction Applied: Changed 'renderWeatherWidget' to 'updateWeatherWidget'**
            updateWeatherWidget(data); // Removed 'container' as 'updateWeatherWidget' does not accept it
            break;
        case 'news':
            renderNewsWidget(data, container);
            break;
        // Add more cases for known widget types
        default:
            // For truly dynamic or unknown types, use the generic widget item function
            addGenericWidgetItem(data, container);
            break;
    }
}

/**
 * Renders the weather data into the Weather widget.
 * @param {Object} weatherData - The weather data object.
 */
/**
 * Renders the weather data into the Weather widget.
 */
function updateWeatherWidget(weatherData) {
    console.log("Raw Weather Data: ", weatherData);

    // Validate weatherData structure before proceeding
    if (!Array.isArray(weatherData) || weatherData.length === 0 || !weatherData[0].data) {
        console.error("Invalid weather data format:", weatherData);
        return;
    }

    // Extract first object from the array
    const dataObject = weatherData[0].data;

    // Validate if weather_data exists and has at least one entry
    if (!dataObject.weather_data || !Array.isArray(dataObject.weather_data) || dataObject.weather_data.length === 0) {
        console.error("Missing or empty weather_data:", dataObject);
        return;
    }

    // Extract the actual weather object from the weather_data array
    const weather = dataObject.weather_data[0];

    console.log("Processed Weather Data: ", weather);

    const weatherWidget = document.querySelector('.weather-box');
    if (!weatherWidget) {
        console.error("Weather widget not found in DOM.");
        return;
    }

    // Validate that location exists before accessing properties
    if (!weather.location || !weather.location.name || !weather.location.country) {
        console.error("Location data is missing or malformed:", weather.location);
        return;
    }

    const location = `${weather.location.name}, ${weather.location.country}`;
    const temperature = `${weather.weather.temperature.toFixed(0)}`;
    const condition = weather.weather.description;
    const High = `High: ${weather.weather.max_temperature}`;
    const Low = `Low: ${weather.weather.min_temperature}`;

    window.globalSunrise = new Date(weather.sun_times?.sunrise || "").toLocaleTimeString();
    window.globalSunset = new Date(weather.sun_times?.sunset || "").toLocaleTimeString();

    // Update the DOM elements safely
    document.getElementById("weather_temp_number").textContent = temperature;
    document.getElementById("weather_place").textContent = location;
    document.getElementById("weather_condition").textContent = condition;
    document.getElementById("weather_high").textContent = High;
    document.getElementById("weather_low").textContent = Low;

    console.log("Sunrise: " + window.globalSunrise);
    console.log("Sunset: " + window.globalSunset);
}



/**
 * Renders a news widget.
 * @param {Object} data - The news data object.
 * @param {HTMLElement} container - The container to render content into.
 */
function renderNewsWidget(newsData, container) {
    console.log("Processing news widget data:", newsData);

    // Extract the actual news data from each item
    const validNewsItems = newsData
        .filter(item => item?.data_type?.toLowerCase() === "news")
        .map(item => item.data);

    console.log("Valid news items:", validNewsItems);

    const newsContainer = document.getElementById("news-widget");
    if (!newsContainer) {
        console.error("News container not found.");
        return;
    }

    console.log("News container found:", newsContainer);

    if (!validNewsItems.length) {
        if (!newsContainer.children.length) {
            newsContainer.innerHTML = '<p>No news available.</p>';
        }
        console.log("No valid news items to render");
        return;
    }

    // Render each news item with thumbs up/down buttons
    validNewsItems.forEach((news, index) => {
        console.log(`Processing news item ${index}:`, news);
        
        if (!news.link) {
            console.warn("Skipping news item without a link:", news);
            return;
        }

        const existingItem = Array.from(newsContainer.children).find(
            child => child.dataset.newsId === news.link
        );
        if (existingItem) {
            console.log(`News item with link ${news.link} already exists, skipping`);
            return;
        }

        console.log(`Creating new news item for: ${news.title}`);

        const newsItem = document.createElement("div");
        newsItem.className = "news-item";
        newsItem.dataset.newsId = news.link;

        newsItem.innerHTML = `
            <h3><a href="${news.link}" target="_blank">${news.title || "No Title"}</a></h3>
            ${news.summary ? `<p>${news.summary}</p>` : ''}
            ${news.published ? `<p class="news-date">${new Date(news.published).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "numeric",
                minute: "2-digit",
                hour12: true
            })}</p>` : ''}
            ${news.source ? `<p class="news-source">Source: ${news.source}</p>` : ''}
            <div class="news-footer">
              <div class="news-actions">
                <button class="thumbs-up" data-id="${news.link}" aria-label="Thumbs up">
                  <i class="fas fa-thumbs-up"></i>
                </button>
                <button class="thumbs-down" data-id="${news.link}" aria-label="Thumbs down">
                  <i class="fas fa-thumbs-down"></i>
                </button>
              </div>
            </div>
            `;

        newsContainer.prepend(newsItem);
        console.log(`News item created and added to container:`, newsItem);

        // Add event listeners to the newly created buttons
        const thumbsUpBtn = newsItem.querySelector('.thumbs-up');
        const thumbsDownBtn = newsItem.querySelector('.thumbs-down');
        
        console.log('Created thumbs up button:', thumbsUpBtn);
        console.log('Created thumbs down button:', thumbsDownBtn);
        
        if (thumbsUpBtn) {
            thumbsUpBtn.addEventListener('click', (event) => {
                console.log('Thumbs up button clicked!');
                handleThumbs('up', event);
            });
        }
        
        if (thumbsDownBtn) {
            thumbsDownBtn.addEventListener('click', (event) => {
                console.log('Thumbs down button clicked!');
                handleThumbs('down', event);
            });
        }
    });

    // Remove the old event listener setup that was causing issues
    // document.querySelectorAll(".thumbs-up, .thumbs-down").forEach(button => {
    //     button.removeEventListener("click", handleThumbs);
    //     button.addEventListener("click", event => handleThumbs(event.target.classList.contains("thumbs-up") ? "up" : "down", event));
    // });
}



/**
 * Renders a generic widget item with minimal and detailed views.
 * @param {Object} data - The data object for the widget.
 * @param {HTMLElement} container - The container to render content into.
 */
function addGenericWidgetItem(data, container) {
    const { title, description, ...metadata } = data; // Extract title and description

    // Clone the generic widget item template
    const template = document.getElementById("generic-widget-template");
    if (!template) {
        console.error("Generic widget item template with ID 'generic-widget-template' not found.");
        return;
    }

    const widgetItem = template.content.cloneNode(true);

    // Populate minimal view
    const minimalTitle = widgetItem.querySelector(".generic-widget__title");
    const minimalDescription = widgetItem.querySelector(".generic-widget__description");

    if (minimalTitle) {
        minimalTitle.textContent = title || 'No Title';
    } else {
        console.error(".generic-widget__title not found in template.");
    }

    if (minimalDescription) {
        minimalDescription.textContent = description || 'No Description';
    } else {
        console.error(".generic-widget__description not found in template.");
    }

    // Populate detailed view dynamically
    const detailsView = widgetItem.querySelector(".generic-widget__item--details");
    if (detailsView) {
        detailsView.classList.add("hidden"); // Hide details by default

        const excludedKeys = ['data_type', 'title', 'description']; // Exclude certain keys

        Object.entries(metadata).forEach(([key, value]) => {
            if (excludedKeys.includes(key) || !value || value === "N/A") {
                return; // Skip this key
            }

            // Format the key and value
            const formattedKey = formatKeyForDisplay(key);
            const formattedValue = formatValue(key, value);

            // Create and append the detail line
            const detailLine = document.createElement("p");
            detailLine.innerHTML = `<strong>${formattedKey}:</strong> ${formattedValue}`;
            detailsView.appendChild(detailLine);
        });
    } else {
        console.error(".generic-widget__item--details not found in template.");
    }

    // Add toggle functionality
    const minimalView = widgetItem.querySelector(".generic-widget__item--minimal");
    if (minimalView && detailsView) {
        minimalView.addEventListener("click", () => {
            detailsView.classList.toggle("hidden");
        });
    } else {
        console.error("Minimal view or details view elements not found in generic widget item.");
    }

    // Append to dynamic widgets area
    container.prepend(widgetItem); // Add to the top
}

/**
 * Capitalizes the first letter of a string.
 * @param {string} string - The string to capitalize.
 * @returns {string} - The capitalized string.
 */
function capitalizeFirstLetter(string) {
    if (!string) return '';
    return string.charAt(0).toUpperCase() + string.slice(1);
}

// ===============Ask user modal

function showAskUserModal(widgetItems) {
    const questionData = widgetItems[0];
    const question = questionData.question;
    const question_id = questionData.question_id;

    let modal = document.getElementById("ask-user-modal");
    if (!modal) {
        modal = document.createElement("div");
        modal.id = "ask-user-modal";
        modal.className = "ask-user-modal";

        modal.innerHTML = `
            <div class="ask-user-content">
                <div id="ask-user-question"></div>
                <input id="ask-user-input" type="text" placeholder="Type your answer..." />
                <button id="ask-user-submit">Submit</button>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById("ask-user-question").innerHTML = question;

    document.getElementById("ask-user-submit").onclick = async () => {
        const answer = document.getElementById("ask-user-input").value.trim();
        if (answer) {
            await sendAskUserResponse(question_id, answer);  // ✅ Route call here
            modal.remove();  // ✅ Modal disappears after response is sent
        }
    };
}

// =============== Notify user modal

function showNotifyUserModal(widgetItems) {
    console.log("Entering showNotifyUserModal")
    console.log(widgetItems)
    const notifyData = widgetItems[0];
    const message = notifyData.message;

    console.log(notifyData)
    console.log(message)

    let modal = document.getElementById("notify-user-modal");
    if (!modal) {
        modal = document.createElement("div");
        modal.id = "notify-user-modal";
        modal.className = "notify-user-modal";

        modal.innerHTML = `
            <div class="notify-user-content">
                <div id="notify-user-message"></div>
                <button id="notify-user-close">OK</button>
            </div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById("notify-user-message").innerHTML = message;

    document.getElementById("notify-user-close").onclick = () => {
        modal.remove();  // ✅ Just dismisses the modal
    };
}


// ==================== Socket.IO Event Handlers ====================

/**
 * Handles incoming Socket.IO events.
 */
function setupSocketListeners() {
    socket.on('connect', () => {
        console.log("Connected to the server via Socket.IO.");
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from the server.');
    });

    socket.on('user_message_data', data => {
        console.log("Received UserMessageData:", data);

        try {
            // Always process chat first
            if (data.chat && data.chat.trim() !== "") {
                console.log("Rendering chat message:", data.chat);
                createBotBubble(data.chat);
            } else {
                console.warn("No chat message found in received data.");
            }

            // Always process feed
            if (data.feed && data.feed.trim() !== "") {
                console.log("Adding feed item:", data.feed);
                addFeedItem(data.feed);
            }

            // Always process sound
            if (data.sound && typeof data.sound === 'string' && data.sound.trim() !== '') {
                const soundKey = data.sound.trim();
                if (soundKey in soundLib) {
                    playSound(soundLib[soundKey]);
                } else if (soundKey === 'default' || soundKey === 'notification') {
                    playRandomNotificationSound();
                } else {
                    console.warn("Unknown sound key:", soundKey);
                }
            }


            // Process widgets safely
            if (Array.isArray(data.widget_data) && data.widget_data.length > 0) {
                try {
                    const widgetsByType = {};

                    data.widget_data.forEach(widgetItem => {
                        if (!widgetItem.data_type || typeof widgetItem.data_type !== 'string') {
                            console.warn("Widget item missing or invalid 'data_type':", widgetItem);
                            handleGenericWidget([widgetItem]); // Handle unknown widgets safely
                            return;
                        }

                        const widgetType = widgetItem.data_type.trim().toLowerCase();

                        if (!widgetsByType[widgetType]) {
                            widgetsByType[widgetType] = [];
                        }

                        widgetsByType[widgetType].push(widgetItem);
                    });

                    Object.entries(widgetsByType).forEach(([widgetType, widgetItems]) => {
                        console.log(`Processing widget type: ${widgetType} with ${widgetItems.length} item(s)`);
                        const handler = widgetHandlers[widgetType] || handleGenericWidget;

                        try {
                            handler(widgetItems); // Call appropriate handler
                        } catch (widgetError) {
                            console.error(`Error processing widget type: ${widgetType}`, widgetError);
                        }
                    });
                } catch (widgetProcessingError) {
                    console.error("Critical error processing widget data:", widgetProcessingError);
                }
            } else {
                console.warn("No widget data received or not in array format.");
            }
        } catch (error) {
            console.error("Unexpected error processing UserMessageData:", error);
        }
    });



    socket.on('audio_file', audioData => {
        console.log(`Received audio file URL: ${audioData.audio_url}`);
        audioQueue.push(audioData.audio_url);
        if (!isAudioPlaying) {
            playNextAudio();
        }
    });
}

socket.on('repo_update_notification', (updateData) => {
    console.log("Received repo update notification:", updateData);

        fetchRepoData();

});

/**
 * Adds a feed item to the top of the feed list with timestamp and limits total items.
 * @param {string} text - The feed text.
 */
function addFeedItem(text) {
    const feedList = document.getElementById("feed-list");
    const maxItems = 50;

    if (!feedList) {
        console.error("Feed list element with ID 'feed-list' not found.");
        return;
    }

    const listItem = document.createElement("li");
    listItem.className = "feed-item";

    // Create timestamp element
    const timestamp = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const metaDiv = document.createElement("div");
    metaDiv.className = "feed__meta";
    metaDiv.innerHTML = `<span class="feed__timestamp">${timestamp}</span>`;

    // Create content container
    const contentDiv = document.createElement("div");
    contentDiv.className = "feed__content";

    // Accept either plain string or rich HTML
    if (typeof text === "string") {
        contentDiv.innerHTML = text;
    } else {
        contentDiv.appendChild(text); // If it's a node (for future-proofing)
    }

    // Assemble the list item
    listItem.appendChild(metaDiv);
    listItem.appendChild(contentDiv);
    feedList.prepend(listItem);
    console.log("Added feed item at the top:", text);

    // Remove excess
    while (feedList.children.length > maxItems) {
        const lastItem = feedList.lastChild;
        feedList.removeChild(lastItem);
        console.log("Removed oldest feed item:", lastItem.textContent);
    }
}


// ==================== Event Listeners ====================

/**
 * Sets up event listeners for user interactions.
 */
function setupEventListeners() {
    // Handle form submission
    const chatForm = document.querySelector(".chat-form");
    if (chatForm) {
        chatForm.addEventListener('submit', function(event) {
            event.preventDefault(); // Prevent the default form submission
            console.log("Chat form submitted.");

            const messageInput = document.getElementById("chat-input"); // Updated ID
            if (messageInput) {
                const message = messageInput.value.trim();
                if (message === "") return;

                createUserBubble(message);
                prepareDataToBeSent(message, null); // No audio blob
                messageInput.value = "";
            } else {
                console.error("Input element with ID 'chat-input' not found.");
            }
        });
    } else {
        console.error("Chat form element with class 'chat-form' not found.");
    }

    // Handle audio playback toggle
    const audioPlaybackBtn = document.getElementById('mute-btn-container');
    if (audioPlaybackBtn) {
        audioPlaybackBtn.addEventListener('click', () => {
            const muteIcon = document.getElementById('mute-icon');
            const unmuteIcon = document.getElementById('unmute-icon');
            if (muteIcon && unmuteIcon) {
                muteIcon.classList.toggle('hidden');
                unmuteIcon.classList.toggle('hidden');
                mute = !mute; // Ensure 'mute' is defined in the appropriate scope
            } else {
                console.error("Mute or Unmute icon elements not found.");
            }
        });
    } else {
        // Corrected the ID in the error message to match the selected element
        console.error("Audio playback button container with ID 'mute-btn-container' not found.");
    }

    // Toggle audio recording
    const recordBtnIcon = document.getElementById("record-btn-icon");
    if (recordBtnIcon) {
        recordBtnIcon.addEventListener('click', () => {
            const recordBtnOff = document.getElementById("record-btn-off");
            const recordBtnOn = document.getElementById("record-btn-on");
            if (recordBtnOff && recordBtnOn) {
                recordBtnOff.classList.toggle('hidden');
                recordBtnOn.classList.toggle('hidden');

                // Toggle the 'active' class based on the current recording state
                recordBtnIcon.classList.toggle('active');

                // Toggle audio recording functionality
                toggleAudioRecording();

                // Remove focus to prevent :focus styling from persisting
                recordBtnIcon.blur();
            } else {
                console.error("Record button icons with IDs 'record-btn-off' and 'record-btn-on' not found.");
            }
        });
    } else {
        console.error("Record button icon with ID 'record-btn-icon' not found.");
    }

    // Handle user typing a message and pressing Enter
    const messageInput = document.getElementById("chat-input"); // Updated ID
    if (messageInput) {
        messageInput.addEventListener('keydown', event => { // Changed from 'keyup' to 'keydown'
            if (event.key === 'Enter') {
                if (event.shiftKey) {
                    // Allow Shift+Enter to insert a newline
                    return;
                }

                event.preventDefault(); // Prevent the default newline insertion
                const message = messageInput.value.trim();
                if (message === "") return;

                createUserBubble(message);
                prepareDataToBeSent(message, null); // No audio blob
                messageInput.value = "";
            }
        });

        // Handle user input events to manage timeouts or other behaviors
        messageInput.addEventListener('input', () => {
            if (window.chatbotTimeout) {
                console.log("Clearing the chatbotTimeout");
                clearTimeout(window.chatbotTimeout);
                window.chatbotTimeout = null; // Reset the timeout reference
            }
            // Optionally, set a new timeout if needed
        });
    } else {
        console.warn("Message input element with ID 'chat-input' not found.");
    }
}

function setupThemeListener()
{
    // Old theme toggle button (kept for backwards compatibility if needed)
    const oldThemeBtn = document.getElementById('theme-toggle');
    if (oldThemeBtn) {
        oldThemeBtn.addEventListener('click', toggleTheme);
    }
    
    // New menu-based theme toggle
    const menuThemeBtn = document.getElementById('menu-theme-toggle');
    if (menuThemeBtn) {
        menuThemeBtn.addEventListener('click', () => {
            toggleTheme();
            updateThemeIcon();
        });
    }
}

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = (currentTheme === 'light') ? 'dark' : 'light';
    html.setAttribute('data-theme', newTheme);
}

function updateThemeIcon() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const menuThemeBtn = document.getElementById('menu-theme-toggle');
    if (menuThemeBtn) {
        const icon = menuThemeBtn.querySelector('i');
        if (icon) {
            icon.className = currentTheme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }
    }
}

// ===== Menu Toggle Functionality =====
function setupMenuToggle() {
    const menuToggleBtn = document.getElementById('menu-toggle-btn');
    const dropdownMenu = document.getElementById('dropdown-menu');
    
    if (!menuToggleBtn || !dropdownMenu) {
        console.warn('Menu elements not found');
        return;
    }
    
    // Toggle menu on button click
    menuToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        dropdownMenu.classList.toggle('hidden');
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!dropdownMenu.contains(e.target) && e.target !== menuToggleBtn) {
            dropdownMenu.classList.add('hidden');
        }
    });
    
    // Setup submenu toggles
    const submenuToggles = document.querySelectorAll('.submenu-toggle');
    submenuToggles.forEach(toggle => {
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const parentItem = toggle.closest('.menu-submenu');
            if (parentItem) {
                parentItem.classList.toggle('open');
            }
        });
    });
    
    // Menu Speak Mode Toggle
    const menuSpeakBtn = document.getElementById('menu-speak-mode');
    if (menuSpeakBtn) {
        menuSpeakBtn.addEventListener('click', () => {
            speakingMode = !speakingMode;
            const span = menuSpeakBtn.querySelector('span');
            if (span) {
                span.textContent = speakingMode ? 'Speak Mode: On' : 'Speak Mode: Off';
            }
            menuSpeakBtn.setAttribute('aria-pressed', speakingMode);
            
            // Try unlocking audio on iOS
            if (/iP(hone|ad|od)/.test(navigator.userAgent) && audioPlayer) {
                const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";
                audioPlayer.src = SILENT;
                audioPlayer.play()
                    .then(() => {
                        audioPlayer.pause();
                        audioPlayer.src = "";
                    })
                    .catch(e => console.warn('Audio unlock failed', e));
            }
        });
    }
    
    // Menu Quiet Mode Toggle
    const menuQuietBtn = document.getElementById('menu-quiet-mode');
    if (menuQuietBtn) {
        // Load initial state
        fetch('/api/settings/quiet-mode')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    const isEnabled = data.quiet_mode.enabled;
                    updateQuietModeUI(isEnabled);
                }
            })
            .catch(err => console.error('Error loading quiet mode state:', err));
        
        menuQuietBtn.addEventListener('click', async () => {
            try {
                const response = await fetch('/api/settings/quiet-mode/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await response.json();
                
                if (data.success) {
                    updateQuietModeUI(data.enabled);
                    showNotification(data.message, 'success');
                } else {
                    showNotification(data.message || 'Failed to toggle quiet mode', 'error');
                }
            } catch (error) {
                console.error('Error toggling quiet mode:', error);
                showNotification('Error toggling quiet mode', 'error');
            }
        });
        
        function updateQuietModeUI(isEnabled) {
            const span = menuQuietBtn.querySelector('span');
            const icon = menuQuietBtn.querySelector('i');
            if (span) {
                span.textContent = isEnabled ? 'Quiet Mode: On' : 'Quiet Mode: Off';
            }
            if (icon) {
                icon.className = isEnabled ? 'fas fa-moon' : 'fas fa-moon';
            }
            menuQuietBtn.setAttribute('aria-pressed', isEnabled);
            menuQuietBtn.classList.toggle('active', isEnabled);
        }
    }
    
    // Ngrok Toggle
    const ngrokBtn = document.getElementById('menu-ngrok-toggle');
    if (ngrokBtn) {
        ngrokBtn.addEventListener('click', async () => {
            const isActive = ngrokBtn.getAttribute('data-active') === 'true';
            const span = ngrokBtn.querySelector('span');
            
            if (isActive) {
                // Stop ngrok
                try {
                    const response = await fetch('/ngrok/stop', { method: 'POST' });
                    const data = await response.json();
                    
                    if (data.success) {
                        ngrokBtn.setAttribute('data-active', 'false');
                        if (span) span.textContent = 'Start Ngrok';
                        showModeNotification('Ngrok stopped');
                    } else {
                        showModeNotification('Failed to stop Ngrok');
                    }
                } catch (error) {
                    console.error('Error stopping ngrok:', error);
                    showModeNotification('Error stopping Ngrok');
                }
            } else {
                // Start ngrok
                try {
                    const response = await fetch('/ngrok/start', { method: 'POST' });
                    const data = await response.json();
                    
                    if (data.success) {
                        ngrokBtn.setAttribute('data-active', 'true');
                        if (span) span.textContent = 'Stop Ngrok';
                        showModeNotification(`Ngrok started! Email sent with link.`);
                    } else {
                        showModeNotification('Failed to start Ngrok');
                    }
                } catch (error) {
                    console.error('Error starting ngrok:', error);
                    showModeNotification('Error starting Ngrok');
                }
            }
        });
    }
}

/**
 * Initializes the currentCalendarDate to the earliest date with events.
 */
function initializeCurrentCalendarDate() {
    const dates = Object.keys(calendarEventsByDate);
    if (dates.length > 0) {
        dates.sort(); // Sort dates in ascending order
        currentCalendarDate = new Date(dates[0]); // Set to the first date
    } else {
        currentCalendarDate = new Date(); // Default to today if no events
    }
}

/**
 * Sets up event listeners for calendar navigation buttons.
 */
function setupCalendarNavigation() {
    const prevBtn = document.getElementById("calendar-prev-btn");
    const nextBtn = document.getElementById("calendar-next-btn");

    if (prevBtn && nextBtn) {
        prevBtn.addEventListener("click", () => {
            currentCalendarDate.setDate(currentCalendarDate.getDate() - 1);
            renderCalendarEvents();
        });

        nextBtn.addEventListener("click", () => {
            currentCalendarDate.setDate(currentCalendarDate.getDate() + 1);
            renderCalendarEvents();
        });
    } else {
        console.error("Calendar navigation buttons not found.");
    }
}

/**
 * Renders the calendar events for the currentCalendarDate.
 */
function renderCalendarEvents() {
    const calendarList = document.getElementById("calendar-list");
    const currentDateKey = getFormattedDate(currentCalendarDate);
    const events = calendarEventsByDate[currentDateKey] || [];

    console.log(`Rendering events for dateKey "${currentDateKey}" with ${events.length} event(s).`);

    // Update the current date display
    const currentDateDisplay = document.getElementById("calendar-current-date");
    if (currentDateDisplay) {
        currentDateDisplay.textContent = currentCalendarDate.toDateString();
    } else {
        console.error("Element with ID 'calendar-current-date' not found.");
    }

    // Clear existing events
    calendarList.innerHTML = '';

    if (events.length === 0) {
        calendarList.innerHTML = '<li>No events for this day.</li>';
        return;
    }

    // Sort events: all-day events first, then by start time (earliest first)
    events.sort((a, b) => {
        // All-day events always come first
        const aAllDay = a.is_all_day === true;
        const bAllDay = b.is_all_day === true;
        
        if (aAllDay && !bAllDay) return -1;  // a is all-day, b is not → a first
        if (!aAllDay && bAllDay) return 1;   // b is all-day, a is not → b first
        
        // Both are same type, sort by start time
        const getStartTime = event => {
            // Check various possible field names for start time
            if (event.start && typeof event.start === 'string') {
                // Most common: flat ISO string from backend
                return new Date(event.start).getTime();
            } else if (event.start_time) {
                return new Date(event.start_time).getTime();
            } else if (event.start && typeof event.start === 'object' && event.start.dateTime) {
                // Google Calendar format
                return new Date(event.start.dateTime).getTime();
            } else if (event.start_dateTime) {
                return new Date(event.start_dateTime).getTime();
            }
            return 0;
        };
        return getStartTime(a) - getStartTime(b);
    });

    // Add each event to the calendar list
    events.forEach(event => {
        const template = document.getElementById("calendar-item-template");
        if (!template) {
            console.error("Calendar item template with ID 'calendar-item-template' not found.");
            return;
        }

        const calendarItem = template.content.cloneNode(true);

        // Populate minimal view
        const minimalTitle = calendarItem.querySelector(".calendar__event-title");
        const minimalTime = calendarItem.querySelector(".calendar__event-time");

        const timeOptions = { hour: 'numeric', minute: '2-digit' };

        // Handle all-day events
        if (event.is_all_day === true) {
            if (minimalTime) {
                minimalTime.textContent = "All Day";
            }
        } else {
            let eventStartTime = "No Start Time";
            if (event.start && typeof event.start === 'string') {
                eventStartTime = new Date(event.start).toLocaleTimeString([], timeOptions);
            }

            let eventEndTime = null;
            if (event.end && typeof event.end === 'string') {
                eventEndTime = new Date(event.end).toLocaleTimeString([], timeOptions);
            }

            if (minimalTime) {
                if (eventEndTime) {
                    minimalTime.innerHTML = `${eventStartTime}<br>${eventEndTime}`;
                } else {
                    minimalTime.textContent = eventStartTime;
                }
            }
        }



        if (minimalTitle) {
            minimalTitle.textContent = event.summary || "No Title";
        } else {
            console.error(".calendar__event-title not found in template.");
        }

        // Populate detailed view
        const detailsView = calendarItem.querySelector(".calendar__item--details");
        if (detailsView) {
            detailsView.classList.add("hidden"); // Hide details by default

            const excludedKeys = ['data_type'];
            Object.entries(event).forEach(([key, value]) => {
                if (excludedKeys.includes(key) || !value || value === "N/A") return;

                const formattedKey = formatKeyForDisplay(key);
                const formattedValue = formatValue(key, value);

                const detailLine = document.createElement("p");
                detailLine.innerHTML = `<strong>${formattedKey}:</strong> ${formattedValue}`;
                detailsView.appendChild(detailLine);
            });
        } else {
            console.error(".calendar__item--details not found in template.");
        }

        // Add toggle functionality for details
        const minimalView = calendarItem.querySelector(".calendar__item--minimal");
        if (minimalView && detailsView) {
            minimalView.addEventListener("click", () => {
                detailsView.classList.toggle("hidden");
            });
        } else {
            console.error("Minimal view or details view elements not found in calendar item.");
        }

        // Append the event to the calendar list
        calendarList.appendChild(calendarItem);
    });
}

/**
 * Sends a request to a tool route with optional payload.
 * @param {string} toolName - The name of the tool (e.g., "todo", "calendar").
 * @param {string} action - The action (e.g., "update", "delete").
 * @param {Object} payload - Optional JSON body to send.
 * @returns {Promise<Object>} - The parsed JSON response.
 */
async function callToolRoute(toolName, action, payload = {}) {
    const url = /tool/;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status} - ${response.statusText}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`Error calling tool route: ${toolName}/${action}`, error);
        return { success: false, error: error.message };
    }
}


// ==================== Initialization ====================


document.addEventListener('DOMContentLoaded', () => {
    setupSocketListeners();
    setupEventListeners();
    attachIdleListeners();
    resetIdleTimer();
    // If the tab becomes hidden (user locks screen / switches tabs), browsers may throttle timers.
    // Send a best-effort idle ping once so server-side maintenance can run.
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            try { invokeIdleRoute(); } catch (e) { /* best-effort */ }
        }
    });
    // Some browsers fire pagehide instead of beforeunload.
    window.addEventListener('pagehide', () => {
        try { invokeIdleRoute(); } catch (e) { /* best-effort */ }
    });
    setupThemeListener();
    setupMenuToggle(); // Initialize the hamburger menu
    setupCalendarNavigation();
    initializeCurrentCalendarDate();
    renderCalendarEvents();
    setupSchedulerNavigation();
    setupChatWidgetExpansion();
    console.log("DOM fully loaded. Fetching repo data...");
    fetchRepoData();
});
function setupChatWidgetExpansion() {
    const chatWidget = document.querySelector('.widget--chat');
    if (!chatWidget) {
        console.warn('Chat widget not found.');
        return;
    }

    const expandButton = document.createElement('button');
    expandButton.id = 'expand-chat-btn';
    expandButton.innerHTML = '<i class="fas fa-expand"></i>';
    expandButton.setAttribute('aria-label', 'Expand Chat');

    const closeButton = document.createElement('button');
    closeButton.id = 'close-chat-btn';
    closeButton.innerHTML = '<i class="fas fa-times"></i>';
    closeButton.setAttribute('aria-label', 'Close Chat');
    closeButton.classList.add('hidden');

    chatWidget.appendChild(expandButton);
    chatWidget.appendChild(closeButton);

    const otherWidgets = document.querySelectorAll('.widget:not(.widget--chat)');

    expandButton.addEventListener('click', () => {
        chatWidget.classList.add('expanded');
        expandButton.classList.add('hidden');
        closeButton.classList.remove('hidden');
        otherWidgets.forEach(widget => widget.classList.add('hidden'));
    });

    closeButton.addEventListener('click', () => {
        chatWidget.classList.remove('expanded');
        expandButton.classList.remove('hidden');
        closeButton.classList.add('hidden');
        otherWidgets.forEach(widget => widget.classList.remove('hidden'));
    });
}
