import pytest
from flask import Flask
from app.models.role import Role
from app.services.auth_service import create_user

@pytest.fixture(scope='function')
def app(app: Flask):
    with app.app_context():
        # Import and run migrations after the app is created
        from migrations.runner import run_migrations
        run_migrations()
    yield app

@pytest.fixture(scope='function')
def admin_client(app: Flask):
    with app.test_client() as client:
        with app.app_context():
            # Create a role with admin permissions
            Role.create(name='admin', description='Administrator', permissions={'access_admin_panel': True})
            
            # Create an admin user
            create_user(
                username='admin',
                password='admin_password',
                email='admin@example.com',
                role_name='admin'
            )
            
            # Log in the admin user
            client.post('/login', json={'username': 'admin', 'password': 'admin_password'})
            
            yield client