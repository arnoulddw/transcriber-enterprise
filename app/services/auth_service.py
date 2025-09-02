# app/services/auth_service.py
# Handles user authentication, registration, and password verification logic.

import logging
from flask import current_app, session
from typing import Optional, Dict, Any
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import cachecontrol
import requests

from app.extensions import bcrypt
from app.models import user as user_model
from app.models.user import User
from app.models import role as role_model
from app.services import user_service

from mysql.connector import Error as MySQLError

class AuthServiceError(Exception):
    """Custom exception for authentication service errors."""
    pass

class InvalidCredentialsError(AuthServiceError):
    """Exception for invalid current password during change."""
    pass


_google_session = None

def _get_google_session():
    """Creates a cached HTTP session for Google requests."""
    global _google_session
    if _google_session is None:
        _google_session = cachecontrol.CacheControl(requests.session())
    return _google_session

def create_user(username: str, password: str, email: str, role_name: str = 'beta-tester', language: Optional[str] = None) -> Optional[User]:
    """
    Creates a new user with a hashed password and assigns a role by name.
    Handles password hashing using Flask-Bcrypt. Now uses MySQL backend via models.

    Args:
        username: The desired username.
        password: The plain text password.
        email: The user's email address.
        role_name: The name of the role to assign (defaults to 'beta-tester').
        language: The user's preferred UI language.

    Returns:
        The created User object or None if creation failed.

    Raises:
        AuthServiceError: If role validation fails or username/email is taken.
        ValueError: If username, password, or email is empty.
    """
    log_prefix = "[SERVICE:Auth]"
    if not username or not password or not email:
        logging.error(f"{log_prefix} Attempted to create user with empty username, password, or email.")
        raise ValueError("Username, password, and email cannot be empty.")

    try:
        role = role_model.get_role_by_name(role_name)
        if not role:
            logging.error(f"{log_prefix} Cannot create user '{username}': Role '{role_name}' not found.")
            raise AuthServiceError(f"Cannot create user: Role '{role_name}' does not exist.")

        existing_user_by_name = user_model.get_user_by_username(username)
        if existing_user_by_name:
            logging.warning(f"{log_prefix} Attempted to create user with duplicate username: {username}")
            raise AuthServiceError("Username is already taken.")
        existing_user_by_email = user_model.get_user_by_email(email)
        if existing_user_by_email:
            logging.warning(f"{log_prefix} Attempted to create user with duplicate email: {email}")
            raise AuthServiceError("Email is already registered.")

        hashed_password = bcrypt.generate_password_hash(
            password, current_app.config['BCRYPT_LOG_ROUNDS']
        ).decode('utf-8')
        logging.debug(f"{log_prefix} Password hashed for user '{username}'.")

        new_user = user_model.add_user(username, email, hashed_password, role_name, language)

        if new_user:
            from app.database import get_db
            db = get_db()
            db.commit()
            logging.info(f"{log_prefix} User '{username}' created successfully with role '{role_name}'.")
            user_service.handle_new_user_template_sync(new_user.id)
            return new_user
        else:
            logging.error(f"{log_prefix} Failed to create user '{username}' (model returned None).")
            raise AuthServiceError("Failed to save user to database.")

    except AuthServiceError as ase:
        raise ase
    except MySQLError as db_err:
        logging.error(f"{log_prefix} Database error creating user '{username}': {db_err}", exc_info=True)
        raise AuthServiceError(f"A database error occurred during user creation.") from db_err
    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error creating user '{username}': {e}", exc_info=True)
        raise AuthServiceError(f"An unexpected error occurred during user creation: {e}") from e


