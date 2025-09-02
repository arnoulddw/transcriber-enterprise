# tests/functional/workflow/test_workflow_management.py

import json
from tests.functional.helpers.test_data import VALID_PROMPT_DATA, INVALID_PROMPT_DATA

def test_create_prompt_successfully(logged_in_client):
    """
    Test case for successful prompt creation with valid data.
    """
    response = logged_in_client.post('/api/user/prompts', data=json.dumps(VALID_PROMPT_DATA), content_type='application/json')
    assert response.status_code == 201
    data = json.loads(response.data)
    assert 'message' in data
    assert 'prompt' in data
    assert data['prompt']['title'] == VALID_PROMPT_DATA['title']

def test_create_prompt_with_missing_fields(logged_in_client):
    """
    Test case for prompt creation with missing required fields.
    """
    response = logged_in_client.post('/api/user/prompts', data=json.dumps({}), content_type='application/json')
    assert response.status_code == 400

def test_create_prompt_with_invalid_data(logged_in_client):
    """
    Test case for prompt creation with invalid data types.
    """
    response = logged_in_client.post('/api/user/prompts', data=json.dumps(INVALID_PROMPT_DATA), content_type='application/json')
    assert response.status_code == 400

def test_create_prompt_with_duplicate_name(logged_in_client):
    """
    Test case for prompt creation with a duplicate name.
    """
    logged_in_client.post('/api/user/prompts', data=json.dumps(VALID_PROMPT_DATA), content_type='application/json')
    response = logged_in_client.post('/api/user/prompts', data=json.dumps(VALID_PROMPT_DATA), content_type='application/json')
    assert response.status_code == 409

def test_edit_prompt_successfully(logged_in_client):
    """
    Test case for successful prompt editing with valid changes.
    """
    response = logged_in_client.post('/api/user/prompts', data=json.dumps(VALID_PROMPT_DATA), content_type='application/json')
    prompt_id = json.loads(response.data)['prompt']['id']
    updated_data = {
        'title': 'Updated Prompt',
        'prompt_text': 'This is an updated prompt.',
        'color': '#000000'
    }
    response = logged_in_client.put(f'/api/user/prompts/{prompt_id}', data=json.dumps(updated_data), content_type='application/json')
    assert response.status_code == 200

def test_edit_non_existent_prompt(logged_in_client):
    """
    Test case for editing a non-existent prompt.
    """
    updated_data = {
        'title': 'Updated Prompt',
        'prompt_text': 'This is an updated prompt.',
        'color': '#000000'
    }
    response = logged_in_client.put('/api/user/prompts/999', data=json.dumps(updated_data), content_type='application/json')
    assert response.status_code == 404

def test_edit_prompt_with_invalid_data(logged_in_client):
    """
    Test case for editing a prompt with invalid data.
    """
    response = logged_in_client.post('/api/user/prompts', data=json.dumps(VALID_PROMPT_DATA), content_type='application/json')
    prompt_id = json.loads(response.data)['prompt']['id']
    response = logged_in_client.put(f'/api/user/prompts/{prompt_id}', data=json.dumps(INVALID_PROMPT_DATA), content_type='application/json')
    assert response.status_code == 400

def test_delete_prompt_successfully(logged_in_client):
    """
    Test case for successful prompt deletion.
    """
    response = logged_in_client.post('/api/user/prompts', data=json.dumps(VALID_PROMPT_DATA), content_type='application/json')
    prompt_id = json.loads(response.data)['prompt']['id']
    response = logged_in_client.delete(f'/api/user/prompts/{prompt_id}')
    assert response.status_code == 200

def test_delete_non_existent_prompt(logged_in_client):
    """
    Test case for deleting a non-existent prompt.
    """
    response = logged_in_client.delete('/api/user/prompts/999')
    assert response.status_code == 404