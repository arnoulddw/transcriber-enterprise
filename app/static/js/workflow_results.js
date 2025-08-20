// app/static/js/workflow_results.js
// Handles interactions with completed workflow results.

const workflowResultsLogPrefix = "[WorkflowJS:Results]";

window.Workflow = window.Workflow || {};

// Utility function (qs) might be needed if not globally available from workflow_modal.js
// For now, assume qs is globally available or defined in workflow_modal.js
// If not, it should be defined here or passed around.
function qs(id) { return document.getElementById(id); }


function _handleEditWorkflowResult(operationId, workflowPanel) {
  console.log(workflowResultsLogPrefix, `Edit workflow result requested for operation ID: ${operationId}`);
  const resultTextElement = workflowPanel.querySelector(".workflow-result-text"),
    actionsDiv = workflowPanel.querySelector(".workflow-actions"),
    readMoreLink = workflowPanel.querySelector(".read-more-workflow");
  if (!resultTextElement || !actionsDiv) return;
  if (!operationId) {
    console.error(workflowResultsLogPrefix, "Cannot edit workflow: Operation ID is missing.");
    window.Workflow.showToast("Error: Cannot identify workflow to edit.", "error");
    return;
  }
  const currentText = resultTextElement.dataset.fullText || resultTextElement.textContent;
  resultTextElement.style.display = "none";
  if (readMoreLink) readMoreLink.style.display = "none";

  const textArea = document.createElement("textarea");
  textArea.className = "form-textarea block w-full rounded-md border-gray-300 shadow-sm focus:border-primary focus:ring-primary sm:text-sm workflow-edit-area min-h-[150px] text-sm";
  textArea.value = currentText;
  resultTextElement.parentNode.insertBefore(textArea, resultTextElement);
  textArea.style.height = 'auto'; textArea.style.height = (textArea.scrollHeight) + 'px';
  textArea.focus();

  actionsDiv.innerHTML = `
        <button class="save-edit-workflow-btn p-1.5 rounded-full text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500" title="Save Changes">
          <i class="material-icons text-base">save</i>
        </button>
        <button class="cancel-edit-workflow-btn p-1.5 rounded-full text-gray-500 bg-gray-200 hover:bg-gray-300 focus:outline-none focus:ring-2 focus:ring-gray-400" title="Cancel Edit">
          <i class="material-icons text-base">cancel</i>
        </button>
      `;
}
window.Workflow.handleEditWorkflowResult = _handleEditWorkflowResult;

function _handleCopyWorkflowResult(workflowPanel) {
  const resultTextElement = workflowPanel.querySelector(".workflow-result-text");
  const textToCopy = resultTextElement
    ? resultTextElement.dataset.fullText || resultTextElement.textContent
    : "";
  if (textToCopy) {
    if (typeof window.copyToClipboard === "function") {
      window.copyToClipboard(textToCopy);
    } else {
      console.error(workflowResultsLogPrefix, "copyToClipboard function not found.");
      window.Workflow.showToast("Error: Copy function unavailable.", "error");
    }
  } else {
    window.Workflow.showToast("Nothing to copy.", "warning");
  }
}
window.Workflow.handleCopyWorkflowResult = _handleCopyWorkflowResult;

function _handleDownloadWorkflowResult(transcriptionId, workflowPanel) {
  const resultTextElement = workflowPanel.querySelector(".workflow-result-text");
  const textToDownload = resultTextElement
    ? resultTextElement.dataset.fullText || resultTextElement.textContent
    : "";
  const transcriptionItem = workflowPanel.closest("li[data-transcription-id]");
  const originalFilenameElem = transcriptionItem?.querySelector(".transcript-panel b");
  const originalFilename = originalFilenameElem?.textContent || "workflow_result";
  const baseFilename = originalFilename.replace(/\.[^/.]+$/, "");
  if (textToDownload) {
    if (typeof window.downloadTranscription === "function") {
      window.downloadTranscription(transcriptionId, textToDownload, `${baseFilename}_workflow`);
    } else {
      console.error(workflowResultsLogPrefix, "downloadTranscription function not found.");
      window.Workflow.showToast("Error: Download function unavailable.", "error");
    }
  } else {
    window.Workflow.showToast("Nothing to download.", "warning");
  }
}
window.Workflow.handleDownloadWorkflowResult = _handleDownloadWorkflowResult;

