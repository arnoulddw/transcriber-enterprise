// app/static/js/history/styles.js
// Color helpers and pill styling utilities.

(function initializeHistoryStyles(window) {
    const History = window.History;
    const { historyLogger, historyLogPrefix } = History.logger;

    function getTextColorForBackground(hexColor) {
        try {
            const hex = hexColor.replace('#', '');
            const r = parseInt(hex.substring(0, 2), 16);
            const g = parseInt(hex.substring(2, 4), 16);
            const b = parseInt(hex.substring(4, 6), 16);
            const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
            return luminance > 0.5 ? 'black' : 'white';
        } catch (error) {
            historyLogger.error(`Error calculating text color for ${hexColor}.`, error);
            return 'black';
        }
    }

    function applyPillStyles(selector, parentElement = document) {
        const pills = parentElement.querySelectorAll(selector);
        pills.forEach(pill => {
            const bgColor = pill.dataset.backgroundColor;
            if (bgColor && bgColor.startsWith('#') && (bgColor.length === 7 || bgColor.length === 4)) {
                const textColor = getTextColorForBackground(bgColor);
                pill.style.backgroundColor = bgColor;
                pill.style.color = textColor;
            } else {
                window.logger.warn(`${historyLogPrefix} Invalid or missing data-background-color found for pill, defaulting styles:`, bgColor, pill);
                pill.style.backgroundColor = '#ffffff';
                pill.style.color = 'black';
            }
        });
    }

    window.getTextColorForBackground = getTextColorForBackground;
    window.applyPillStyles = applyPillStyles;

    History.styles = { getTextColorForBackground, applyPillStyles };
})(window);
