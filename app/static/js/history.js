// app/static/js/history.js
// Handles actions on the server-rendered transcription history list UI.
// Includes polling for generated titles.

const historyLogPrefix = "[HistoryJS]";
const historyLogger = window.logger.scoped("HistoryJS");

function scopedHistoryLogger(section) {
    return window.logger.scoped(`HistoryJS:${section}`);
}

// Title Polling State
let titlePollIntervalId = null;
const idsToPollForTitle = new Set();
const titlePollAttempts = {}; 
const MAX_TITLE_POLL_ATTEMPTS = 20; 
const TITLE_POLL_INTERVAL_MS = 3000; 


/**
 * Calculates whether black or white text provides better contrast against a given background color.
 * @param {string} hexColor - Background color in hex format (e.g., "#ffffff").
 * @returns {string} - Returns 'black' or 'white'.
 */
function getTextColorForBackground(hexColor) {
    try {
        const hex = hexColor.replace('#', '');
        const r = parseInt(hex.substring(0, 2), 16);
        const g = parseInt(hex.substring(2, 4), 16);
        const b = parseInt(hex.substring(4, 6), 16);
        const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
        return luminance > 0.5 ? 'black' : 'white';
    } catch (e) {
        historyLogger.error(`Error calculating text color for ${hexColor}.`, e);
        return 'black';
    }
}
window.getTextColorForBackground = getTextColorForBackground;


/**
 * Finds all elements matching the selector, reads the background color from a data attribute,
 * and applies both the background color and the calculated contrast text color.
 * @param {string} selector - CSS selector for the pill elements (e.g., '.prompt-label-pill').
 * @param {HTMLElement} [parentElement=document] - Optional parent element to search within.
 */
function applyPillStyles(selector, parentElement = document) { 
    const pills = parentElement.querySelectorAll(selector); 
    pills.forEach(pill => {
        const bgColor = pill.dataset.backgroundColor;
        if (bgColor && bgColor.startsWith('#') && (bgColor.length === 7 || bgColor.length === 4)) {
             const textColor = getTextColorForBackground(bgColor);
             pill.style.backgroundColor = bgColor;
             pill.style.color = textColor;
        } else {
             window.logger.warn(`[HistoryJS] Invalid or missing data-background-color found for pill, defaulting styles:`, bgColor, pill);
             pill.style.backgroundColor = '#ffffff';
             pill.style.color = 'black';
        }
    });
}
window.applyPillStyles = applyPillStyles;


/**
 * Checks if a string value represents meaningful content, ignoring common placeholders.
 * @param {string|null|undefined} value - The string value to check.
 * @returns {boolean} - True if the value has meaningful content, false otherwise.
 */
function hasMeaningfulContent(value) {
    if (typeof value !== 'string' || !value.trim()) { return false; }
    const lowerValue = value.trim().toLowerCase();
    const placeholders = ['n/a', 'null', 'undefined', '[empty result]', 'none', '-', 'no result', 'no error', 'no prompt'];
    if (placeholders.includes(lowerValue)) { return false; }
    return true;
}

/**
 * Adds a single transcription item to the history list UI.
 * Handles prepending, removing duplicates, and initializing UI elements.
 * NOTE: This function now ONLY renders the transcription panel. Workflow data is handled separately.
 * It also adds the transcription ID to the title polling list based on the shouldPollTitle flag.
 * @param {object} transcription - The transcription data object (transcription fields ONLY).
 * @param {boolean} canDownload - Whether the user can download transcripts.
 * @param {boolean} canRunWorkflow - Whether the user can run workflows.
 * @param {boolean} [prepend=false] - If true, adds the item to the top of the list.
 * @param {boolean} [shouldPollTitle=false] - If true, adds the item ID to the title polling list.
 * @param {boolean} [hadPendingWorkflow=false] - If true, indicates a workflow was pre-applied.
 */
