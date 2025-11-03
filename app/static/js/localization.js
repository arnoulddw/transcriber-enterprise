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
        window.logger.error("Error formatting date:", e);
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
        window.logger.error("Error formatting datetime:", e);
        return isoString; // Fallback to original string on error
    }
}
/**
 * Formats a number into a locale-aware string.
 * @param {number|string} num - The number to format.
 * @param {object} [options] - Options for Intl.NumberFormat.
 * @returns {string} The formatted number string.
 */
function formatLocaleNumber(num, options = {}) {
    const number = parseFloat(num);
    if (isNaN(number)) {
        return ''; // Return empty string for invalid inputs
    }
    const locale = getUserLocale();
    return new Intl.NumberFormat(locale, options).format(number);
}

/**
 * Parses a locale-specific number string into a float.
 * It handles both comma and dot decimal separators.
 * @param {string} str - The string to parse.
 * @returns {number} The parsed number, or NaN if invalid.
 */
function parseLocaleNumber(str) {
    if (typeof str !== 'string' || str.trim() === '') {
        return NaN;
    }
    // Get the locale-specific decimal separator
    const locale = getUserLocale();
    const parts = new Intl.NumberFormat(locale).formatToParts(1234.5);
    const decimalSeparator = parts.find(part => part.type === 'decimal').value;
    const thousandSeparator = parts.find(part => part.type === 'group').value;

    // Remove thousand separators
    const sanitizedStr = str.replace(new RegExp(`\\${thousandSeparator}`, 'g'), '');
    
    // Replace locale decimal separator with a dot
    const normalizedStr = sanitizedStr.replace(decimalSeparator, '.');

    return parseFloat(normalizedStr);
}

// Expose functions to the global window object to be accessible from other scripts.
window.formatDate = formatDate;
window.formatDateTime = formatDateTime;
window.formatLocaleNumber = formatLocaleNumber;
window.parseLocaleNumber = parseLocaleNumber;