/* app/static/js/auth.js */
/* Handles client-side authentication form enhancements, like password visibility toggle. */

document.addEventListener('DOMContentLoaded', function() {
    const logPrefix = "[AuthJS]";

    // --- Initial Field Focus ---
    const usernameField = document.getElementById('username');
    const passwordField = document.getElementById('password');

    const focusUsername = () => {
        if (!usernameField) return;
        try {
            usernameField.focus({ preventScroll: true });
        } catch (err) {
            usernameField.focus();
        }
        if (typeof usernameField.setSelectionRange === 'function') {
            const end = usernameField.value.length;
            usernameField.setSelectionRange(end, end);
        }
    };

    if (usernameField) {
        let userInteracted = false;
        const markInteraction = () => { userInteracted = true; };
        ['mousedown', 'keydown', 'touchstart'].forEach(evt => {
            document.addEventListener(evt, markInteraction, { once: true, capture: true });
        });

        focusUsername();
        window.logger.debug(logPrefix, "Username field focused on load.");

        if (passwordField) {
            passwordField.addEventListener('focus', () => {
                if (userInteracted) return;
                requestAnimationFrame(() => {
                    if (!userInteracted && document.activeElement === passwordField) {
                        focusUsername();
                        window.logger.debug(logPrefix, "Prevented auto-focus on password; restored username focus.");
                    }
                });
            });
        }
    } else {
        window.logger.debug(logPrefix, "Username field not found for initial focus.");
    }

    // --- Password Visibility Toggle ---
    function setupPasswordToggle(inputId, toggleIconId) {
        const passwordInput = document.getElementById(inputId);
        const toggleIcon = document.getElementById(toggleIconId);

        if (passwordInput && toggleIcon) {
            toggleIcon.addEventListener('click', function() {
                const currentType = passwordInput.getAttribute('type');
                const newType = currentType === 'password' ? 'text' : 'password';
                passwordInput.setAttribute('type', newType);
                this.textContent = newType === 'password' ? 'visibility' : 'visibility_off';
            });
            window.logger.debug(logPrefix, `Password toggle initialized for input #${inputId}`);
        } else {
            if (!passwordInput) window.logger.debug(logPrefix, `Password input element #${inputId} not found.`);
            if (!toggleIcon) window.logger.debug(logPrefix, `Password toggle icon #${toggleIconId} not found.`);
        }
    }

    setupPasswordToggle('password', 'togglePassword');
    setupPasswordToggle('confirm_password', 'toggleConfirmPassword');

}); // End DOMContentLoaded
