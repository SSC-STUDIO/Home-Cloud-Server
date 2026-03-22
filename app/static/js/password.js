document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('.btn[id^="togglePassword"]').forEach((button) => {
        button.addEventListener("click", () => {
            const explicitTarget = button.getAttribute("data-target");
            const passwordInput =
                (explicitTarget && document.getElementById(explicitTarget)) ||
                button.closest(".input-group")?.querySelector("input");

            if (!passwordInput) {
                return;
            }

            const nextType = passwordInput.getAttribute("type") === "password" ? "text" : "password";
            passwordInput.setAttribute("type", nextType);

            const eyeIcon = button.querySelector("i");
            if (eyeIcon) {
                eyeIcon.classList.toggle("fa-eye");
                eyeIcon.classList.toggle("fa-eye-slash");
            }
        });
    });

    document.querySelectorAll("form").forEach((form) => {
        const passwordInput = form.querySelector('input[name="password"], input[name="new_password"]');
        const confirmInput = form.querySelector('input[name="confirm_password"]');
        const feedback = form.querySelector("#password-feedback") || confirmInput?.closest(".mb-3, .col-md-6, .col-12")?.querySelector(".invalid-feedback");

        if (!passwordInput || !confirmInput) {
            return;
        }

        const validate = () => {
            const matches = passwordInput.value === confirmInput.value;
            confirmInput.setCustomValidity(matches ? "" : "Passwords do not match");
            confirmInput.classList.toggle("is-invalid", !matches);

            if (feedback) {
                feedback.style.display = matches ? "none" : "block";
            }

            return matches;
        };

        passwordInput.addEventListener("input", validate);
        confirmInput.addEventListener("input", validate);
        form.addEventListener("submit", (event) => {
            if (passwordInput.value && !validate()) {
                event.preventDefault();
            }
        });
    });
});
