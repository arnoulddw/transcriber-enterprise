# tests/functional/services/test_email_service.py

import pytest
from unittest.mock import patch, MagicMock

from app.services import email_service
from app.services.email_service import EmailServiceError

# --- Fixtures ---

@pytest.fixture
def mock_email_dependencies(app):
    """Mocks all dependencies for the email service."""
    with app.test_request_context():
        with patch('app.services.email_service.current_app', autospec=True) as mock_current_app, \
             patch('app.services.email_service.render_template', autospec=True) as mock_render_template, \
             patch('app.services.email_service.mail') as mock_mail, \
             patch('app.services.email_service.Message', autospec=True) as mock_message:

            # Configure mock app to simulate full configuration
            mock_current_app.config = {
                'MAIL_SERVER': 'smtp.test.com',
                'MAIL_DEFAULT_SENDER': 'noreply@test.com',
                'MAIL_USERNAME': 'testuser',
                'MAIL_PASSWORD': 'testpassword'
            }
            
            # Mock render_template to return simple strings
            mock_render_template.side_effect = lambda template, **kwargs: f"Rendered {template} with {kwargs}"

            yield {
                "current_app": mock_current_app,
                "render_template": mock_render_template,
                "mail": mock_mail,
                "message": mock_message
            }

# --- Test Cases ---

def test_send_password_reset_email_success(app, mock_email_dependencies):
    """Tests successful sending of a password reset email."""
    with app.app_context():
        email_service.send_password_reset_email('test@example.com', 'testuser', 'test_token')
        
        # Verify that the email was constructed and sent correctly
        mock_email_dependencies['mail'].send.assert_called_once()
        mock_email_dependencies['message'].assert_called_once()


def test_send_password_reset_email_missing_config(app, mock_email_dependencies):
    """Tests that an error is raised if email configuration is incomplete."""
    # Simulate missing configuration
    mock_email_dependencies['current_app'].config = {
        'MAIL_SERVER': '',
        'MAIL_DEFAULT_SENDER': ''
    }
    
    with app.app_context():
        with pytest.raises(EmailServiceError, match="Email service is not configured."):
            email_service.send_password_reset_email('test@example.com', 'testuser', 'test_token')


def test_send_password_reset_email_url_generation_fails(app, mock_email_dependencies):
    """Tests that an error is raised if the reset URL cannot be generated."""
    with patch('app.services.email_service.url_for', side_effect=RuntimeError("Test error")):
        with app.app_context():
            with pytest.raises(EmailServiceError, match="Could not generate password reset URL."):
                email_service.send_password_reset_email('test@example.com', 'testuser', 'test_token')


def test_send_password_reset_email_sending_fails(app, mock_email_dependencies):
    """Tests that an error is raised if mail.send() fails."""
    mock_email_dependencies['mail'].send.side_effect = Exception("SMTP Error")
    
    with app.app_context():
        with pytest.raises(EmailServiceError, match="Failed to send password reset email."):
            email_service.send_password_reset_email('test@example.com', 'testuser', 'test_token')
