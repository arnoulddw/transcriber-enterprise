# tests/functional/services/test_auth_service.py

import pytest
from app.services import auth_service
from app.models import role as role_model
from app.services.auth_service import AuthServiceError

def test_create_user_successfully(app, clean_db):
    """
    Tests that a user can be created successfully with valid data.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        user = auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        assert user is not None
        assert user.username == 'testuser'
        assert user.email == 'test@example.com'
        assert user.role.name == 'test-role'

def test_create_user_duplicate_username(app, clean_db):
    """
    Tests that creating a user with a duplicate username raises an AuthServiceError.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        with pytest.raises(AuthServiceError, match="Username 'testuser' is already taken."):
            auth_service.create_user('testuser', 'anotherpassword', 'another@example.com', 'test-role')

def test_create_user_duplicate_email(app, clean_db):
    """
    Tests that creating a user with a duplicate email raises an AuthServiceError.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        with pytest.raises(AuthServiceError, match="Email address 'test@example.com' is already registered."):
            auth_service.create_user('anotheruser', 'anotherpassword', 'test@example.com', 'test-role')

def test_verify_password_correct(app, clean_db):
    """
    Tests that password verification succeeds with the correct password.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        user = auth_service.verify_password('testuser', 'password123')
        assert user is not None
        assert user.username == 'testuser'

def test_verify_password_incorrect(app, clean_db):
    """
    Tests that password verification fails with an incorrect password.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        user = auth_service.verify_password('testuser', 'wrongpassword')
        assert user is None

def test_password_reset_token_generation_and_verification(app, clean_db):
    """
    Tests that a password reset token can be generated and successfully verified.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        user = auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        
        token = auth_service.generate_password_reset_token(user.id)
        assert token is not None
        
        verified_user_id = auth_service.verify_password_reset_token(token)
        assert verified_user_id == user.id

def test_verify_expired_password_reset_token(app, clean_db):
    """
    Tests that an expired password reset token fails verification.
    """
    with app.app_context():
        role_model.create_role('test-role', 'A role for testing')
        user = auth_service.create_user('testuser', 'password123', 'test@example.com', 'test-role')
        
        token = auth_service.generate_password_reset_token(user.id)
        
        import time
        time.sleep(2)  # Wait for the token to expire
        
        from itsdangerous import SignatureExpired
        with pytest.raises(SignatureExpired):
            s = auth_service._get_serializer()
            s.loads(token, max_age=1)