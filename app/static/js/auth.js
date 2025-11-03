/* app/static/js/auth.js */
/* Handles client-side authentication form enhancements, like password visibility toggle. */

document.addEventListener('DOMContentLoaded', function() {
    const logPrefix = "[AuthJS]";

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