# tests/functional/conftest.py

import pytest
import json

@pytest.fixture(scope='function')
def clean_db(app):
    """Truncate all tables in the test database."""
    with app.app_context():
        from app.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("TRUNCATE TABLE user_prompts")
        cursor.execute("TRUNCATE TABLE template_prompts")
        cursor.execute("TRUNCATE TABLE llm_operations")
        cursor.execute("TRUNCATE TABLE transcriptions")
        cursor.execute("TRUNCATE TABLE user_usage")
        cursor.execute("TRUNCATE TABLE users")
        cursor.execute("TRUNCATE TABLE roles")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        cursor.close()

@pytest.fixture(scope='function')
def logged_in_client(app, clean_db):
    """A test client that is logged in with a clean database."""
    with app.test_client() as client:
        with app.app_context():
            from app.services import auth_service
            from app.models import role as role_model
            # Create a test user and role
            if not role_model.get_role_by_name('test_role'):
                role_model.create_role('test_role', 'A role for testing')
            if not auth_service.get_user_by_username('testuser'):
                auth_service.create_user('testuser', 'testpassword', 'test@example.com', 'test_role')

        # Log in the test user
        client.post('/login', data=json.dumps({
            'username': 'testuser',
            'password': 'testpassword'
        }), content_type='application/json', headers={'Accept': 'application/json'})

        yield client

@pytest.fixture(scope='function')
def logged_in_client_with_permissions(app, clean_db):
    """A test client that is logged in with a clean database and a role with all permissions."""
    with app.test_client() as client:
        with app.app_context():
            from app.services import auth_service
            from app.models import role as role_model
            # Create a test user and role
            role = role_model.get_role_by_name('test_role_with_permissions')
            if not role:
                permissions = {
                    'allow_workflows': True,
                    'use_api_openai_whisper': True
                }
                role = role_model.create_role('test_role_with_permissions', 'A role for testing with permissions', permissions)

            if not auth_service.get_user_by_username('testuser_permissions'):
                auth_service.create_user('testuser_permissions', 'password123', 'test_permissions@example.com', role.name)

        # Log in the test user
        client.post('/login', data=json.dumps({
            'username': 'testuser_permissions',
            'password': 'password123'
        }), content_type='application/json', headers={'Accept': 'application/json'})

        yield client