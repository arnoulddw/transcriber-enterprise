# app/api/auth.py
# Defines the Blueprint for authentication routes (login, logout, register).
# Handles both HTML page rendering and form submissions.

import logging
from flask import (
    Blueprint, request, jsonify, flash, redirect, url_for, render_template,
    current_app, session
)
from flask_login import login_user, logout_user, login_required, current_user
# Removed: from werkzeug.urls import url_parse
# Add this if needed later for redirect validation within this blueprint:
from urllib.parse import urlparse
# --- NEW: Import gettext for translation ---
from flask_babel import gettext as _, lazy_gettext as _l

# Import extensions and application components
from app.extensions import limiter # Import limiter instance
from app.forms import LoginForm, RegistrationForm, ForgotPasswordForm, ResetPasswordForm
from app.services import auth_service, email_service
from app.services.auth_service import AuthServiceError # Specific exception
from app.models import user as user_model

# Define the Blueprint
# No url_prefix here, routes like /login, /register are defined directly
auth_bp = Blueprint('auth', __name__)

# --- Rate Limiting ---
# Apply specific (stricter) limits to authentication endpoints
# Limit by a combination of IP address AND username (if submitted) to prevent brute-force
# on specific accounts while still limiting overall attempts from an IP.
def auth_limit_key():
    # Use username from form OR json payload OR fallback to remote IP
    username = None
    if request.form:
        username = request.form.get('username')
    elif request.is_json:
        username = request.json.get('username')
    # Combine IP and username (if available) for a more specific key
    key = f"{request.remote_addr or 'unknown'}"
    if username:
        key += f":{username}"
    return key

limit_auth_attempts = "10 per minute;100 per hour"
limit_reset_attempts = "5 per hour" # Limit password reset requests
limit_oauth_attempts = "20 per minute;200 per hour" # Limit OAuth callbacks