function addTranscriptionToHistory(transcription, canDownload, canRunWorkflow, prepend = false, shouldPollTitle = false, hadPendingWorkflow = false) {
    const logPrefix = `[HistoryJS:addTranscriptionToHistory:${transcription.id.substring(0, 8)}]`;
window.logger.debug(logPrefix, "Attempting to add/update history item:", transcription, "Should Poll Title:", shouldPollTitle, "Had Pending WF:", hadPendingWorkflow);

    const historyList = document.getElementById('transcriptionHistory');
    if (!historyList) {
        window.logger.error(logPrefix, "History list element (#transcriptionHistory) not found.");
        return;
    }
    const placeholder = document.getElementById('history-placeholder');

    const existingItem = historyList.querySelector(`li[data-transcription-id="${transcription.id}"]`);
    if (existingItem) {
        window.logger.debug(logPrefix, "Removing existing history item before adding updated one.");
        existingItem.remove();
        idsToPollForTitle.delete(transcription.id); 
        delete titlePollAttempts[transcription.id]; 
    }

    const listItem = document.createElement('li');
    listItem.className = 'py-4'; 
    listItem.dataset.transcriptionId = transcription.id;
    listItem.dataset.fullText = transcription.transcription_text || '[Transcription text not available]';
    listItem.dataset.initialPollTitle = shouldPollTitle ? 'true' : 'false';


    if (hadPendingWorkflow && transcription.pending_workflow_prompt_text) {
        listItem.dataset.pendingWorkflowPrompt = transcription.pending_workflow_prompt_text;
        listItem.dataset.pendingWorkflowTitle = transcription.pending_workflow_prompt_title || "Custom Workflow";
        listItem.dataset.pendingWorkflowColor = transcription.pending_workflow_prompt_color || "#ffffff";
        if (transcription.pending_workflow_origin_prompt_id) {
            listItem.dataset.workflowOriginPromptId = transcription.pending_workflow_origin_prompt_id;
        }
        window.logger.debug(logPrefix, "Stored pending workflow details on dataset:", listItem.dataset);
    }


    const apiName = window.API_NAME_MAP_FRONTEND?.[transcription.api_used] || capitalizeFirstLetter(transcription.api_used || 'Unknown API');
    const detectedLanguage = typeof transcription.detected_language === 'string'
        ? transcription.detected_language.trim()
        : '';
    const normalizedLanguage = detectedLanguage.toLowerCase();
    const shouldShowLanguage = detectedLanguage
        && normalizedLanguage !== 'unknown'
        && normalizedLanguage !== 'und';
    const langName = shouldShowLanguage
        ? (window.SUPPORTED_LANGUAGE_MAP?.[detectedLanguage] || capitalizeFirstLetter(detectedLanguage))
        : null;
    const durationMinutes = transcription.audio_length_minutes;
    const formattedDuration = (durationMinutes !== null && durationMinutes !== undefined) ? `${Math.ceil(durationMinutes)} min` : 'N/A';
    const formattedCreatedAt = typeof window.formatDateTime === 'function' ? window.formatDateTime(transcription.created_at) : transcription.created_at;
    const metaSegments = [apiName];
    if (langName) {
        metaSegments.push(langName);
    }
    metaSegments.push(formattedDuration, formattedCreatedAt);
    const metaText = metaSegments.map(segment => window.escapeHtml(segment)).join(' | ');

    const downloadButtonHtml = canDownload ? `
        <button class="download-btn p-2 rounded-full text-gray-500 hover:text-primary hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-opacity-50 flex items-center" title="Download Transcript">
            <i class="material-icons text-base">download</i>
        </button>
    ` : '';
    
    const historyItemContentClasses = ['history-item-content', 'flex', 'flex-col'];
    
    const transcriptPanelClasses = ['transcript-panel', 'w-full', 'relative', 'p-4'];
    const workflowPanelClasses = ['workflow-panel', 'w-full', 'mt-4', 'p-4', 'border', 'border-gray-300', 'rounded-md', 'bg-gray-50', 'relative', 'pb-11'];
    
    if (!hadPendingWorkflow) { 
        workflowPanelClasses.push('hidden');
    } else {
        historyItemContentClasses.push('has-active-workflow'); 
    }

    let startWorkflowButtonHtml = '';
    if (canRunWorkflow && !hadPendingWorkflow) {
        startWorkflowButtonHtml = `
            <div class="start-workflow-action text-right mt-2.5">
                <button class="start-workflow-btn bg-primary-light hover:bg-primary text-white text-xs px-2.5 py-1 rounded-full inline-flex items-center focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-primary-light">
                    <i class="material-icons tiny -ml-0.5 mr-1">auto_awesome</i>${window.i18n.startWorkflow || 'Start Workflow'}
                </button>
            </div>
        `;
    }
    
    const initialTitleText = (transcription.generated_title && transcription.title_generation_status === 'success')
                             ? transcription.generated_title
                             : (transcription.filename || 'Unknown Filename');
    const showInitialTitleIcon = transcription.generated_title && transcription.title_generation_status === 'success';


    listItem.innerHTML = `
        <div class="${historyItemContentClasses.join(' ')}">
            <div class="${transcriptPanelClasses.join(' ')}">
                <div class="flex justify-between items-start gap-4">
                    <div class="flex-grow min-w-0">
                        <div class="title-wrapper">
                            <b id="title-${transcription.id}" class="text-gray-800 font-medium sm:truncate leading-tight">
                                ${window.escapeHtml(initialTitleText)}<i class="material-icons tiny text-primary align-middle ml-1 ${showInitialTitleIcon ? '' : 'hidden'}" id="title-icon-${transcription.id}">auto_awesome</i>
                            </b>
                        </div>
                        <p class="meta text-xs text-gray-500">
                            ${metaText}
                            ${transcription.status === 'error' ? '<span class="text-red-600"> (Failed)</span>' : ''}
                        </p>
                    </div>
                    <div class="secondary-content history-item-actions flex-shrink-0 flex space-x-0.5">
                        <button class="copy-btn p-2 rounded-full text-gray-500 hover:text-primary hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-opacity-50 flex items-center" title="Copy Transcript">
                            <i class="material-icons text-base">content_copy</i>
                        </button>
                        ${downloadButtonHtml}
                        <button class="delete-btn p-2 rounded-full text-gray-500 hover:text-red-600 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-50 flex items-center" title="Delete Transcript">
                            <i class="material-icons text-base">delete</i>
                        </button>
                    </div>
                </div>
                <p class="transcription-text text-sm text-gray-700 mt-2 mb-2"></p>
                ${startWorkflowButtonHtml}
            </div>
            <div class="${workflowPanelClasses.join(' ')}"
                 ${transcription.llm_operation_id ? `data-operation-id="${transcription.llm_operation_id}"` : ''}>
                ${hadPendingWorkflow ? `
                    <div class="flex flex-col items-center justify-center text-gray-500 min-h-[100px]">
                      <span class="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-primary mb-2"></span>
                      <span>Loading Workflow...</span>
                   </div>` : ''}
            </div>
        </div>
    `;

    const transcriptElement = listItem.querySelector('.transcription-text');
    if (transcriptElement) {
        const fullText = transcription.transcription_text || '';
        const words = fullText.split(/\s+/).filter(Boolean);
        const previewLength = 140; 
        if (words.length > previewLength) {
            const truncatedText = words.slice(0, previewLength).join(' ') + '...';
            transcriptElement.textContent = truncatedText;
            transcriptElement.dataset.readMoreState = 'truncated'; 
            let readMoreLink = document.createElement('a');
            readMoreLink.href = '#!';
            readMoreLink.className = 'read-more text-primary hover:text-primary-dark text-sm';
            readMoreLink.style.fontSize = '0.9em'; 
            readMoreLink.style.marginLeft = '0px'; 
            readMoreLink.textContent = window.i18n.readMore || ' Read More';
            transcriptElement.parentNode.insertBefore(readMoreLink, transcriptElement.nextSibling);
        } else {
            transcriptElement.textContent = fullText;
            transcriptElement.dataset.readMoreState = 'full'; 
        }
    }

    if (placeholder) {
        placeholder.style.display = 'none';
    }

    if (prepend) {
        historyList.prepend(listItem); 
        window.logger.debug(logPrefix, "Prepended new history item to the list.");
    } else {
        historyList.appendChild(listItem);
        window.logger.debug(logPrefix, "Appended new history item to the list.");
    }

    if (shouldPollTitle) {
        idsToPollForTitle.add(transcription.id);
        titlePollAttempts[transcription.id] = 0;
        window.logger.debug(logPrefix, `Added ${transcription.id} to title polling list.`);
        startTitlePolling();
    } else if (prepend && transcription.status === 'finished' && !showInitialTitleIcon) {
        window.logger.debug(logPrefix, `Newly finished job ${transcription.id}, not polling. Making one-time call to fetchTitleStatus.`);
        fetchTitleStatus(transcription.id);
    } else {
        window.logger.debug(logPrefix, `Skipping title polling for ${transcription.id} (shouldPollTitle=${shouldPollTitle}, prepend=${prepend}, status=${transcription.status}, showInitialIcon=${showInitialTitleIcon}).`);
    }


    if (hadPendingWorkflow) {
        window.logger.debug(logPrefix, `Pre-applied workflow detected for ${transcription.id}. Initiating workflow status polling.`);
        if (typeof window.Workflow !== 'undefined' && typeof window.Workflow.startWorkflowPollingForTranscription === 'function') {
            Workflow.startWorkflowPollingForTranscription(transcription.id);
        } else {
            window.logger.error(logPrefix, "Workflow.startWorkflowPollingForTranscription function is missing.");
            const workflowPanel = listItem.querySelector(".workflow-panel");
            if (workflowPanel) workflowPanel.innerHTML = '<p class="text-red-600 text-center">Error: Could not start workflow polling.</p>';
        }
    }
}
window.addTranscriptionToHistory = addTranscriptionToHistory;

