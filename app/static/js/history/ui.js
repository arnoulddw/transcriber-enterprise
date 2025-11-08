// app/static/js/history/ui.js
// UI helpers for maintaining the history list structure.

(function initializeHistoryUi(window) {
    const History = window.History;
    const { historyLogger } = History.logger;

    function hasMeaningfulContent(value) {
        if (typeof value !== 'string' || !value.trim()) {
            return false;
        }
        const lowerValue = value.trim().toLowerCase();
        const placeholders = ['n/a', 'null', 'undefined', '[empty result]', 'none', '-', 'no result', 'no error', 'no prompt'];
        return !placeholders.includes(lowerValue);
    }

    function updateHistoryEmptyState() {
        const historyList = document.getElementById('transcriptionHistory');
        if (!historyList) {
            return;
        }

        const hasVisibleItems = Boolean(historyList.querySelector('li[data-transcription-id]'));
        let placeholder = document.getElementById('history-placeholder');
        const clearAllBtn = document.getElementById('clearAllBtn');

        if (!hasVisibleItems) {
            const emptyText = (window.i18n && (window.i18n.noTranscriptionsFound || window.i18n.noTranscriptions)) || 'No transcriptions found.';
            if (!placeholder) {
                placeholder = document.createElement('li');
                placeholder.id = 'history-placeholder';
                placeholder.className = 'py-4 text-center text-gray-500';
                placeholder.textContent = emptyText;
                historyList.appendChild(placeholder);
            } else {
                placeholder.style.display = '';
                placeholder.textContent = emptyText;
            }
            if (clearAllBtn) {
                clearAllBtn.style.display = 'none';
            }
        } else {
            if (placeholder) {
                placeholder.remove();
            }
            if (clearAllBtn) {
                clearAllBtn.style.display = '';
            }
        }
    }

    function animateHistoryItemRemoval(itemElement, onComplete) {
        if (!itemElement) {
            if (typeof onComplete === 'function') {
                onComplete();
            }
            return;
        }

        const computedStyle = window.getComputedStyle(itemElement);
        const marginTop = parseFloat(computedStyle.marginTop) || 0;
        const marginBottom = parseFloat(computedStyle.marginBottom) || 0;
        const totalHeight = itemElement.offsetHeight + marginTop + marginBottom;

        itemElement.style.boxSizing = 'border-box';
        itemElement.style.transition = 'opacity 250ms ease, transform 250ms ease, max-height 250ms ease, margin 250ms ease, padding 250ms ease';
        itemElement.style.maxHeight = `${totalHeight}px`;
        itemElement.style.overflow = 'hidden';

        requestAnimationFrame(() => {
            itemElement.style.opacity = '0';
            itemElement.style.transform = 'translateX(-12px)';
            itemElement.style.maxHeight = '0';
            itemElement.style.marginTop = '0';
            itemElement.style.marginBottom = '0';
            itemElement.style.paddingTop = '0';
            itemElement.style.paddingBottom = '0';
        });

        setTimeout(() => {
            if (typeof onComplete === 'function') {
                onComplete();
            }
        }, 280);
    }

    window.hasMeaningfulContent = hasMeaningfulContent;
    History.ui = { hasMeaningfulContent, updateHistoryEmptyState, animateHistoryItemRemoval };
})(window);
