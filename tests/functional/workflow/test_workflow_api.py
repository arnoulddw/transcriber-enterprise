import pytest
from unittest.mock import patch

from app.services.workflow_service import (
    OperationNotFoundError,
    PermissionDeniedError,
    UsageLimitExceededError,
    TranscriptionNotFoundError,
)
from app.models import role as role_model


@pytest.fixture(autouse=True)
def ensure_app_context(app):
    """
    Provide application context for url building and logging.
    """
    with app.app_context():
        yield


def _get_permissions_user_id(client):
    from app.models.user import get_user_by_username

    with client.application.app_context():
        user = get_user_by_username("testuser_permissions")
        return user.id


@pytest.fixture
def client_with_workflow_permission(logged_in_client_with_permissions):
    return logged_in_client_with_permissions


def test_run_workflow_success(client_with_workflow_permission):
    transcription_id = "abc123"
    user_id = _get_permissions_user_id(client_with_workflow_permission)
    with patch(
        "app.api.workflows.workflow_service.start_workflow", return_value=42
    ) as mock_start:
        response = client_with_workflow_permission.post(
            f"/api/transcriptions/{transcription_id}/workflow",
            json={"prompt": "Summarize this transcript."},
        )

    assert response.status_code == 202
    data = response.get_json()
    assert data["message"] == "Workflow started successfully."
    assert data["operation_id"] == 42
    mock_start.assert_called_once_with(
        user_id,
        transcription_id,
        "Summarize this transcript.",
        None,
    )


def test_run_workflow_with_prompt_id(client_with_workflow_permission):
    transcription_id = "job456"
    user_id = _get_permissions_user_id(client_with_workflow_permission)
    with patch(
        "app.api.workflows.workflow_service.start_workflow", return_value=77
    ) as mock_start:
        response = client_with_workflow_permission.post(
            f"/api/transcriptions/{transcription_id}/workflow",
            json={"prompt": "Use saved prompt", "prompt_id": "8"},
        )

    assert response.status_code == 202
    mock_start.assert_called_once_with(
        user_id, transcription_id, "Use saved prompt", 8
    )


def test_run_workflow_missing_prompt(client_with_workflow_permission):
    response = client_with_workflow_permission.post(
        "/api/transcriptions/some-id/workflow", json={}
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Please include a workflow prompt before submitting."


def test_run_workflow_permission_denied(client_with_workflow_permission):
    with patch(
        "app.api.workflows.workflow_service.start_workflow",
        side_effect=PermissionDeniedError("nope"),
    ):
        response = client_with_workflow_permission.post(
            "/api/transcriptions/xyz/workflow",
            json={"prompt": "Summarize"},
        )
    assert response.status_code == 403
    assert "nope" in response.get_json()["error"]


def test_run_workflow_usage_limit(client_with_workflow_permission):
    with patch(
        "app.api.workflows.workflow_service.start_workflow",
        side_effect=UsageLimitExceededError("limit hit"),
    ):
        response = client_with_workflow_permission.post(
            "/api/transcriptions/xyz/workflow",
            json={"prompt": "Summarize"},
        )
    assert response.status_code == 403
    payload = response.get_json()
    assert payload["error"] == "You have reached your workflow usage limit. Please try again later. Details: limit hit"
    assert payload["code"] == "WORKFLOW_LIMIT_EXCEEDED"


def test_edit_workflow_success(client_with_workflow_permission):
    user_id = _get_permissions_user_id(client_with_workflow_permission)
    with patch(
        "app.api.workflows.workflow_service.edit_workflow_result"
    ) as mock_edit:
        response = client_with_workflow_permission.put(
            "/api/workflows/operations/99",
            json={"result": "Updated text"},
        )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Workflow result updated successfully."
    mock_edit.assert_called_once_with(user_id, 99, "Updated text")


def test_edit_workflow_missing_result(client_with_workflow_permission):
    response = client_with_workflow_permission.put(
        "/api/workflows/operations/99", json={}
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Please include the updated workflow result in your request."


def test_edit_workflow_not_found(client_with_workflow_permission):
    with patch(
        "app.api.workflows.workflow_service.edit_workflow_result",
        side_effect=OperationNotFoundError("not found"),
    ):
        response = client_with_workflow_permission.put(
            "/api/workflows/operations/11",
            json={"result": "Updated"},
        )
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_delete_workflow_success(client_with_workflow_permission):
    user_id = _get_permissions_user_id(client_with_workflow_permission)
    with patch(
        "app.api.workflows.workflow_service.delete_workflow_result"
    ) as mock_delete:
        response = client_with_workflow_permission.delete(
            "/api/transcriptions/abc/workflow"
        )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Workflow result deleted successfully."
    mock_delete.assert_called_once_with(user_id, "abc")


def test_delete_workflow_not_found(client_with_workflow_permission):
    with patch(
        "app.api.workflows.workflow_service.delete_workflow_result",
        side_effect=TranscriptionNotFoundError("missing"),
    ):
        response = client_with_workflow_permission.delete(
            "/api/transcriptions/missing/workflow"
        )

    assert response.status_code == 404
    assert "missing" in response.get_json()["error"]