function addReadMoreToWorkflowHTML(resultElement) {
    if (!resultElement) return;
    const originalMarkdown = resultElement.dataset.fullText;
    if (!originalMarkdown) return;
    const previewLengthChars = 500;
    if (originalMarkdown.length > previewLengthChars) {
        let breakPoint = originalMarkdown.lastIndexOf(' ', previewLengthChars);
        if (breakPoint === -1 || breakPoint < previewLengthChars / 2) breakPoint = previewLengthChars;
        const truncatedMarkdown = originalMarkdown.substring(0, breakPoint) + '...';
        let fullHtml = '', truncatedHtml = '';
        if (typeof marked !== "undefined") {
            try { marked.setOptions({ gfm: true, breaks: false }); fullHtml = marked.parse(originalMarkdown); truncatedHtml = marked.parse(truncatedMarkdown); }
            catch (e) { window.logger.error(historyLogPrefix, "Error parsing Markdown:", e); fullHtml = `<pre>${window.escapeHtml(originalMarkdown)}</pre>`; truncatedHtml = `<pre>${window.escapeHtml(truncatedMarkdown)}</pre>`; }
        } else { fullHtml = `<pre>${window.escapeHtml(originalMarkdown)}</pre>`; truncatedHtml = `<pre>${window.escapeHtml(truncatedMarkdown)}</pre>`; }
        resultElement.innerHTML = truncatedHtml;
        resultElement.dataset.readMoreState = 'truncated';
        let readMoreLink = resultElement.nextElementSibling;
        if (!readMoreLink || !readMoreLink.classList.contains('read-more-workflow')) {
            readMoreLink = document.createElement('a'); readMoreLink.href = '#!';
            readMoreLink.className = 'read-more-workflow text-primary hover:text-primary-dark text-sm block mt-1.5';
            readMoreLink.style.fontSize = '0.9em'; 
            readMoreLink.style.marginLeft = '0px';
            readMoreLink.style.display = 'block';
            readMoreLink.style.marginTop = '5px';
            resultElement.parentNode.insertBefore(readMoreLink, resultElement.nextSibling);
        }
        readMoreLink.textContent = window.i18n.readMore || ' Read More'; readMoreLink.dataset.fullHtml = fullHtml; readMoreLink.dataset.truncatedHtml = truncatedHtml;
    } else {
        let fullHtml = '';
         if (typeof marked !== 'undefined') {
            try { marked.setOptions({ gfm: true, breaks: false }); fullHtml = marked.parse(originalMarkdown); }
            catch (e) { window.logger.error(historyLogPrefix, "Error parsing short Markdown:", e); fullHtml = `<pre>${window.escapeHtml(originalMarkdown)}</pre>`; }
        } else { fullHtml = `<pre>${window.escapeHtml(originalMarkdown)}</pre>`; }
        resultElement.innerHTML = fullHtml; resultElement.dataset.readMoreState = 'full';
        let existingLink = resultElement.nextElementSibling;
        if (existingLink && existingLink.classList.contains('read-more-workflow')) existingLink.remove();
    }
}
window.addReadMoreToWorkflowHTML = addReadMoreToWorkflowHTML;

