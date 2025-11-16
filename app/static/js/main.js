let audioChunks = [];
let isRecording = false;
let mediaRecorder;
let mediaStream;
let firstAudio = true;
let audioPlayer = new Audio();
let socket = io.connect('https://' + document.domain + ':' + location.port);
let audioQueue = [];
let isAudioPlaying = false;
let audioOutput = false;
let submitAllowed = true;
let mode='respond_correct';
let lastReceivedResponse = "";
let lastInteractionTime = 0;

function prepareDataToBeSent(message) {

  console.log("In prepareDataToBeSent, lastInteractionTime:", lastInteractionTime);


  submitAllowed = false;


  var formData = new FormData();
  if (audioChunks.length > 0){
        var audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      formData.append('audio', audioBlob);
  }

  var socketId = socket.id;  // Get the Socket.IO session ID
  formData.append('socket_id', socketId);
  formData.append('text', message)

    var language = document.getElementById('language').value;
    var respondPrompt = document.getElementById('respond_prompt').value;
    var correctPrompt = document.getElementById('correct_prompt').value;

    formData.append('language', language);
    formData.append('respond_prompt', respondPrompt);
    formData.append('correct_prompt', correctPrompt);
    formData.append('audio_output', audioOutput.toString());

    let elapsedSeconds = 0;  // Declare elapsedSeconds here

    // Calculate the elapsed time in seconds
    if (lastInteractionTime != 0) {
        let currentTime = Date.now();
        console.log("Time diff", (currentTime - lastInteractionTime))
        elapsedSeconds = Math.floor((currentTime - lastInteractionTime) / 1000);  // Assign the calculated value
        lastInteractionTime = 0;
    }

    // Construct the data object with the query and elapsed time
    formData.append('elapsed_time', elapsedSeconds);


  fetch(route, {
    method: 'POST',
    body: formData
  })
  .then(response => {
    if (!response.ok) {
      throw new Error('Network response was not ok');
    }
    // Process any necessary response here, if needed
  })
  .catch(error => {
    console.error('Error sending data:', error);
  });
  // Reset the blobs after sending
  audioChunks = [];
}



function toggleAudioRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        isRecording = false;
        mediaRecorder.stop();
    } else {
        if (mediaStream) {
            // Extract only the audio track from the media stream
            const audioTracks = mediaStream.getAudioTracks();
            if (audioTracks.length > 0) {
                const audioStream = new MediaStream(audioTracks);
                mediaRecorder = new MediaRecorder(audioStream);

                mediaRecorder.ondataavailable = event => {
                    audioChunks.push(event.data);
                    if (!isRecording) {
                        prepareDataToBeSent();
                    }
                };
                mediaRecorder.start(1000);
                isRecording = true;
            }
        }
    }
}


function playNextAudio() {
    if (audioQueue.length > 0) {
        var audioUrl = audioQueue.shift();  // Get the next URL from the queue
        var audio = document.getElementById('chatBotAudio'); // Use the same audio element
        audio.src = audioUrl;  // Set new source
        audio.play();
        isAudioPlaying = true;

        audio.onended = function() {
            isAudioPlaying = false;
            playNextAudio();  // Play the next audio when this one ends
        };
    }
}



$(document).ready(function()
{
    socket.on('connect', function() {
        console.log("Connected");
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from the server');
    });

    socket.on('all_done', function() {
        submitAllowed = true;
        console.log("all done");
        lastInteractionTime = Date.now();
        console.log(lastInteractionTime)

            // Find the last bot bubble and mark it as done
            let chatBox = document.getElementById("chat-box");
            let lastBubble = chatBox.lastElementChild;

            if (lastBubble && lastBubble.classList.contains("bot-bubble")) {
                lastBubble.classList.add("done");
            }


        }
    });


    socket.on('audio_file', function(audioFileUrl) {
        console.log(audioFileUrl);
        audioQueue.push(audioFileUrl);  // Add new audio URL to the queue
        if (!isAudioPlaying) {
            playNextAudio();  // If no audio is playing, start playback
        }
    });
    socket.on('connect', function() {
        console.log("Connected");
    });

    socket.on('llm_response', function(data) {
        console.log('got back' + data.text);
        lastReceivedResponse += data.text;
        create_or_update_bot_bubble(data.text);
    });


    $("#record-btn-on").toggle();

    $('#audio-playback-btn-container').click(function(){
           $('#audio-playback-on-icon').toggle();
           $('#audio-playback-off-icon').toggle();
           audioOutput = !audioOutput;
    });

    $("#record-btn-container").click(function() {
        $("#record-btn-off").toggle();
        $("#record-btn-on").toggle();
        toggleAudioRecording();
    });


    function user_typed_a_message(e){
        if (e.keyCode == 13 && submitAllowed) {
            var inp_node = document.getElementById("message_input");
            var message = inp_node.value;
            create_user_bubble(message);
            inp_node.value = "";
            prepareDataToBeSent(message);
        }
}

window.addEventListener('load', function () {
  document.getElementById("message_input").onkeyup = user_typed_a_message
});



// Event listener for user input
function onUserInput() {
    if (window.chatbotTimeout) {
        console.log("Clearing the chatbotTimeout")
        clearTimeout(window.chatbotTimeout);
    }
}


document.getElementById("message_input").addEventListener('input', onUserInput);



});


function create_bot_bubble(text)
{
	d = document.createElement("div");
	p = document.createElement("p");
	p.innerHTML = text;
	d.appendChild(p);
	d.setAttribute("class", "bot-bubble");
	node = document.getElementById("chat-box");
	node.appendChild(d);
	  window.setTimeout(function () {
        node = document.getElementById("chat-box");
        node.scrollTop = node.scrollHeight;
      }, 200);

}
// For Streaming text
function create_or_update_bot_bubble(text) {
    let chatBox = document.getElementById("chat-box");
    let lastBubble = chatBox.lastElementChild;

    // Check if the last bubble is a bot bubble and not marked as done
    if (lastBubble && lastBubble.classList.contains("bot-bubble") && !lastBubble.classList.contains("done")) {
        // Append text to the existing bubble
        lastBubble.firstElementChild.innerHTML += text;
    } else {
        // Create new bubble
        let bubble = document.createElement("div");
        let p = document.createElement("p");
        p.innerHTML = text;
        bubble.appendChild(p);
        bubble.setAttribute("class", "bot-bubble");
        chatBox.appendChild(bubble);
    }

    // Scroll to the bottom of the chat box
    window.setTimeout(function () {
        chatBox.scrollTop = chatBox.scrollHeight;
    }, 200);
}


function create_user_bubble(message) {
  d = document.createElement("div");
  p = document.createElement("p");
  p.innerHTML = message;
  d.appendChild(p);
  d.setAttribute("class", "chat-box-body-send");
  node = document.getElementById("chat-box");
  node.appendChild(d);
  window.setTimeout(function () {
    node = document.getElementById("chat-box");
    node.scrollTop = node.scrollHeight;
  }, 200);
}


