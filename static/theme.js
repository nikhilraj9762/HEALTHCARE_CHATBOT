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
});

function updateThemeButton(button) {
    const icon = button.querySelector(".theme-icon");
    const text = button.querySelector(".theme-text");

    if (document.body.classList.contains("light-mode")) {
        if (icon) icon.innerText = "🌙";
        if (text) text.innerText = "Dark Mode";
    } else {
        if (icon) icon.innerText = "☀";
        if (text) text.innerText = "Light Mode";
    }
}