function togglePrompt(ellipsisElement) {
    const container = ellipsisElement.closest('.truncated-prompt'); if (!container) return;
    const truncatedPart = container.querySelector('em'); const ellipsis = container.querySelector('.ellipsis'); const fullPromptPart = container.querySelector('.full-prompt');
    if (fullPromptPart.style.display === 'none') { truncatedPart.style.display = 'none'; ellipsis.style.display = 'none'; fullPromptPart.style.display = 'inline'; }
    else { truncatedPart.style.display = 'inline'; ellipsis.style.display = 'inline'; fullPromptPart.style.display = 'none'; }
}
window.togglePrompt = togglePrompt;

function logDownload(transcriptionId) {
    const logPrefix = `[HistoryJS:logDownload:${transcriptionId}]`; window.logger.debug(logPrefix, "Logging download...");
    fetch(`/api/transcriptions/${transcriptionId}/log_download`, { method: 'POST', headers: { 'X-CSRFToken': window.csrfToken, 'Accept': 'application/json' } })
    .then(response => { if (!response.ok) { response.json().then(errData => { window.logger.error(logPrefix, `Failed to log download (${response.status}):`, errData.error || 'Unknown error'); }).catch(() => { window.logger.error(logPrefix, `Failed to log download (${response.status}) and couldn't parse error response.`); }); } else { window.logger.debug(logPrefix, "Download logged successfully."); } })
    .catch(error => { window.logger.error(logPrefix, "Network error logging download:", error); });
}
window.logDownload = logDownload; 

