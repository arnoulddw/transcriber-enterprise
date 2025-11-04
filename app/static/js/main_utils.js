// app/static/js/main_utils.js
/* Shared utility functions for the main application UI. */

const mainUtilsLogPrefix = "[MainUtilsJS]";

const LOG_LEVELS = Object.freeze({
    debug: 10,
    info: 20,
    warn: 30,
    error: 40
});

function isDebugEnabled() {
    return Boolean(window.APP_DEBUG_MODE);
}

function isInfoEnabled() {
    return Boolean(window.APP_DEBUG_MODE);
}

function shouldLog(level) {
    if (level === 'warn' || level === 'error') return true;
    if (level === 'info') return isInfoEnabled();
    if (level === 'debug') return isDebugEnabled();
    return false;
}

function normalizeScope(scope) {
    if (!scope) return "App";
    if (scope.startsWith("[") && scope.endsWith("]")) {
        return scope.slice(1, -1);
    }
    return scope;
}

function emitLog(level, scope, message, metadata) {
    if (!shouldLog(level)) return;
    const consoleMethod = level === 'debug'
        ? console.debug
        : level === 'info'
            ? console.info
            : level === 'warn'
                ? console.warn
                : console.error;

    const parts = [`[${scope}]`];
    if (message !== undefined && message !== null) {
        parts.push(message);
    }
    if (metadata !== undefined) {
        parts.push(metadata);
    }
    consoleMethod(...parts);
}

function normalizeLegacyArgs(arg1, arg2, arg3) {
    if (typeof arg1 === 'string' && arg1.startsWith("[")) {
        return {
            scope: normalizeScope(arg1),
            message: arg2,
            metadata: arg3
        };
    }
    return {
        scope: "App",
        message: arg1,
        metadata: arg2
    };
}

window.logger = {
    debug(arg1, arg2, arg3) {
        const { scope, message, metadata } = normalizeLegacyArgs(arg1, arg2, arg3);
        emitLog('debug', scope, message, metadata);
    },
    info(arg1, arg2, arg3) {
        const { scope, message, metadata } = normalizeLegacyArgs(arg1, arg2, arg3);
        emitLog('info', scope, message, metadata);
    },
    warn(arg1, arg2, arg3) {
        const { scope, message, metadata } = normalizeLegacyArgs(arg1, arg2, arg3);
        emitLog('warn', scope, message, metadata);
    },
    error(arg1, arg2, arg3) {
        const { scope, message, metadata } = normalizeLegacyArgs(arg1, arg2, arg3);
        emitLog('error', scope, message, metadata);
    },
    scoped(scopeName) {
        const normalizedScope = normalizeScope(scopeName);
        return {
            debug: (message, metadata) => emitLog('debug', normalizedScope, message, metadata),
            info: (message, metadata) => emitLog('info', normalizedScope, message, metadata),
            warn: (message, metadata) => emitLog('warn', normalizedScope, message, metadata),
            error: (message, metadata) => emitLog('error', normalizedScope, message, metadata),
            isDebugEnabled: () => shouldLog('debug'),
            isInfoEnabled: () => shouldLog('info')
        };
    },
    isDebugEnabled,
    isInfoEnabled
};
const mainUtilsLogger = window.logger.scoped("MainUtilsJS");


/**
 * Simple HTML escaping.
 * @param {string} str The string to escape.
 * @returns {string} Escaped string.
 */
 function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#39;");
}
window.escapeHtml = escapeHtml;


/**
 * Displays a persistent notification message at the top of the page using Tailwind CSS.
 * @param {string} message - The message text (can include HTML).
 * @param {string} [type='info'] - Type of notification ('error', 'info', 'warning', 'success'). Determines styling.
 * @param {number} [duration=6000] - Duration in ms before auto-dismissal. 0 for no auto-dismiss.
 * @param {boolean} [persistent=true] - If true, message doesn't dismiss on click (unless a close button is added).
 * @param {string} [id=null] - Optional unique ID for the notification element.
 * @returns {HTMLElement|null} The created notification element or null.
 */