def verify_password(username: str, password_provided: str) -> Optional[User]:
    """
    Verifies a user's provided password against the stored hash. Uses MySQL backend via models.

    Args:
        username: The username attempting to log in.
        password_provided: The plain text password provided.

    Returns:
        The User object if authentication is successful, None otherwise.
    """
    log_prefix = "[SERVICE:Auth]"
    if not username or not password_provided:
        logging.warning(f"{log_prefix} Verify password called with empty username or password.")
        return None

    try:
        user = user_model.get_user_by_username(username)

        if user and user.password_hash:
            if bcrypt.check_password_hash(user.password_hash, password_provided):
                logging.info(f"{log_prefix} Password verification successful for user '{username}'.")
                return user
            else:
                logging.warning(f"{log_prefix} Password verification failed for user '{username}'.")
                return None
        elif user and not user.password_hash:
             logging.warning(f"{log_prefix} Login attempt for user '{username}' failed: User exists but has no password set (likely OAuth user).")
             return None
        else:
            logging.warning(f"{log_prefix} User '{username}' not found during password verification.")
            return None
    except MySQLError as db_err:
        logging.error(f"{log_prefix} Database error during password verification for user '{username}': {db_err}", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"{log_prefix} Error during password verification for user '{username}': {e}", exc_info=True)
        return None


def verify_google_id_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies the Google ID token and returns the user info payload if valid.

    Args:
        token: The ID token string received from the frontend.

    Returns:
        A dictionary containing user info (sub, email, name, etc.) or None if invalid.

    Raises:
        AuthServiceError: If verification fails due to configuration or other issues.
    """
    log_prefix = "[SERVICE:Auth:Google]"
    if not token:
        logging.warning(f"{log_prefix} Received empty Google ID token.")
        return None

    google_client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    if not google_client_id:
        logging.error(f"{log_prefix} GOOGLE_CLIENT_ID is not configured. Cannot verify token.")
        raise AuthServiceError("Google Sign-In is not configured on the server.")

    try:
        request_session = _get_google_session()
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(session=request_session), google_client_id)
        logging.info(f"{log_prefix} Google ID token verified successfully for email: {idinfo.get('email')}")
        return idinfo

    except ValueError as e:
        logging.error(f"{log_prefix} Google ID token verification failed: {e}", exc_info=True)
        raise AuthServiceError(f"Invalid Google Sign-In token: {e}") from e
    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error verifying Google ID token: {e}", exc_info=True)
        raise AuthServiceError("An unexpected error occurred during Google Sign-In verification.") from e


def handle_google_login(idinfo: Dict[str, Any]) -> Optional[User]:
    """
    Handles user login/registration based on verified Google ID token info.
    Finds existing user by Google ID or email, or creates a new user.

    Args:
        idinfo: The dictionary of claims from the verified Google ID token.

    Returns:
        The User object (existing or newly created) or None on failure.

    Raises:
        AuthServiceError: If user creation/linking fails.
    """
    log_prefix = "[SERVICE:Auth:Google]"
    provider = 'google'
    provider_id = idinfo.get('sub')
    email = idinfo.get('email')
    first_name = idinfo.get('given_name')
    last_name = idinfo.get('family_name')

    if not provider_id or not email:
        logging.error(f"{log_prefix} Missing 'sub' (Google ID) or 'email' in verified token payload.")
        raise AuthServiceError("Incomplete user information received from Google.")

    try:
        user = user_model.get_user_by_oauth(provider, provider_id)
        if user:
            logging.info(f"{log_prefix} Found existing user ID {user.id} via Google ID {provider_id}.")
            return user

        user = user_model.get_user_by_email(email)
        if user:
            logging.info(f"{log_prefix} Found existing user ID {user.id} via email {email}. Linking Google ID {provider_id}.")
            success = user_model.link_oauth_to_user(user.id, provider, provider_id)
            if not success:
                 raise AuthServiceError(f"Failed to link Google account to existing user {user.id}.")
            return user

        logging.info(f"{log_prefix} No existing user found for Google ID {provider_id} or email {email}. Creating new user.")
        language_from_session = session.get('language')
        if language_from_session:
            logging.info(f"{log_prefix} Found language '{language_from_session}' in session for new OAuth user.")
        
        new_user = user_model.add_oauth_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            oauth_provider=provider,
            oauth_provider_id=provider_id,
            language=language_from_session
        )
        if not new_user:
            logging.error(f"{log_prefix} Failed to create new user via add_oauth_user for email {email}.")
            raise AuthServiceError("Failed to create new user account after Google Sign-In.")
        
        logging.info(f"{log_prefix} Successfully created new user ID {new_user.id} for email {email} via Google Sign-In.")
        user_service.handle_new_user_template_sync(new_user.id)
        return new_user

    except MySQLError as db_err:
        logging.error(f"{log_prefix} Database error during Google login handling for email {email}: {db_err}", exc_info=True)
        raise AuthServiceError("A database error occurred during Google Sign-In.") from db_err
    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error during Google login handling for email {email}: {e}", exc_info=True)
        if isinstance(e, AuthServiceError):
            raise e
        else:
            raise AuthServiceError("An unexpected error occurred during Google Sign-In.") from e


def get_user_by_username(username: str) -> Optional[User]:
    """Retrieves a user by username (simple wrapper around model function using MySQL)."""
    try:
        return user_model.get_user_by_username(username)
    except MySQLError as db_err:
        logging.error(f"[SERVICE:Auth] DB error calling get_user_by_username for '{username}': {db_err}", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"[SERVICE:Auth] Error calling get_user_by_username for '{username}': {e}", exc_info=True)
        return None

def get_user_by_email(email: str) -> Optional[User]:
    """Retrieves a user by email address (simple wrapper around model function using MySQL)."""
    try:
        return user_model.get_user_by_email(email)
    except MySQLError as db_err:
        logging.error(f"[SERVICE:Auth] DB error calling get_user_by_email for '{email}': {db_err}", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"[SERVICE:Auth] Error calling get_user_by_email for '{email}': {e}", exc_info=True)
        return None

def get_user_by_id(user_id: int) -> Optional[User]:
    """Retrieves a user by ID (simple wrapper around model function using MySQL)."""
    try:
        return user_model.get_user_by_id(user_id)
    except MySQLError as db_err:
        logging.error(f"[SERVICE:Auth] DB error calling get_user_by_id for ID '{user_id}': {db_err}", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"[SERVICE:Auth] Error calling get_user_by_id for ID '{user_id}': {e}", exc_info=True)
        return None

def _get_serializer() -> URLSafeTimedSerializer:
    """Creates a serializer instance using the app's secret key."""
    secret_key = current_app.config.get('SECRET_KEY')
    if not secret_key:
        raise AuthServiceError("SECRET_KEY is not configured, cannot generate tokens.")
    return URLSafeTimedSerializer(secret_key, salt='password-reset-salt')

