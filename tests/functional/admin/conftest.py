import pytest
from flask import Flask
from app.models.role import get_role_by_name, create_role
from app.services.auth_service import create_user, get_user_by_username


@pytest.fixture(scope='function')
def admin_client(app: Flask, clean_db):
    """A test client logged in as an admin user."""
    with app.test_client() as client:
        with app.app_context():
            # Create dedicated test admin role to avoid mutating real 'admin'
            if not get_role_by_name('admin_test_role'):
                create_role(
                    name='admin_test_role',
                    description='Administrator (test)',
                    permissions={
                        'access_admin_panel': True,
                        'manage_workflow_templates': True,
                    }
                )

            # Create a test admin user if it doesn't exist
            if not get_user_by_username('adminuser'):
                create_user(
                    username='adminuser',
                    password='admin_password',
                    email='adminuser@example.com',
                    role_name='admin_test_role'
                )
            
            # Log in the admin user
            client.post('/login', json={'username': 'adminuser', 'password': 'admin_password'})
            
            yield client