async function _handleDeleteWorkflowResult(transcriptionId, transcriptionItem) {
  const delLog = `[WorkflowJS:Results:handleDelete:${transcriptionId}]`;
  if (!confirm("Are you sure you want to delete this workflow result?")) return;
  console.log(delLog, "Deleting workflow result...");
  const workflowPanel = transcriptionItem.querySelector(".workflow-panel");
  const deleteButton = workflowPanel?.querySelector(".delete-workflow-btn");
  if (deleteButton) deleteButton.disabled = true;
  try {
    const response = await fetch(`/api/transcriptions/${transcriptionId}/workflow`, {
      method: "DELETE",
      headers: { Accept: "application/json", "X-CSRFToken": window.csrfToken }
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP error ${response.status}`);
    window.Workflow.showToast(data.message || "Workflow result deleted.", "success");
    console.log(delLog, "Workflow result deleted successfully via API.");
    if (workflowPanel) {
      workflowPanel.innerHTML = "";
      workflowPanel.style.display = "none";
      workflowPanel.className = "workflow-panel hidden";
      delete workflowPanel.dataset.operationId;
    }
    const startButtonActionDiv = transcriptionItem.querySelector(".start-workflow-action");
    if (startButtonActionDiv) startButtonActionDiv.style.display = "block";
    const contentContainer = transcriptionItem.querySelector(".history-item-content");
    if (contentContainer) contentContainer.classList.remove("has-active-workflow");
  } catch (error) {
    console.error(delLog, "Error deleting workflow result:", error);
    const escapedError = typeof window.escapeHtml === 'function' ? window.escapeHtml(error.message) : error.message;
    window.Workflow.showToast(`Error: ${escapedError}`, "error");
    if (deleteButton) deleteButton.disabled = false;
  }
}
window.Workflow.handleDeleteWorkflowResult = _handleDeleteWorkflowResult;

async function _handleSaveWorkflowEdit(operationId, workflowPanel) {
  const saveLog = `[WorkflowJS:Results:handleSaveEdit:Op:${operationId}]`;
  const textArea = workflowPanel.querySelector(".workflow-edit-area");
  const saveButton = workflowPanel.querySelector(".save-edit-workflow-btn");
  if (!textArea || !saveButton || !operationId) {
    console.error(saveLog, "Missing required elements for save.");
    window.Workflow.showToast("Error saving edit.", "error");
    return;
  }
  const newResult = textArea.value;
  saveButton.disabled = true;
  saveButton.innerHTML =
    '<span class="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></span>';
  try {
    const response = await fetch(`/api/workflows/operations/${operationId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": window.csrfToken
      },
      body: JSON.stringify({ result: newResult })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP error ${response.status}`);
    window.Workflow.showToast(data.message || "Workflow result updated.", "success");
    console.log(saveLog, "Workflow edit saved successfully.");
    _handleCancelWorkflowEdit(workflowPanel, newResult); // Call local version
  } catch (error) {
    console.error(saveLog, "Error saving workflow edit:", error);
    const escapedError = typeof window.escapeHtml === 'function' ? window.escapeHtml(error.message) : error.message;
    window.Workflow.showToast(`Error: ${escapedError}`, "error");
    saveButton.disabled = false;
    saveButton.innerHTML = '<i class="material-icons text-base">save</i>';
  }
}
window.Workflow.handleSaveWorkflowEdit = _handleSaveWorkflowEdit;

function _handleCancelWorkflowEdit(workflowPanel, updatedText = null) {
  const resultTextElement = workflowPanel.querySelector(".workflow-result-text"),
    textArea = workflowPanel.querySelector(".workflow-edit-area"),
    actionsDiv = workflowPanel.querySelector(".workflow-actions"),
    readMoreLink = workflowPanel.querySelector(".read-more-workflow");
  if (textArea) textArea.remove();
  if (resultTextElement) {
    let textToDisplay = updatedText === null ? resultTextElement.dataset.fullText || "" : updatedText;
    if (updatedText !== null) resultTextElement.dataset.fullText = textToDisplay;

    let resultHtml = "";
    if (typeof marked !== "undefined") {
      try {
        marked.setOptions({ gfm: true, breaks: false });
        resultHtml = marked.parse(textToDisplay);
      } catch (e) {
        console.error(workflowResultsLogPrefix, "Error parsing Markdown:", e);
        resultHtml = `<pre class="whitespace-pre-wrap break-words">${window.escapeHtml(textToDisplay)}</pre>`;
      }
    } else {
      resultHtml = `<pre class="whitespace-pre-wrap break-words">${window.escapeHtml(textToDisplay)}</pre>`;
    }
    resultTextElement.innerHTML = resultHtml;
    resultTextElement.style.display = "block";
    if (readMoreLink) readMoreLink.style.display = "block";
    if (typeof window.addReadMoreToWorkflowHTML === "function") {
      window.addReadMoreToWorkflowHTML(resultTextElement);
    }
  }
  const canDownload = window.USER_PERMISSIONS?.allow_download_transcript ?? true;
  const downloadButtonHtml = canDownload
    ? `<button class="download-workflow-btn p-1.5 rounded-full text-gray-500 hover:text-primary hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary" title="Download Result"><i class="material-icons text-base">download</i></button>`
    : "";
  actionsDiv.innerHTML = `
        <button class="edit-workflow-btn p-1.5 rounded-full text-gray-500 hover:text-primary hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary" title="Edit Result"><i class="material-icons text-base">edit</i></button>
        <button class="copy-workflow-btn p-1.5 rounded-full text-gray-500 hover:text-primary hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary" title="Copy Result"><i class="material-icons text-base">content_copy</i></button>
        ${downloadButtonHtml}
        <button class="delete-workflow-btn p-1.5 rounded-full text-gray-500 hover:text-red-600 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-500" title="Delete Result"><i class="material-icons text-base">delete</i></button>
      `;
}
window.Workflow.handleCancelWorkflowEdit = _handleCancelWorkflowEdit;

function _manageWorkflowReadMoreLink(resultElement) {
  if (!resultElement) return;
  const originalMarkdown = resultElement.dataset.fullText;
  if (!originalMarkdown) return;
  const previewLengthChars = 500;
  let readMoreLink = resultElement.nextElementSibling;
  if (originalMarkdown.length > previewLengthChars) {
    if (!readMoreLink || !readMoreLink.classList.contains("read-more-workflow")) {
      readMoreLink = document.createElement("a");
      readMoreLink.href = "#!";
      readMoreLink.className = "read-more-workflow text-primary hover:text-primary-dark text-sm block mt-1.5";
      readMoreLink.style.fontSize = '0.9em';
      readMoreLink.style.marginLeft = '0px';
      readMoreLink.style.display = 'block';
      readMoreLink.style.marginTop = '5px';
      resultElement.parentNode.insertBefore(readMoreLink, resultElement.nextSibling);
    }
    const currentState = resultElement.dataset.readMoreState || "full";
    readMoreLink.textContent = currentState === "truncated" ? " Read More" : " Read Less";
    readMoreLink.style.display = "block";
  } else {
    if (readMoreLink && readMoreLink.classList.contains("read-more-workflow")) {
      readMoreLink.remove();
    }
    resultElement.dataset.readMoreState = "full";
  }
}
window.Workflow.manageWorkflowReadMoreLink = _manageWorkflowReadMoreLink;


document.addEventListener("DOMContentLoaded", function () {
    const logPrefix = "[WorkflowJS:Results:DOMContentLoaded]";
    const historyList = qs("transcriptionHistory");

    if (historyList) {
        historyList.addEventListener("click", function (event) {
            // Check if the click is on a start button, if so, modal.js handles it.
            if (event.target.closest(".start-workflow-btn")) {
                return;
            }

            // Handle workflow result actions
            const targetButton = event.target.closest("button");
            if (!targetButton) return;

            const workflowPanel = targetButton.closest(".workflow-panel");
            if (!workflowPanel) return; // Action is not within a workflow panel

            const transcriptionItem = workflowPanel.closest("li[data-transcription-id]");
            const transcriptionId = transcriptionItem?.dataset.transcriptionId;
            const operationId = workflowPanel.dataset.operationId;

            if (!transcriptionId) { // Should always have transcriptionId if workflowPanel exists
                console.warn(logPrefix, "Could not find transcription ID for workflow action.");
                return;
            }

            if (targetButton.classList.contains("edit-workflow-btn")) {
                window.Workflow.handleEditWorkflowResult(operationId, workflowPanel);
            } else if (targetButton.classList.contains("copy-workflow-btn")) {
                window.Workflow.handleCopyWorkflowResult(workflowPanel);
            } else if (targetButton.classList.contains("download-workflow-btn")) {
                window.Workflow.handleDownloadWorkflowResult(transcriptionId, workflowPanel);
            } else if (targetButton.classList.contains("delete-workflow-btn")) {
                window.Workflow.handleDeleteWorkflowResult(transcriptionId, transcriptionItem);
            } else if (targetButton.classList.contains("save-edit-workflow-btn")) {
                window.Workflow.handleSaveWorkflowEdit(operationId, workflowPanel);
            } else if (targetButton.classList.contains("cancel-edit-workflow-btn")) {
                window.Workflow.handleCancelWorkflowEdit(workflowPanel);
            }
        });
        console.debug(logPrefix, "Workflow result action listener attached to history list.");
    }
});