function showNotification(message, type = 'info', duration = 6000, persistent = true, id = null) {
    const container = document.getElementById('notification-container');
    if (!container) {
        mainUtilsLogger.error("Notification container not found!");
        return null;
    }

    // If an ID is provided, remove any existing notification with the same ID
    if (id) {
        const existing = document.getElementById(id);
        if (existing) {
            existing.remove();
        }
    }

    const notificationDiv = document.createElement('div');
    if (id) {
        notificationDiv.id = id;
    }

    // Base Tailwind classes for all notifications
    notificationDiv.className = 'w-full max-w-full px-4 py-3 rounded-lg shadow-lg flex items-start sm:items-center gap-3 text-sm transition-all duration-300 ease-in-out transform opacity-0 translate-y-2 pointer-events-auto';

    // Type-specific Tailwind classes and icons
    let bgColorClass, textColorClass, iconName, iconColorClass;
    switch (type) {
        case 'error':
            bgColorClass = 'bg-alert-error'; // from tailwind.config.js
            textColorClass = 'text-white';
            iconName = 'error_outline';
            iconColorClass = 'text-white';
            break;
        case 'warning':
            bgColorClass = 'bg-alert-warning'; // from tailwind.config.js
            textColorClass = 'text-gray-800'; // Dark text for better contrast on orange
            iconName = 'warning_amber';
            iconColorClass = 'text-gray-800';
            break;
        case 'success':
            bgColorClass = 'bg-alert-success'; // from tailwind.config.js
            textColorClass = 'text-white';
            iconName = 'check_circle_outline';
            iconColorClass = 'text-white';
            break;
        case 'info':
        default:
            bgColorClass = 'bg-alert-info'; // from tailwind.config.js
            textColorClass = 'text-white';
            iconName = 'info_outline';
            iconColorClass = 'text-white';
            break;
    }

    notificationDiv.classList.add(bgColorClass, textColorClass);

    // Icon element
    const iconElement = document.createElement('i');
    iconElement.className = `material-icons mr-3 ${iconColorClass}`;
    iconElement.textContent = iconName;

    // Message content element
    const messageElement = document.createElement('span');
    messageElement.className = 'flex-grow leading-snug';
    messageElement.innerHTML = message; // Allow HTML in message

    notificationDiv.appendChild(iconElement);
    notificationDiv.appendChild(messageElement);

    // Close button (always add for persistent, or if not auto-dismissing for a long time)
    if (persistent || duration === 0 || duration > 10000) {
        const closeButton = document.createElement('button');
        closeButton.type = 'button';
        closeButton.className = `ml-auto -mr-1 flex-shrink-0 p-1 rounded-md hover:bg-black hover:bg-opacity-10 focus:outline-none focus:ring-2 focus:ring-white ${textColorClass}`;
        closeButton.setAttribute('aria-label', 'Close notification');
        closeButton.innerHTML = '<i class="material-icons text-base">close</i>';
        closeButton.addEventListener('click', () => dismissNotification(notificationDiv));
        notificationDiv.appendChild(closeButton);
    }

    container.appendChild(notificationDiv);

    // Enter animation
    requestAnimationFrame(() => {
        notificationDiv.classList.remove('opacity-0', 'translate-y-2');
        notificationDiv.classList.add('opacity-100', 'translate-y-0');
    });

    // Auto-dismissal
    if (duration > 0) {
        setTimeout(() => dismissNotification(notificationDiv), duration);
    }

    return notificationDiv;
}
window.showNotification = showNotification; // Expose globally

function dismissNotification(notificationDiv) {
    if (!notificationDiv || !notificationDiv.parentNode) return;

    // Leave animation
    notificationDiv.classList.remove('opacity-100', 'translate-y-0');
    notificationDiv.classList.add('opacity-0', 'translate-y-2');

    setTimeout(() => {
        if (notificationDiv.parentNode) {
            notificationDiv.remove();
        }
    }, 300); // Match transition duration
}


/**
 * Helper function to Open API Key Modal.
 * (Used when an error message includes a link to manage keys)
 */
