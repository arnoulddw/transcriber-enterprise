// app/static/js/localization.js
// This file provides localization utilities, focusing on date and time formatting.

/**
 * Gets the user's preferred locale from the browser.
 * Falls back to 'en-US' if the locale cannot be determined.
 * @returns {string} The determined locale.
 */
function getUserLocale() {
    return (navigator.languages && navigator.languages.length) ? navigator.languages[0] : (navigator.language || 'en-US');
}

/**
 * Formats an ISO 8601 datetime string into a locale-aware date string.
 * @param {string} isoString - The ISO 8601 datetime string.
 * @returns {string} A formatted date string (e.g., "8/18/2025" or "18/8/2025").
 */
function formatDate(isoString) {
    if (!isoString) return 'N/A';
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return isoString;
        const locale = getUserLocale();
        return new Intl.DateTimeFormat(locale).format(date);
    } catch (e) {
        console.error("Error formatting date:", e);
        return isoString; // Fallback to original string on error
    }
}

/**
 * Formats an ISO 8601 datetime string into a locale-aware date and time string.
 * @param {string} isoString - The ISO 8601 datetime string.
 * @returns {string} A formatted date and time string (e.g., "8/18/2025, 2:30 PM" or "18/8/2025, 14:30").
 */
function formatDateTime(isoString) {
    if (!isoString) return 'N/A';
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return isoString;
        const locale = getUserLocale();
        const options = {
            year: 'numeric',
            month: 'numeric',
            day: 'numeric',
            hour: 'numeric',
            minute: 'numeric'
        };
        return new Intl.DateTimeFormat(locale, options).format(date);
    } catch (e) {
        console.error("Error formatting datetime:", e);
        return isoString; // Fallback to original string on error
    }
}

// Expose functions to the global window object to be accessible from other scripts.
window.formatDate = formatDate;
window.formatDateTime = formatDateTime;