function downloadTranscription(transcriptionId, text, baseFilename) {
  if (!text) { 
    window.showNotification('Nothing to download!', 'warning', 3000, false);
    return; 
  }
  const filename = `${baseFilename || 'transcription'}.txt`; const element = document.createElement('a');
  const fileContent = text || ""; const blob = new Blob([fileContent], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob); element.setAttribute('href', url); element.setAttribute('download', filename);
  element.style.display = 'none'; document.body.appendChild(element); element.click(); document.body.removeChild(element); URL.revokeObjectURL(url);
  window.logger.debug(historyLogPrefix, `Download triggered for ${filename}`); window.logDownload(transcriptionId);
}
window.downloadTranscription = downloadTranscription; 


function handleClearAll() {
    if (confirm('Are you sure you want to clear your entire transcription history?\nThis action cannot be undone.')) {
        window.logger.info(historyLogPrefix, "Clear All confirmed. Sending request...");
        fetch('/api/transcriptions/clear', { method: 'DELETE', headers: { 'X-CSRFToken': window.csrfToken } })
        .then(response => { if (!response.ok) { return response.json().catch(() => ({ error: `HTTP error! Status: ${response.status}` })).then(errData => { throw new Error(errData.error || `HTTP error! Status: ${response.status}`); }); } return response.json(); })
        .then(data => {
            window.showNotification(data.message || 'History cleared successfully.', 'success', 4000, false);
            window.logger.info(historyLogPrefix, "History cleared successfully via API.");
            const historyList = document.getElementById('transcriptionHistory'); const clearAllBtn = document.getElementById('clearAllBtn');
            if (historyList) { historyList.innerHTML = '<li class="py-4 text-center text-gray-500" id="history-placeholder">No transcriptions found.</li>'; } 
            if (clearAllBtn) clearAllBtn.style.display = 'none';
            const paginationContainer = document.querySelector('.pagination-container'); if (paginationContainer) paginationContainer.remove();
        })
        .catch(error => { 
            window.logger.error(historyLogPrefix, 'Error clearing transcriptions:', error); 
            window.showNotification(`Error clearing history: ${window.escapeHtml(error.message)}`, 'error', 5000, false);
        });
    } else { window.logger.debug(historyLogPrefix, "Clear All cancelled by user."); }
}
window.handleClearAll = handleClearAll; 