function openApiKeyModal(event) {
    if (event) event.preventDefault(); // Prevent default link behavior
    // The new Tailwind/JS modal opening logic is in user_settings.js
    if (typeof window.openApiKeyModalDialog === 'function') {
        window.openApiKeyModalDialog();
    } else {
        mainUtilsLogger.error("openApiKeyModalDialog function not found in user_settings.js. API Key management might be unavailable.");
        // Removed Materialize fallback code
        // alert('API Key management is not available or modal function missing.'); // This alert was commented out
    }
}
window.openApiKeyModal = openApiKeyModal; // Expose globally



/**
 * Simple minutes formatter for displaying usage limits.
 * @param {number} totalMinutes
 * @returns {string} Formatted string like "90 min". Returns "Unlimited" if 0 or less.
 */
function formatMinutesSimple(totalMinutes) {
    if (isNaN(totalMinutes) || totalMinutes <= 0) return "Unlimited";
    // Round up to the nearest whole minute for display consistency with history
    const roundedMinutes = Math.ceil(totalMinutes);
    return `${roundedMinutes} min`;
}
window.formatMinutesSimple = formatMinutesSimple; // Expose globally


/**
 * Finds all <time> elements with a datetime attribute on the page
 * and updates their content to a localized, formatted string.
 * This now relies on the functions in localization.js
 */
function initializeLocalizedDates() {
    const timeElements = document.querySelectorAll('time[datetime]');
    timeElements.forEach(timeEl => {
        const isoString = timeEl.getAttribute('datetime');
        if (isoString) {
            // Use the new global formatter from localization.js
            if (typeof window.formatDateTime === 'function') {
                timeEl.textContent = window.formatDateTime(isoString);
            } else {
                mainUtilsLogger.warn("window.formatDateTime function not found. Dates will not be localized.");
            }
        }
    });
}

// Run the date localization on page load.
document.addEventListener('DOMContentLoaded', initializeLocalizedDates);


// --- Copy to Clipboard Functionality with Toast Cooldown ---
let lastCopyToastTime = 0;
const TOAST_COOLDOWN_MS = 1000; // 1 second cooldown for copy toasts

function fallbackCopyToClipboard(text) {
  const log = window.logger.scoped("MainUtilsJS:fallbackCopy");
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed"; // Prevent scrolling to bottom
  textArea.style.top = "-9999px";
  textArea.style.left = "-9999px";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    const successful = document.execCommand('copy');
    const now = Date.now();
    if (successful) {
      if (now - lastCopyToastTime > TOAST_COOLDOWN_MS) {
        showNotification('Copied (fallback)!', 'info', 2000, false);
        lastCopyToastTime = now;
      } else {
        log.debug("Fallback copy toast suppressed due to cooldown.");
      }
      log.debug("Text copied using fallback method.");
    } else {
      showNotification('Copy failed (fallback)!', 'error', 3000, false);
      log.error('Fallback copy command failed.');
    }
  } catch (err) {
    showNotification('Copy failed (fallback)!', 'error', 3000, false);
    log.error('Error during fallback copy:', err);
  }
  document.body.removeChild(textArea);
}
window.fallbackCopyToClipboard = fallbackCopyToClipboard; // Expose globally

function copyToClipboard(text) {
  const log = window.logger.scoped("MainUtilsJS:copyToClipboard");
  if (!text) {
    showNotification('Nothing to copy!', 'warning', 2000, false);
    return;
  }

  const now = Date.now();

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text)
      .then(() => {
        if (now - lastCopyToastTime > TOAST_COOLDOWN_MS) {
          showNotification('Copied to clipboard!', 'success', 2000, false);
          lastCopyToastTime = now;
        } else {
          log.debug("Clipboard API copy toast suppressed due to cooldown.");
        }
        log.debug("Text copied using Clipboard API.");
      })
      .catch(err => {
        showNotification('Copy failed!', 'error', 3000, false);
        log.error('Async copy failed:', err);
        window.fallbackCopyToClipboard(text); // Ensure fallback is called
      });
  } else {
    log.warn("Using fallback copy method (navigator.clipboard not available or insecure context).");
    window.fallbackCopyToClipboard(text); // Ensure fallback is called
  }
}
window.copyToClipboard = copyToClipboard; // Expose globally


mainUtilsLogger.info("Utilities ready.");
