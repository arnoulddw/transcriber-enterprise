# tests/functional/conftest.py

import pytest
import json

@pytest.fixture(scope='function')
def clean_db(app):
    """Truncate all tables in the test database and reset auto-increment."""
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
        # Reset centralized catalog tables to ensure consistent test state
        cursor.execute("TRUNCATE TABLE transcription_models_catalog")
        cursor.execute("TRUNCATE TABLE transcription_languages_catalog")
        # Explicitly reset auto-increment to ensure fresh IDs
        cursor.execute("ALTER TABLE roles AUTO_INCREMENT = 1")
        cursor.execute("ALTER TABLE users AUTO_INCREMENT = 1")
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
    import logging
    from unittest.mock import _patch
    logger = logging.getLogger(__name__)
    
    # Stop any active patches that might interfere (from previous tests)
    patches_stopped = 0
    for patch_obj in list(_patch._active_patches):
        try:
            patch_obj.stop()
            patches_stopped += 1
        except:
            pass
    
    if patches_stopped > 0:
        logger.warning(f"FIXTURE: Stopped {patches_stopped} lingering patches from previous tests")
    
    with app.test_client() as client:
        with app.app_context():
            from app.services import auth_service
            from app.models import role as role_model
            from app.models import user as user_model
            from app.database import get_db
            
            logger.info("=" * 80)
            logger.info("FIXTURE: logged_in_client_with_permissions - START")
            logger.info("=" * 80)
            
            # Verify clean state - no roles should exist after clean_db
            existing_roles = role_model.get_all_roles()
            logger.info(f"FIXTURE: Checking database state - found {len(existing_roles)} existing roles")
            if existing_roles:
                logger.warning(f"FIXTURE: Found {len(existing_roles)} existing roles after clean_db: {[(r.id, r.name, r.use_api_openai_whisper) for r in existing_roles]}")
                # Force clean the roles table again
                cursor = get_db().cursor()
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                cursor.execute("TRUNCATE TABLE roles")
                cursor.execute("ALTER TABLE roles AUTO_INCREMENT = 1")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                get_db().commit()
                cursor.close()
                logger.info("FIXTURE: Forced roles table cleanup")
            else:
                logger.info("FIXTURE: Database is clean - no existing roles")
            
            # Always create a fresh role with correct permissions (clean_db has truncated roles table)
            logger.info("FIXTURE: Creating test_role_with_permissions")
            permissions = {
                'allow_workflows': True,
                'use_api_openai_whisper': True,
                'allow_api_key_management': True,
                'allow_auto_title_generation': True
            }
            role = role_model.create_role('test_role_with_permissions', 'A role for testing with permissions', permissions)
            if not role:
                raise RuntimeError("Failed to create test_role_with_permissions")
            logger.info(f"FIXTURE: Created role - id={role.id}, name={role.name}, use_api_openai_whisper={role.use_api_openai_whisper}")

            # Create the test user
            logger.info("FIXTURE: Creating testuser_permissions")
            auth_service.create_user('testuser_permissions', 'password123', 'test_permissions@example.com', role.name)
            
            # Enable auto-title generation for the test user
            user = user_model.get_user_by_username('testuser_permissions')
            if not user:
                raise RuntimeError("Failed to create testuser_permissions")
                
            logger.info(f"FIXTURE: Found user - id={user.id}, username={user.username}, role_id={user.role_id}, enable_auto_title={user.enable_auto_title_generation}")
            
            # Enable auto-title generation
            logger.info(f"FIXTURE: Enabling auto-title generation for user {user.id}")
            user_model.update_user_preferences(user.id, None, None, True, None)
            
            # Verify the setup (avoid accessing user.role as it may trigger lingering mocks)
            user_after = user_model.get_user_by_id(user.id)
            logger.info(f"FIXTURE: After updates - user_id={user_after.id}, role_id={user_after.role_id}, enable_auto_title={user_after.enable_auto_title_generation}")
            
            # Verify role directly from database instead of through user.role property
            role_check = role_model.get_role_by_id(user_after.role_id)
            if role_check:
                logger.info(f"FIXTURE: User role verified from DB - role_name={role_check.name}, use_api_openai_whisper={role_check.use_api_openai_whisper}, allow_auto_title_generation={role_check.allow_auto_title_generation}")
            else:
                logger.warning(f"FIXTURE: Could not load role with ID {user_after.role_id} from database!")
            
            logger.info("FIXTURE: logged_in_client_with_permissions - SETUP COMPLETE")

        # Log in the test user
        client.post('/login', data=json.dumps({
            'username': 'testuser_permissions',
            'password': 'password123'
        }), content_type='application/json', headers={'Accept': 'application/json'})

        yield client
@pytest.fixture(scope='function')
def app():
    """Create and configure a new app instance for each test session."""
    from app import create_app
    import app.database as database
    from tests.functional.config.test_config import TestConfig

    # Ensure a fresh DB pool per test to avoid cross-app leakage
    database.db_pool = None
    app = create_app(config_class=TestConfig)
    app.config['PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS'] = 3600

    with app.app_context():
        from app.initialization import initialize_database_schema, create_initialization_marker
        from app.database import get_db
        
        # Drop all tables first to ensure clean state
        cursor = get_db().cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("DROP TABLE IF EXISTS user_prompts, template_prompts, llm_operations, transcriptions, user_usage, users, roles;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        get_db().commit()
        
        # Manually run the necessary initialization for the test environment
        initialize_database_schema(create_roles=False)
        
        # Manually create the marker file to signal that initialization is complete
        create_initialization_marker(app.config)

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
        # Reset the global DB pool after each test to prevent config leakage
        import app.database as database
        database.db_pool = None
