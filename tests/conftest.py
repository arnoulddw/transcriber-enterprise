# tests/conftest.py

import pytest

@pytest.fixture(scope='session')
def app():
    """Create and configure a new app instance for each test session."""
    from app import create_app
    from app.database import db_pool
    from tests.functional.config.test_config import TestConfig

    app = create_app(config_class=TestConfig)
    app.config['PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS'] = 3600

    with app.app_context():
        from app.initialization import initialize_database_schema
        initialize_database_schema(create_roles=False)

    yield app

    with app.app_context():
        from app.database import get_db
        cursor = get_db().cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("DROP TABLE IF EXISTS user_prompts, template_prompts, llm_operations, transcriptions, user_usage, users, roles;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        get_db().commit()
        from app.database import close_db
        close_db()

@pytest.fixture(scope='function')
def clean_db(app):
    """A fixture to clean the database before each test."""
    with app.app_context():
        from app.database import get_db
        cursor = get_db().cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        # List of all tables to be truncated
        tables = [
            "user_prompts", "template_prompts", "llm_operations",
            "transcriptions", "user_usage", "users", "roles"
        ]
        for table in tables:
            cursor.execute(f"TRUNCATE TABLE {table}")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        get_db().commit()

        # Clear any caches
        from app.extensions import cache
        cache.clear()

@pytest.fixture(scope='function')
def client(app):
    """A test client for the app."""
    return app.test_client()