function deleteTranscription(transcriptionId, transcriptionItemElement) {
    const logPrefix = `[HistoryJS:deleteTranscription:${transcriptionId}]`; window.logger.debug(logPrefix, "Delete requested.");
    fetch(`/api/transcriptions/${transcriptionId}`, { method: 'DELETE', headers: { 'X-CSRFToken': window.csrfToken } })
    .then(response => { if (!response.ok) { return response.json().catch(() => ({ error: `HTTP error! Status: ${response.status}` })).then(errData => { throw new Error(errData.error || `HTTP error! Status: ${response.status}`); }); } return response.json(); })
    .then(data => {
        window.showNotification(data.message || 'Transcription deleted.', 'success', 4000, false);
        window.logger.info(logPrefix, "Deletion successful via API.");
        window.location.reload(); 
    })
    .catch(error => { 
        window.logger.error(historyLogPrefix, 'Error deleting transcription:', error); 
        window.showNotification(`Error deleting: ${window.escapeHtml(error.message)}`, 'error', 5000, false);
    });
}
window.deleteTranscription = deleteTranscription; 

function capitalizeFirstLetter(string) { if (!string || typeof string !== 'string') return string || ''; return string.charAt(0).toUpperCase() + string.slice(1); }
window.capitalizeFirstLetter = capitalizeFirstLetter; 


/**
 * Fetches the title status for a single transcription ID.
 * @param {string} transcriptionId
 */
async function fetchTitleStatus(transcriptionId) {
    const pollLogPrefix = `[HistoryJS:TitlePoll:${transcriptionId.substring(0, 8)}]`;
    try {
        const response = await fetch(`/api/transcriptions/${transcriptionId}/title`, {
            method: 'GET',
            headers: { 'Accept': 'application/json', 'X-CSRFToken': window.csrfToken }
        });

        if (!response.ok) {
            window.logger.error(pollLogPrefix, `Error fetching title status (${response.status}). Removing from poll.`);
            idsToPollForTitle.delete(transcriptionId);
            delete titlePollAttempts[transcriptionId];
            return;
        }

        const data = await response.json();
        const titleElement = document.getElementById(`title-${transcriptionId}`);
        const iconElement = document.getElementById(`title-icon-${transcriptionId}`);

        if (!titleElement || !iconElement) {
            window.logger.warn(pollLogPrefix, `Title or icon element not found for ID. Removing from poll.`);
            idsToPollForTitle.delete(transcriptionId);
            delete titlePollAttempts[transcriptionId];
            return;
        }

        switch (data.status) {
            case 'generated':
                window.logger.info(pollLogPrefix, `Title generated: '${data.title}'`);
                titleElement.innerHTML = `${window.escapeHtml(data.title)}<i class="material-icons tiny text-primary align-middle ml-1" id="title-icon-${transcriptionId}">auto_awesome</i>`;
                titleElement.classList.add('title-updated'); 
                idsToPollForTitle.delete(transcriptionId);
                delete titlePollAttempts[transcriptionId];
                break;
            case 'failed':
            case 'unknown':
            case 'disabled': // Added 'disabled' case
                window.logger.warn(pollLogPrefix, `Title generation status is '${data.status}'. Using filename. Stopping poll.`);
                titleElement.innerHTML = `${window.escapeHtml(data.title)}<i class="material-icons tiny text-primary align-middle ml-1 hidden" id="title-icon-${transcriptionId}">auto_awesome</i>`;
                idsToPollForTitle.delete(transcriptionId);
                delete titlePollAttempts[transcriptionId];
                break;
            case 'processing':
            case 'pending':
                titlePollAttempts[transcriptionId] = (titlePollAttempts[transcriptionId] || 0) + 1;
                if (titlePollAttempts[transcriptionId] > MAX_TITLE_POLL_ATTEMPTS) {
                    window.logger.warn(pollLogPrefix, `Max poll attempts reached for title generation. Stopping poll.`);
                    iconElement.classList.add('hidden'); 
                    iconElement.style.display = 'none';
                    idsToPollForTitle.delete(transcriptionId);
                    delete titlePollAttempts[transcriptionId];
                } else {
                    window.logger.debug(pollLogPrefix, `Title status is '${data.status}'. Continuing poll (Attempt ${titlePollAttempts[transcriptionId]}).`);
                }
                break;
            default:
                window.logger.error(pollLogPrefix, `Unexpected title status received: ${data.status}. Stopping poll.`);
                iconElement.classList.add('hidden'); 
                iconElement.style.display = 'none';
                idsToPollForTitle.delete(transcriptionId);
                delete titlePollAttempts[transcriptionId];
        }

    } catch (error) {
        window.logger.error(pollLogPrefix, "Error during title status fetch:", error);
        const iconElement = document.getElementById(`title-icon-${transcriptionId}`);
        if(iconElement) { 
            iconElement.classList.add('hidden');
            iconElement.style.display = 'none';
        }
        idsToPollForTitle.delete(transcriptionId); 
        delete titlePollAttempts[transcriptionId];
    }
}