def generate_password_reset_token(user_id: int) -> str:
    """Generates a secure, time-limited token for password reset."""
    log_prefix = f"[SERVICE:Auth:Token:User:{user_id}]"
    try:
        s = _get_serializer()
        token = s.dumps(user_id)
        logging.info(f"{log_prefix} Generated password reset token.")
        return token
    except Exception as e:
        logging.error(f"{log_prefix} Failed to generate password reset token: {e}", exc_info=True)
        raise AuthServiceError("Could not generate password reset token.") from e

def verify_password_reset_token(token: str) -> Optional[int]:
    """Verifies a password reset token and returns the user ID if valid."""
    log_prefix = "[SERVICE:Auth:Token]"
    try:
        s = _get_serializer()
        max_age_seconds = 3600
        user_id = s.loads(token, max_age=max_age_seconds)
        logging.info(f"{log_prefix} Password reset token verified successfully for user ID {user_id}.")
        return user_id
    except SignatureExpired:
        logging.warning(f"{log_prefix} Password reset token expired: {token}")
        return None
    except BadSignature:
        logging.warning(f"{log_prefix} Invalid password reset token signature: {token}")
        return None
    except Exception as e:
        logging.error(f"{log_prefix} Error verifying password reset token '{token}': {e}", exc_info=True)
        return None

