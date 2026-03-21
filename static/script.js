const sendBtn = document.getElementById("sendBtn");
const userInput = document.getElementById("userInput");
const chatMessages = document.getElementById("chatMessages");
const voiceToggle = document.getElementById("voiceToggle");
const micBtn = document.getElementById("micBtn");
const medicineList = document.getElementById("medicineList");

let voiceEnabled = false;
let alreadyReminded = {};
let currentLatitude = null;
let currentLongitude = null;

let recognition = null;
let isListening = false;

function addMessage(text, sender) {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add("message");

    if (sender === "user") {
        messageDiv.classList.add("user-message");
    } else {
        messageDiv.classList.add("bot-message");
    }

    messageDiv.textContent = text;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function speakText(text) {
    if (!voiceEnabled) return;

    window.speechSynthesis.cancel();

    const speech = new SpeechSynthesisUtterance(text);
    speech.rate = 0.95;
    speech.pitch = 1;
    speech.volume = 1;

    window.speechSynthesis.speak(speech);
}

function requestLocationSilently() {
    if (!navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
        function (position) {
            currentLatitude = position.coords.latitude;
            currentLongitude = position.coords.longitude;
            console.log("Location captured:", currentLatitude, currentLongitude);
        },
        function (error) {
            console.log("Location permission denied or unavailable.");
        }
    );
}

async function sendMessage() {
    const message = userInput.value.trim();
    if (message === "") return;

    addMessage(message, "user");
    userInput.value = "";

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                lat: currentLatitude,
                lon: currentLongitude
            })
        });

        const data = await response.json();
        addMessage(data.reply, "bot");
        speakText(data.reply);

    } catch (error) {
        const errorText = "Sorry, something went wrong. Please try again.";
        addMessage(errorText, "bot");
        speakText(errorText);
    }
}

function sendQuickMessage(text) {
    userInput.value = text;
    sendMessage();
}

if (voiceToggle) {
    voiceToggle.addEventListener("change", function () {
        voiceEnabled = this.checked;

        if (!voiceEnabled) {
            window.speechSynthesis.cancel();
        }
    });
}

if (sendBtn) {
    sendBtn.addEventListener("click", sendMessage);
}

if (userInput) {
    userInput.addEventListener("keypress", function (event) {
        if (event.key === "Enter") {
            sendMessage();
        }
    });
}

if (micBtn) {
    

    micBtn.addEventListener("click", function () {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            alert("Speech recognition is not supported in this browser.");
            return;
        }

        if (isListening) return;

        recognition = new SpeechRecognition();
        recognition.lang = "en-US";
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        recognition.continuous = true;

        let finalTranscript = "";
        isListening = true;

        micBtn.disabled = true;
        micBtn.innerHTML = "&#127908;";

        recognition.start();

        recognition.onresult = function (event) {
            let interimTranscript = "";

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;

                if (event.results[i].isFinal) {
                    finalTranscript += transcript + " ";
                } else {
                    interimTranscript += transcript;
                }
            }

            userInput.value = (finalTranscript + interimTranscript).trim();
        };

        recognition.onerror = function () {
            alert("Voice recognition failed. Please try again.");
            isListening = false;
            micBtn.disabled = false;
            micBtn.innerHTML = "&#127908;";
        };

        recognition.onend = function () {
            isListening = false;
            micBtn.disabled = false;
            micBtn.innerHTML = "&#127908;";

            const spokenText = userInput.value.trim();
            if (spokenText !== "") {
                sendMessage();
            }
        };

        setTimeout(() => {
            if (recognition && isListening) {
                recognition.stop();
            }
        }, 8000);
    });
}

async function loadMedicines() {
    if (!medicineList) return;

    try {
        const response = await fetch("/get_medicines");
        const medicines = await response.json();

        medicineList.innerHTML = "";

        if (!medicines.length) {
            medicineList.innerHTML = `<p class="empty-text">No medicine reminders added yet.</p>`;
            return;
        }

        medicines.forEach(med => {
            const card = document.createElement("div");
            card.classList.add("medicine-card");
            card.innerHTML = `
                <h3>${med.name}</h3>
                <p><strong>Dosage:</strong> ${med.dosage}</p>
                <p><strong>Date:</strong> ${med.date}</p>
                <p><strong>Time:</strong> ${med.time}</p>
                <p><strong>Schedule:</strong> ${med.schedule}</p>
            `;
            medicineList.appendChild(card);
        });
    } catch (error) {
        console.log("Failed to load medicines.");
    }
}

function checkMedicineReminders() {
    const now = new Date();
    const today = now.toISOString().split("T")[0];
    const currentTime = now.toTimeString().slice(0, 5);

    fetch("/get_medicines")
        .then(response => response.json())
        .then(medicines => {
            medicines.forEach(med => {
                const reminderKey = med.id + "_" + today + "_" + currentTime;

                if (med.date === today && med.time === currentTime && !alreadyReminded[reminderKey]) {
                    const reminderText = `Reminder: It is time to take ${med.name}, dosage ${med.dosage}.`;
                    alert(reminderText);
                    addMessage(reminderText, "bot");
                    speakText(reminderText);
                    alreadyReminded[reminderKey] = true;
                }
            });
        })
        .catch(() => {
            console.log("Reminder check failed.");
        });
}

window.onload = function () {
    requestLocationSilently();
    loadMedicines();
    setInterval(checkMedicineReminders, 30000);
};