# tests/functional/routes/test_auth_routes.py

import pytest
from flask import url_for
from app.models import user as user_model
from app.models import role as role_model
from app.services import auth_service
from app.database import get_db, get_cursor

def test_register_user_successfully(client, clean_db):
    """
    Tests that a user can register successfully through the registration route.
    """
    with client.application.app_context():
        role_model.create_role('test-role', 'A role for testing')
        role_model.create_role('beta-tester', 'Beta Tester')
        response = client.post(url_for('auth.register'), data={
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': 'test-role'
        }, follow_redirects=True)
    
        assert response.status_code == 200
    
        db = get_db()
        db.commit()
        cursor = get_cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s", ('newuser',))
        user = cursor.fetchone()
        assert user is not None
        assert user['email'] == 'newuser@example.com'


def test_register_duplicate_username(client, clean_db):
    """
    Tests that registering with a duplicate username fails.
    """
    with client.application.app_context():
        role_model.create_role('test-role', 'A role for testing')
        role_model.create_role('beta-tester', 'Beta Tester')
        auth_service.create_user('existinguser', 'password', 'exists@example.com', 'test-role')
        response = client.post(url_for('auth.register'), data={
            'username': 'existinguser',
            'email': 'new@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': 'test-role'
        }, follow_redirects=True)
    
        assert response.status_code == 200
        assert b"Username 'existinguser' is already taken." in response.data


def test_register_duplicate_email(client, clean_db):
    """
    Tests that registering with a duplicate email fails.
    """
    with client.application.app_context():
        role_model.create_role('test-role', 'A role for testing')
        role_model.create_role('beta-tester', 'Beta Tester')
        auth_service.create_user('existinguser', 'password', 'exists@example.com', 'test-role')
        response = client.post(url_for('auth.register'), data={
            'username': 'newuser',
            'email': 'exists@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'role': 'test-role'
        }, follow_redirects=True)
    
        assert response.status_code == 200
        assert b"Email address 'exists@example.com' is already registered." in response.data


def test_login_successfully(client, clean_db):
    """
    Tests that a user can log in successfully.
    """
    with client.application.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        response = client.post(url_for('auth.login'), data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)
    
        assert response.status_code == 200
        assert b'Logged in successfully' in response.data


def test_login_incorrect_password(client, clean_db):
    """
    Tests that logging in with an incorrect password fails.
    """
    with client.application.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        response = client.post(url_for('auth.login'), data={
            'username': 'testuser',
            'password': 'wrongpassword'
        }, follow_redirects=True)
    
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data


def test_login_non_existent_user(client, clean_db):
    """
    Tests that logging in with a non-existent username fails.
    """
    with client.application.app_context():
        response = client.post(url_for('auth.login'), data={
            'username': 'nouser',
            'password': 'password123'
        }, follow_redirects=True)
    
        assert response.status_code == 200
        assert b'Invalid username or password' in response.data


def test_logout_successfully(client, clean_db):
    """
    Tests that a logged-in user can successfully log out.
    """
    with client.application.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        client.post(url_for('auth.login'), data={
            'username': 'testuser',
            'password': 'password123'
        }, follow_redirects=True)

        response = client.get(url_for('auth.logout'), follow_redirects=True)
    
        assert response.status_code == 200
        assert b'You have been logged out' in response.data