def reset_user_password(user_id: int, new_password: str) -> bool:
    """Resets the user's password after verifying a reset token. Uses MySQL backend via models."""
    log_prefix = f"[SERVICE:Auth:ResetPwd:User:{user_id}]"
    if not new_password or len(new_password) < 8:
        logging.warning(f"{log_prefix} Password reset failed: Password too short.")
        raise ValueError("New password must be at least 8 characters long.")

    try:
        hashed_password = bcrypt.generate_password_hash(
            new_password, current_app.config['BCRYPT_LOG_ROUNDS']
        ).decode('utf-8')
        logging.debug(f"{log_prefix} New password hashed.")

        success = user_model.update_user_password_hash(user_id, hashed_password)

        if success:
            logging.info(f"{log_prefix} Password reset successfully.")
            return True
        else:
            logging.error(f"{log_prefix} Failed to update password hash in database (model returned False).")
            raise AuthServiceError("Failed to update password in database.")

    except MySQLError as db_err:
        logging.error(f"{log_prefix} Database error during password reset: {db_err}", exc_info=True)
        raise AuthServiceError("A database error occurred during password reset.") from db_err
    except Exception as e:
        logging.error(f"{log_prefix} Error during password reset: {e}", exc_info=True)
        if isinstance(e, (ValueError, AuthServiceError)):
            raise e
        else:
            raise AuthServiceError("An unexpected error occurred during password reset.") from e


def change_password(user_id: int, current_password: str, new_password: str) -> None:
    """
    Changes the password for an authenticated user.

    Args:
        user_id: The ID of the user changing their password.
        current_password: The user's current password for verification.
        new_password: The desired new password.

    Raises:
        InvalidCredentialsError: If the current password is incorrect.
        ValueError: If the new password is too short.
        AuthServiceError: For database or unexpected errors.
    """
    log_prefix = f"[SERVICE:Auth:ChangePwd:User:{user_id}]"
    logging.info(f"{log_prefix} Password change request received.")

    user = get_user_by_id(user_id)
    if not user:
        logging.error(f"{log_prefix} User not found during password change attempt.")
        raise AuthServiceError("User not found.")
    if not user.password_hash:
        logging.warning(f"{log_prefix} Password change attempt failed: User '{user.username}' has no password set (likely OAuth).")
        raise AuthServiceError("Password change is not available for this account type.")


    if not verify_password(user.username, current_password):
        logging.warning(f"{log_prefix} Password change failed: Incorrect current password provided.")
        raise InvalidCredentialsError("Incorrect current password.")

    if not new_password or len(new_password) < 8:
        logging.warning(f"{log_prefix} Password change failed: New password too short.")
        raise ValueError("New password must be at least 8 characters long.")

    try:
        success = reset_user_password(user_id, new_password)
        if not success:
            raise AuthServiceError("Failed to update password in database.")
        logging.info(f"{log_prefix} Password changed successfully.")
    except (ValueError, AuthServiceError) as e:
        logging.error(f"{log_prefix} Error during password update step: {e}")
        raise e
    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error during password update step: {e}", exc_info=True)
        raise AuthServiceError("An unexpected error occurred while changing the password.") from e

def is_admin(user: Optional[User]) -> bool:
    """
    Checks if a given user object has administrative privileges.
    Currently checks if the user's role has the 'access_admin_panel' permission.
    """
    is_admin_user = False
    if user and user.is_authenticated and user.role:
        is_admin_user = user.role.access_admin_panel

    username = user.username if user else 'None'
    logging.debug(f"[SERVICE:Auth] Admin check for user '{username}': {'Yes' if is_admin_user else 'No'}")
    return is_admin_user