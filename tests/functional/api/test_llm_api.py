# tests/functional/api/test_llm_api.py
# Contains functional tests for the LLM API endpoints.

import pytest
from unittest.mock import patch, MagicMock

# --- Fixtures ---

@pytest.fixture(autouse=True)
def mock_llm_dependencies(monkeypatch):
    """Mocks all external dependencies for the LLM API tests."""
    # Mock llm_service
    mock_llm_service = MagicMock()
    mock_llm_service.generate_text_via_llm.return_value = "Mocked LLM response"
    monkeypatch.setattr('app.api.llm.llm_service', mock_llm_service)

    # Mock llm_operation_model
    mock_llm_op_model = MagicMock()
    monkeypatch.setattr('app.api.llm.llm_operation_model', mock_llm_op_model)

    # Mock current_app config
    # Using monkeypatch on current_app directly is tricky.
    # Instead, we can patch the config attribute of the app context.
    # This will be done within tests where specific config is needed.

    yield {
        "llm_service": mock_llm_service,
        "llm_operation_model": mock_llm_op_model
    }

# --- Test Cases ---

# --- Tests for /generate endpoint ---

def test_generate_llm_text_success(logged_in_client, mock_llm_dependencies, app):
    """
    GIVEN a logged-in user and a valid prompt
    WHEN the /api/llm/generate endpoint is called
    THEN it should return a 200 OK with the mocked LLM response.
    """
    with app.app_context():
        # The API route checks config directly, so we must set it
        app.config['OPENAI_API_KEY'] = 'test_key'

    response = logged_in_client.post('/api/llm/generate', json={'prompt': 'Hello, world!', 'provider': 'openai'})

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['result'] == "Mocked LLM response"
    # The API route calls the service, so this mock should be called
    mock_llm_dependencies['llm_service'].generate_text_via_llm.assert_called_once()

def test_generate_llm_text_no_prompt(logged_in_client):
    """
    GIVEN a logged-in user
    WHEN the /api/llm/generate endpoint is called with no prompt
    THEN it should return a 400 Bad Request.
    """
    response = logged_in_client.post('/api/llm/generate', json={})
    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    assert 'Missing prompt' in json_data['error']

def test_generate_llm_text_requires_login(client):
    """
    GIVEN no logged-in user
    WHEN the /api/llm/generate endpoint is called
    THEN it should return a 401 Unauthorized.
    """
    response = client.post('/api/llm/generate', json={'prompt': 'test'})
    assert response.status_code == 401

def test_generate_llm_text_configuration_error(logged_in_client, mock_llm_dependencies, app):
    """
    GIVEN the required API key is not in the config
    WHEN the /api/llm/generate endpoint is called
    THEN it should return a 400 Bad Request.
    """
    from app.services.api_clients.exceptions import LlmConfigurationError
    # Ensure the key is missing from the config
    with app.app_context():
        app.config['OPENAI_API_KEY'] = None

    response = logged_in_client.post('/api/llm/generate', json={'prompt': 'test', 'provider': 'openai'})

    assert response.status_code == 400
    json_data = response.get_json()
    assert 'error' in json_data
    assert "API key for LLM provider 'openai' is not configured" in json_data['error']

def test_generate_llm_text_api_error(logged_in_client, mock_llm_dependencies, app):
    """
    GIVEN the llm_service raises an LlmApiError
    WHEN the /api/llm/generate endpoint is called
    THEN it should return a 500 Internal Server Error.
    """
    from app.services.api_clients.exceptions import LlmApiError
    # The key must be present for the route to proceed to call the service
    with app.app_context():
        app.config['OPENAI_API_KEY'] = 'a-valid-key'
        
    mock_llm_dependencies['llm_service'].generate_text_via_llm.side_effect = LlmApiError("API failed")

    response = logged_in_client.post('/api/llm/generate', json={'prompt': 'test', 'provider': 'openai'})

    assert response.status_code == 500
    json_data = response.get_json()
    assert 'error' in json_data
    assert 'API failed' in json_data['error']

# --- Tests for /operations/<id>/status endpoint ---

def test_get_llm_operation_status_success(logged_in_client, mock_llm_dependencies):
    """
    GIVEN a logged-in user and a valid operation ID they own
    WHEN the /api/llm/operations/<id>/status endpoint is called
    THEN it should return a 200 OK with the operation status.
    """
    mock_op = {
        'status': 'finished',
        'result': 'Final result',
        'error': None,
        'provider': 'test_provider',
        'operation_type': 'test_op',
        'created_at': '2023-01-01T00:00:00',
        'completed_at': '2023-01-01T00:01:00',
        'transcription_id': 1,
        'prompt_id': 1
    }
    mock_llm_dependencies['llm_operation_model'].get_llm_operation_by_id.return_value = mock_op

    response = logged_in_client.get('/api/llm/operations/123/status')

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['operation_id'] == 123
    assert json_data['status'] == 'finished'
    assert json_data['result'] == 'Final result'
    mock_llm_dependencies['llm_operation_model'].get_llm_operation_by_id.assert_called_with(123, 1) # user_id=1 from logged_in_client

def test_get_llm_operation_status_not_found(logged_in_client, mock_llm_dependencies):
    """
    GIVEN a logged-in user
    WHEN the /api/llm/operations/<id>/status endpoint is called with an unknown ID
    THEN it should return a 404 Not Found.
    """
    mock_llm_dependencies['llm_operation_model'].get_llm_operation_by_id.return_value = None

    response = logged_in_client.get('/api/llm/operations/999/status')

    assert response.status_code == 404
    json_data = response.get_json()
    assert 'error' in json_data
    assert 'not found' in json_data['error']

def test_get_llm_operation_status_access_denied(logged_in_client, mock_llm_dependencies):
    """
    GIVEN a logged-in user
    WHEN they request an operation they do not own
    THEN it should return a 403 Forbidden.
    """
    # Simulate finding the operation without user_id, but not with it
    mock_llm_dependencies['llm_operation_model'].get_llm_operation_by_id.side_effect = [
        None, # Call with user_id fails
        {'id': 456} # Call without user_id succeeds
    ]

    response = logged_in_client.get('/api/llm/operations/456/status')

    assert response.status_code == 403
    json_data = response.get_json()
    assert 'error' in json_data
    assert 'Access denied' in json_data['error']

def test_get_llm_operation_status_requires_login(client):
    """
    GIVEN no logged-in user
    WHEN the /api/llm/operations/<id>/status endpoint is called
    THEN it should return a 401 Unauthorized.
    """
    response = client.get('/api/llm/operations/123/status')
    assert response.status_code == 401