/**
 * Starts the interval timer for polling title statuses.
 */
function startTitlePolling() {
    if (titlePollIntervalId) {
        window.logger.debug(historyLogPrefix, "Title polling interval already running.");
        return;
    }
    if (idsToPollForTitle.size === 0) {
        window.logger.debug(historyLogPrefix, "No transcription IDs to poll for titles.");
        return;
    }

    window.logger.info(historyLogPrefix, "Starting title polling interval...");
    titlePollIntervalId = setInterval(() => {
        if (idsToPollForTitle.size === 0) {
            window.logger.info(historyLogPrefix, "No more IDs to poll for titles. Stopping interval.");
            clearInterval(titlePollIntervalId);
            titlePollIntervalId = null;
            return;
        }
        const idsToCheck = new Set(idsToPollForTitle); // Iterate over a copy
        window.logger.debug(historyLogPrefix, `Polling titles for ${idsToCheck.size} IDs...`);
        idsToCheck.forEach(id => fetchTitleStatus(id));
    }, TITLE_POLL_INTERVAL_MS);
}
window.startTitlePolling = startTitlePolling;


document.addEventListener('DOMContentLoaded', function() {
    const clearAllBtn = document.getElementById('clearAllBtn');
    if (clearAllBtn) { clearAllBtn.addEventListener('click', window.handleClearAll); window.logger.debug(historyLogPrefix, "Clear All button listener attached."); }
    else { window.logger.debug(historyLogPrefix, "Clear All button not found on page load."); }

    const historyList = document.getElementById('transcriptionHistory');
    if (historyList) {
        historyList.addEventListener('click', function(event) {
            const copyBtn = event.target.closest('.transcript-panel .copy-btn');
            const downloadBtn = event.target.closest('.transcript-panel .download-btn');
            const deleteBtn = event.target.closest('.transcript-panel .delete-btn');
            const transcriptionItem = event.target.closest('li[data-transcription-id]'); 

            if (!transcriptionItem) return;

            const transcriptionId = transcriptionItem.dataset.transcriptionId;
            const fullText = transcriptionItem.dataset.fullText;
            const filenameElement = transcriptionItem.querySelector('.transcript-panel b'); 
            const filename = filenameElement ? filenameElement.textContent.trim() : 'transcription';
            const baseFilename = filename.replace(/\.[^/.]+$/, "");

            if (copyBtn && transcriptionId && fullText) {
                window.copyToClipboard(fullText); 
                return; 
            }
            if (downloadBtn && transcriptionId && fullText) {
                window.downloadTranscription(transcriptionId, fullText, `${baseFilename}_transcription`); 
                return; 
            }
            if (deleteBtn && transcriptionId) {
                window.deleteTranscription(transcriptionId, transcriptionItem); 
                return; 
            }
        });
        window.logger.debug(historyLogPrefix, "Transcription action listeners attached via delegation.");

        historyList.addEventListener('click', function(event) {
            const readMoreWorkflow = event.target.closest('.read-more-workflow');
            if (readMoreWorkflow) {
                event.preventDefault();
                const resultElement = readMoreWorkflow.previousElementSibling;
                if (resultElement && resultElement.classList.contains('workflow-result-text')) {
                    const currentState = resultElement.dataset.readMoreState;
                    const fullHtml = readMoreWorkflow.dataset.fullHtml;
                    const truncatedHtml = readMoreWorkflow.dataset.truncatedHtml;

                    if (currentState === 'truncated') {
                        resultElement.innerHTML = fullHtml;
                        resultElement.dataset.readMoreState = 'full';
                        readMoreWorkflow.textContent = window.i18n.readLess || ' Read Less';
                    } else {
                        resultElement.innerHTML = truncatedHtml;
                        resultElement.dataset.readMoreState = 'truncated';
                        readMoreWorkflow.textContent = window.i18n.readMore || ' Read More';
                    }
                }
                return; 
            }

            const readMoreTranscript = event.target.closest('.read-more');
            if (readMoreTranscript) {
                event.preventDefault();
                const transcriptElement = readMoreTranscript.previousElementSibling;
                if (transcriptElement && transcriptElement.classList.contains('transcription-text')) {
                    const transcriptionItem = transcriptElement.closest('li[data-transcription-id]'); 
                    const fullText = transcriptionItem?.dataset.fullText;
                    if (fullText) {
                        const currentState = transcriptElement.dataset.readMoreState;
                        if (currentState === 'truncated') {
                            transcriptElement.textContent = fullText;
                            transcriptElement.dataset.readMoreState = 'full';
                            readMoreTranscript.textContent = window.i18n.readLess || ' Read Less';
                        } else {
                            const words = fullText.split(/\s+/).filter(Boolean);
                            const previewLength = 140; 
                            const truncatedText = words.slice(0, previewLength).join(' ') + (words.length > previewLength ? '...' : '');
                            transcriptElement.textContent = truncatedText;
                            transcriptElement.dataset.readMoreState = 'truncated';
                            readMoreTranscript.textContent = window.i18n.readMore || ' Read More';
                        }
                    }
                }
                return; 
            }
        });
        window.logger.debug(historyLogPrefix, "Read more listeners attached via delegation.");

        historyList.querySelectorAll('.transcription-text').forEach(el => {
            const transcriptionItem = el.closest('li[data-transcription-id]'); 
            const fullText = transcriptionItem?.dataset.fullText;
            if (fullText) {
                const words = fullText.split(/\s+/).filter(Boolean);
                const previewLength = 140;
                if (words.length > previewLength) {
                    const truncatedText = words.slice(0, previewLength).join(' ') + '...';
                    el.textContent = truncatedText;
                    el.dataset.readMoreState = 'truncated'; 
                    let readMoreLink = el.nextElementSibling;
                    if (!readMoreLink || !readMoreLink.classList.contains('read-more')) {
                        readMoreLink = document.createElement('a');
                        readMoreLink.href = '#!';
                        readMoreLink.className = 'read-more text-primary hover:text-primary-dark text-sm';
                        readMoreLink.style.fontSize = '0.9em'; 
                        readMoreLink.style.marginLeft = '0px';
                        el.parentNode.insertBefore(readMoreLink, el.nextSibling);
                    }
                    readMoreLink.textContent = window.i18n.readMore || ' Read More';
                } else {
                    el.textContent = fullText;
                    el.dataset.readMoreState = 'full'; 
                    let existingLink = el.nextElementSibling;
                    if (existingLink && existingLink.classList.contains('read-more')) existingLink.remove();
                }
            }
        });

        if (typeof window.applyPillStyles === 'function') {
            window.applyPillStyles('#transcriptionHistory .prompt-label-pill');
        } else {
            window.logger.error("applyPillStyles function not found in history.js");
        }

        historyList.querySelectorAll('li[data-transcription-id]').forEach(item => {
            if (item.dataset.initialPollTitle === 'true') { // Use the stored initial flag
                idsToPollForTitle.add(item.dataset.transcriptionId);
                titlePollAttempts[item.dataset.transcriptionId] = 0;
            }
        });
        window.logger.debug(historyLogPrefix, `Initial title polling list size: ${idsToPollForTitle.size}`);
        startTitlePolling(); 
    }
});