# --- HTML Routes for Login/Register Pages ---

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(limit_auth_attempts, key_func=auth_limit_key)
def login():
    """Handles user login page (GET) and form submission (POST)."""
    # Redirect if user is already authenticated
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) # Redirect to main index page

    form = LoginForm()
    if form.validate_on_submit(): # Handles POST validation and CSRF
        username = form.username.data
        password = form.password.data
        remember = form.remember_me.data
        log_prefix = f"[API:Auth:Login:{username}]"
        logging.info(f"{log_prefix} Login attempt received.")

        try:
            # Verify credentials using the auth service
            user = auth_service.verify_password(username, password)
            if user:
                # Log the user in using Flask-Login
                login_user(user, remember=remember)
                logging.info(f"{log_prefix} Login successful.")
                flash(_l('Logged in successfully'), 'success')
                # Prevent session fixation - Flask-Login's login_user handles marking session as fresh.

                # --- NEW: Persist language from session to profile ---
                if 'language' in session:
                    lang_to_set = session['language']
                    logging.info(f"{log_prefix} Found language '{lang_to_set}' in session. Persisting to user profile.")
                    try:
                        user_model.update_user_preferences(user.id, default_language=None, default_model=None, language=lang_to_set)
                        session.pop('language', None)
                        logging.info(f"{log_prefix} Successfully persisted language and removed from session.")
                    except Exception as e:
                        logging.error(f"{log_prefix} Failed to persist language preference from session: {e}", exc_info=True)
                # --- END NEW ---

                # Redirect to the originally requested page, or the main index
                next_page = request.args.get('next')
                # Security: Validate the next_page URL to prevent open redirect vulnerabilities
                if next_page and urlparse(next_page).netloc == '': # Check if relative
                     return redirect(next_page)
                elif next_page:
                     logging.warning(f"{log_prefix} Invalid 'next' parameter detected: {next_page}. Redirecting home.")
                     return redirect(url_for('main.index'))
                else:
                    logging.debug(f"{log_prefix} Redirecting to main index page.")
                    return redirect(url_for('main.index'))
            else:
                # Authentication failed (logged by auth_service)
                flash(_l('Invalid username or password.'), 'danger')
                logging.warning(f"{log_prefix} Login failed: Invalid credentials.")

        except Exception as e:
            # Catch unexpected errors during login process
            logging.error(f"{log_prefix} Unexpected error during login: {e}", exc_info=True)
            flash(_l('An unexpected error occurred during login. Please try again.'), 'danger')

    # Render the login page for GET requests or failed POST validation
    # Pass google_client_id from config via context processor
    return render_template('login.html', title='Login', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit(limit_auth_attempts) # Limit registration attempts by IP
def register():
    """Handles user registration page (GET) and form submission (POST)."""
    # Registration is only allowed in multi-user mode
    if current_app.config['DEPLOYMENT_MODE'] != 'multi':
        flash(_l('User registration is disabled in single-user mode.'), 'warning')
        return redirect(url_for('auth.login'))

    # Redirect if user is already authenticated
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit(): # Handles POST validation and CSRF
        username = form.username.data
        password = form.password.data
        email = form.email.data
        log_prefix = f"[API:Auth:Register:{username}]"
        logging.info(f"{log_prefix} Registration attempt received for email {email}.")

        try:
            # --- NEW: Get language from session ---
            language_from_session = session.get('language')
            if language_from_session:
                logging.info(f"{log_prefix} Found language '{language_from_session}' in session for new user.")
            # --- END NEW ---

            # Create user using the auth service (default role is 'beta-tester')
            new_user = auth_service.create_user(username, password, email, language=language_from_session)
            if new_user:
                # --- NEW: Pop language from session after successful registration ---
                if language_from_session:
                    session.pop('language', None)
                    logging.info(f"{log_prefix} Language preference from session used and removed.")
                # --- END NEW ---
                logging.info(f"{log_prefix} Registration successful.")
                flash(_l('Account created for %(username)s! You can now log in.', username=username), 'success')
                return redirect(url_for('auth.login'))
            else:
                # This path might be less likely now service raises exceptions
                flash(_l('Registration failed. Please try again.'), 'danger')

        except AuthServiceError as ase:
             # Handle specific errors from the service (e.g., username/email taken)
             logging.warning(f"{log_prefix} Registration failed: {ase}")
             flash(str(ase), 'danger') # Show the specific error message
             # No redirect here, re-render the page to show the error
        except Exception as e:
            # Catch unexpected errors during registration
            logging.error(f"{log_prefix} Unexpected error during registration: {e}", exc_info=True)
            flash(_l('An unexpected error occurred during registration. Please try again.'), 'danger')
            return redirect(url_for('auth.register'))

    # Render the registration page for GET requests or failed POST validation
    # Pass google_client_id from config via context processor
    return render_template('login.html', title='Register', form=form)


@auth_bp.route('/logout')
@login_required # User must be logged in to log out
def logout():
    """Logs the current user out."""
    username = current_user.username # Get username before logout
    logout_user()
    # Optional: Clear the session completely for extra security
    # session.clear()
    logging.info(f"[API:Auth:Logout:{username}] User logged out.")
    flash(_l('You have been logged out successfully.'), 'success')
    return redirect(url_for('auth.login')) # Redirect to login page


# --- Password Reset Routes ---

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit(limit_reset_attempts) # Limit reset requests by IP
def forgot_password():
    """Handles the 'Forgot Password' request page and form submission."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) # No need if already logged in

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data
        log_prefix = f"[API:Auth:ForgotPwd:{email}]"
        logging.info(f"{log_prefix} Forgot password request received.")
        try:
            user = auth_service.get_user_by_email(email)
            if user:
                # Generate token and send email
                token = auth_service.generate_password_reset_token(user.id)
                # Ensure email service is configured before trying to send
                if all(current_app.config.get(key) for key in ['MAIL_SERVER', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER']):
                    email_service.send_password_reset_email(user.email, user.username, token)
                    logging.info(f"{log_prefix} Password reset email sent to {email}.")
                else:
                     logging.error(f"{log_prefix} Email service not configured. Cannot send reset email.")
                     # Flash a generic message even if email sending fails server-side
                     # Avoid confirming if the email exists to prevent enumeration attacks
            else:
                logging.warning(f"{log_prefix} Forgot password request for non-existent email.")
                # Don't reveal if the user exists, just log it

            # Flash generic message regardless of user existence or email sending success
            flash(_l('If an account with that email exists, a password reset link has been sent. Please check your inbox and spam folder if you don\'t see it within a few minutes.'), 'info')
            return redirect(url_for('auth.login'))

        except Exception as e:
            logging.error(f"{log_prefix} Error processing forgot password request: {e}", exc_info=True)
            flash(_l('An error occurred while processing your request. Please try again.'), 'danger')
            # Redirect to login even on error to avoid confusion
            return redirect(url_for('auth.login'))

    return render_template('forgot_password.html', title='Forgot Password', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit(limit_reset_attempts) # Limit reset attempts by IP (token is part of URL)
def reset_password_request(token):
    """Handles the password reset link verification (GET) and new password submission (POST)."""
    if current_user.is_authenticated:
        return redirect(url_for('main.index')) # No need if already logged in

    log_prefix = f"[API:Auth:ResetPwd:{token[:8]}...]" # Log truncated token

    # Verify token first (for both GET and POST)
    user_id = auth_service.verify_password_reset_token(token)
    if not user_id:
        logging.warning(f"{log_prefix} Invalid or expired password reset token.")
        flash(_l('The password reset link is invalid or has expired.'), 'danger')
        return redirect(url_for('auth.forgot_password'))

    # Token is valid, proceed with form handling
    form = ResetPasswordForm()
    if form.validate_on_submit():
        # POST request: Process password reset
        new_password = form.password.data
        logging.info(f"{log_prefix} Valid token. Attempting password reset for user ID {user_id}.")
        try:
            success = auth_service.reset_user_password(user_id, new_password)
            if success:
                logging.info(f"{log_prefix} Password reset successful for user ID {user_id}.")
                flash(_l('Your password has been reset successfully. You can now log in.'), 'success')
                return redirect(url_for('auth.login'))
            else:
                # Should be rare if token/form are valid, but handle model failure
                flash(_l('Password reset failed. Please try again.'), 'danger')
        except Exception as e:
            logging.error(f"{log_prefix} Error resetting password for user ID {user_id}: {e}", exc_info=True)
            flash(_l('An error occurred while resetting your password. Please try again.'), 'danger')
            # Stay on the reset page on error? Or redirect to forgot? Redirecting might be less confusing.
            return redirect(url_for('auth.forgot_password'))

    # GET request: Show the reset password form
    logging.debug(f"{log_prefix} Valid token. Displaying reset password form for user ID {user_id}.")
    return render_template('reset_password.html', title='Reset Password', form=form, token=token)


# --- Google Sign-In Callback --- # <<< NEW ROUTE

@auth_bp.route('/api/auth/google-callback', methods=['POST'])
@limiter.limit(limit_oauth_attempts) # Apply rate limiting
def google_callback():
    """Handles the callback from Google Sign-In (receives ID token)."""
    log_prefix = "[API:Auth:GoogleCallback]"
    if current_user.is_authenticated:
        logging.warning(f"{log_prefix} Received callback while user {current_user.id} already logged in.")
        # Decide action: maybe link accounts or just redirect home? For now, redirect home.
        return jsonify({'success': True, 'message': _('Already logged in.'), 'redirect': url_for('main.index')})

    # Check if GOOGLE_CLIENT_ID is configured
    if not current_app.config.get('GOOGLE_CLIENT_ID'):
        logging.error(f"{log_prefix} Attempted Google Sign-In callback, but GOOGLE_CLIENT_ID is not configured.")
        return jsonify({'success': False, 'error': _('Google Sign-In is not configured on the server.')}), 500

    # Get the ID token from the JSON payload sent by the frontend JS
    data = request.get_json()
    if not data or 'id_token' not in data:
        logging.error(f"{log_prefix} Invalid request: Missing 'id_token' in JSON payload.")
        return jsonify({'success': False, 'error': _('Invalid request payload.')}), 400

    id_token_str = data['id_token']

    try:
        # Verify the token and get user info
        idinfo = auth_service.verify_google_id_token(id_token_str)
        if not idinfo:
            # Verification failed (logged by service)
            return jsonify({'success': False, 'error': _('Invalid Google token.')}), 401

        # Handle login or registration based on verified info
        user = auth_service.handle_google_login(idinfo)
        if not user:
            # Should not happen if verify succeeded, but handle defensively
            return jsonify({'success': False, 'error': _('Failed to process Google Sign-In.')}), 500

        # --- NEW: Persist language from session to profile ---
        # The language is handled inside handle_google_login if it's a new user.
        # If it's an existing user, we need to update it here.
        if 'language' in session:
            lang_to_set = session['language']
            logging.info(f"{log_prefix} Found language '{lang_to_set}' in session. Persisting to user profile for Google login.")
            try:
                user_model.update_user_preferences(user.id, default_language=None, default_model=None, language=lang_to_set)
                session.pop('language', None)
                logging.info(f"{log_prefix} Successfully persisted language and removed from session for Google login.")
            except Exception as e:
                logging.error(f"{log_prefix} Failed to persist language preference from session for Google login: {e}", exc_info=True)
        # --- END NEW ---

        # Log the user in using Flask-Login
        # Use remember=True for convenience with OAuth logins
        login_user(user, remember=True)
        logging.info(f"{log_prefix} User {user.id} ({user.email}) logged in successfully via Google.")

        # Determine redirect URL (e.g., 'next' param if provided and safe, or home)
        next_page = request.args.get('next')
        redirect_url = url_for('main.index') # Default redirect
        if next_page and urlparse(next_page).netloc == '': # Check if relative
            redirect_url = next_page
        elif next_page:
            logging.warning(f"{log_prefix} Invalid 'next' parameter during OAuth callback: {next_page}. Redirecting home.")

        return jsonify({'success': True, 'message': _('Login successful.'), 'redirect': redirect_url}), 200

    except AuthServiceError as e:
        logging.error(f"{log_prefix} Authentication service error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400 # Or 500 depending on error type
    except Exception as e:
        logging.error(f"{log_prefix} Unexpected error during Google callback: {e}", exc_info=True)
        return jsonify({'success': False, 'error': _('An unexpected server error occurred.')}), 500


# --- Optional: JSON API Endpoints (If needed for JS-driven auth) ---
# @auth_bp.route('/api/login', methods=['POST'])
# @limiter.limit(limit_auth_attempts, key_func=auth_limit_key)
# def api_login(): ...

# @auth_bp.route('/api/register', methods=['POST'])
# @limiter.limit(limit_auth_attempts)
# def api_register(): ...

# @auth_bp.route('/api/logout', methods=['POST'])
# @login_required
# def api_logout(): ...
