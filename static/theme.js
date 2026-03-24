document.addEventListener("DOMContentLoaded", function () {
    const savedTheme = localStorage.getItem("theme") || "dark";

    if (savedTheme === "light") {
        document.body.classList.add("light-mode");
    }

    const themeToggleBtn = document.getElementById("themeToggleBtn");

    if (themeToggleBtn) {
        updateThemeButton(themeToggleBtn);

        themeToggleBtn.addEventListener("click", function () {
            document.body.classList.toggle("light-mode");

            const currentTheme = document.body.classList.contains("light-mode") ? "light" : "dark";
            localStorage.setItem("theme", currentTheme);

            updateThemeButton(themeToggleBtn);
        });
    }

    speakFromPushQueryIfPresent();
});

function updateThemeButton(button) {
    const icon = button.querySelector(".theme-icon");
    const text = button.querySelector(".theme-text");

    if (document.body.classList.contains("light-mode")) {
        if (icon) icon.innerText = "\u{1F319}";
        if (text) text.innerText = "Dark Mode";
    } else {
        if (icon) icon.innerText = "\u2600";
        if (text) text.innerText = "Light Mode";
    }
}

function speakFromPushQueryIfPresent() {
    const params = new URLSearchParams(window.location.search);
    const speechText = params.get("push_speak");
    const fromPush = params.get("from_push");

    if (fromPush !== "1" || !speechText) return;
    if (!("speechSynthesis" in window)) return;

    const utterance = new SpeechSynthesisUtterance(speechText);
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.volume = 1;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
}
