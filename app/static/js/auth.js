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

    // --- reCAPTCHA v3 Integration ---
    const recaptchaForm = document.querySelector('form[data-recaptcha-site-key]');
    if (recaptchaForm) {
        const siteKey = recaptchaForm.dataset.recaptchaSiteKey;
        const actionName = recaptchaForm.dataset.recaptchaAction || 'login';
        const tokenInput = recaptchaForm.querySelector('input[name="recaptcha_token"]');
        const isEnterprise = recaptchaForm.dataset.recaptchaEnterprise === 'true';
        let isRequestInFlight = false;
        let lastTokenTimestamp = 0;

        const resolveRecaptchaClient = () => {
            if (!window.grecaptcha) return null;
            if (isEnterprise && window.grecaptcha.enterprise) {
                return window.grecaptcha.enterprise;
            }
            return window.grecaptcha;
        };

        const requestRecaptchaToken = () => new Promise((resolve, reject) => {
            const client = resolveRecaptchaClient();
            if (!client || typeof client.ready !== 'function' || typeof client.execute !== 'function') {
                reject(new Error('grecaptcha-not-ready'));
                return;
            }
            client.ready(() => {
                client.execute(siteKey, { action: actionName })
                    .then(resolve)
                    .catch(reject);
            });
        });

        recaptchaForm.addEventListener('submit', function(event) {
            if (!siteKey || !tokenInput) {
                window.logger.warn(logPrefix, 'reCAPTCHA configuration missing on login form.');
                return;
            }
            const tokenAgeMs = Date.now() - lastTokenTimestamp;
            if (tokenInput.value && tokenAgeMs < 90000) {
                window.logger.debug(logPrefix, 'Existing reCAPTCHA token reused for submission.');
                return;
            }

            event.preventDefault();

            if (isRequestInFlight) {
                window.logger.debug(logPrefix, 'reCAPTCHA token request already in progress.');
                return;
            }

            isRequestInFlight = true;
            const submitButton = recaptchaForm.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
            }

            requestRecaptchaToken()
                .then(token => {
                    tokenInput.value = token;
                    lastTokenTimestamp = Date.now();
                    isRequestInFlight = false;
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                    recaptchaForm.submit();
                })
                .catch(error => {
                    window.logger.error(logPrefix, 'Unable to obtain reCAPTCHA token:', error);
                    isRequestInFlight = false;
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                    tokenInput.value = '';
                    alert('reCAPTCHA could not verify your request. Please ensure the script is not being blocked and try again.');
                });
        });
    } else {
        window.logger.debug(logPrefix, 'No reCAPTCHA-enabled login form detected.');
    }

}); // End DOMContentLoaded
