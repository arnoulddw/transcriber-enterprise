// app/static/js/history/state.js
// Shared logger, constants, and mutable state for the history UI domain.

(function initializeHistoryState(window) {
    const History = window.History || (window.History = {});

    const historyLogPrefix = "[HistoryJS]";
    const historyLogger = window.logger?.scoped
        ? window.logger.scoped("HistoryJS")
        : console;

    function scopedHistoryLogger(section) {
        return window.logger?.scoped
            ? window.logger.scoped(`HistoryJS:${section}`)
            : historyLogger;
    }

    const idsToPollForTitle = new Set();
    const titlePollAttempts = {};
    const deletedTranscriptionUndoData = new Map();

    const UNDO_NOTIFICATION_BASE_DURATION_MS = 6000;
    const UNDO_NOTIFICATION_TOUCH_EXTRA_MS = 4000;
    const UNDO_NOTIFICATION_DURATION_MS = (() => {
        try {
            if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) {
                return UNDO_NOTIFICATION_BASE_DURATION_MS + UNDO_NOTIFICATION_TOUCH_EXTRA_MS;
            }
        } catch (error) {
            historyLogger.debug("Unable to evaluate pointer media query for undo duration.", error);
        }
        return UNDO_NOTIFICATION_BASE_DURATION_MS;
    })();

    History.logger = { historyLogPrefix, historyLogger, scopedHistoryLogger };
    History.state = {
        idsToPollForTitle,
        titlePollAttempts,
        deletedTranscriptionUndoData,
        titlePollIntervalId: null
    };
    History.constants = {
        MAX_TITLE_POLL_ATTEMPTS: 20,
        TITLE_POLL_INTERVAL_MS: 3000,
        UNDO_NOTIFICATION_BASE_DURATION_MS,
        UNDO_NOTIFICATION_TOUCH_EXTRA_MS,
        UNDO_NOTIFICATION_DURATION_MS
    };
})(window);
