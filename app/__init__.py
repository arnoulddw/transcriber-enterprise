# app/__init__.py

import os
import logging
import logging.handlers # Keep this for when we revert
import threading
import time
import fcntl # For file locking
from datetime import datetime, timezone
from dateutil.parser import isoparse
from typing import Optional, Mapping, Any
from urllib.parse import urlparse
from flask import Flask, render_template, g, request, jsonify, redirect, url_for, flash, current_app, session

# Import Flask-Login current_user proxy
from flask_login import current_user
# --- NEW: Import get_locale and gettext ---
from flask_babel import get_locale, gettext as _

# Import extensions, config, blueprints, and other components
from app.config import Config
from app.extensions import bcrypt, login_manager, csrf, limiter, mail, babel
from app.database import init_app as init_db
# Import models and services needed for initialization and user loading
from app.models import role as role_model
from app.models import user as user_model
from app.models import transcription as transcription_model, llm_operation as llm_operation_model
from app.models.user import User
from app.models.role import Role
from app.services import user_service, auth_service
from app.services.auth_service import AuthServiceError
from app.tasks.cleanup import run_cleanup_task
# --- Import new initialization functions ---
from app.initialization import (
    check_initialization_marker,
    create_initialization_marker,
    run_initialization_sequence
)
# Import MySQL error class for specific handling if needed later
from mysql.connector import Error as MySQLError

# --- Logging Configuration ---
def configure_logging(config: Mapping[str, Any]) -> None:
    """Sets up application logging based on configuration."""
    log_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s'
    )
    log_level_name = config.get('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = config.get('LOG_DIR')
    log_file = config.get('LOG_FILE')

    if not log_dir or not log_file:
        print("Error: LOG_DIR or LOG_FILE not configured.")
        file_handler = None
    else:
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.handlers.TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8')
            file_handler.setFormatter(log_formatter)
            file_handler.setLevel(log_level)
        except Exception as e:
            print(f"Error setting up file log handler: {e}")
            file_handler = None

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(log_level)

    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    if file_handler:
        root_logger.addHandler(file_handler)

    # Adjust log levels for noisy libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('assemblyai').setLevel(logging.INFO)
    logging.getLogger('openai').setLevel(logging.INFO)
    logging.getLogger('pydub').setLevel(logging.INFO)
    logging.getLogger('mail').setLevel(logging.INFO)
    logging.getLogger('mysql.connector').setLevel(logging.WARNING)
    logging.getLogger('google.auth.transport.requests').setLevel(logging.WARNING) # Quieten Google auth logs
    logging.getLogger('google.generativeai').setLevel(logging.INFO) # Set to INFO or WARNING
    logging.getLogger('google_genai.models').setLevel(logging.WARNING) # Set specific google_genai.models to WARNING
    logging.getLogger('google.api_core').setLevel(logging.WARNING) # Quieten API core logs

    logging.info("[SYSTEM] Logging configured successfully.")
    logging.info(f"[SYSTEM] Log Level set to: {log_level_name}")


# --- Background Task & Initialization Management (Using File Lock) ---
_background_thread_started_in_process = False
_file_lock_handle = None

def initialize_app_resources(app: Flask):
    """
    Handles one-time application initialization (DB, roles, admin) and
    starts background tasks (like cleanup) if not already done by another worker process.
    Uses a non-blocking file lock (fcntl.flock) to ensure only one process succeeds.
    """
    global _background_thread_started_in_process, _file_lock_handle
    log_prefix = f"[SYSTEM:InitResources:PID:{os.getpid()}]"

    is_main_process_or_prod = not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

    if not is_main_process_or_prod:
        logging.debug(f"{log_prefix} Skipping resource initialization in Flask debug reloader sub-process.")
        return

    if _background_thread_started_in_process:
        logging.debug(f"{log_prefix} Background task already started in this process. Skipping.")
        return

    lock_file_path = app.config.get('TASK_LOCK_FILE')
    if not lock_file_path:
        logging.error(f"{log_prefix} TASK_LOCK_FILE not configured. Cannot initialize resources safely.")
        return

    logging.debug(f"{log_prefix} Attempting to acquire file lock for resource initialization: {lock_file_path}")

    try:
        # Ensure runtime directory exists before trying to open lock file
        runtime_dir = os.path.dirname(lock_file_path)
        os.makedirs(runtime_dir, exist_ok=True)

        _file_lock_handle = open(lock_file_path, 'a')
        fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        logging.debug(f"{log_prefix} Successfully acquired file lock.")
        initialization_done = False
        try:
            with app.app_context(): # Context needed for initialization checks/runs
                if not check_initialization_marker():
                    logging.debug(f"{log_prefix} Initialization marker not found. Running initialization sequence...")
                    # This now runs MySQL schema creation etc.
                    run_initialization_sequence(app)
                    create_initialization_marker()
                    initialization_done = True
                    logging.info(f"{log_prefix} Initialization sequence completed and marker created.")
                else:
                    logging.debug(f"{log_prefix} Initialization marker found. Skipping initialization sequence.")
                    initialization_done = True

            if initialization_done:
                logging.debug(f"{log_prefix} Proceeding to start background tasks...")
                cleanup_thread = threading.Thread(target=run_cleanup_task, args=(app,), daemon=True)
                cleanup_thread.start()
                _background_thread_started_in_process = True
                logging.debug(f"{log_prefix} Background cleanup task thread initiated.")
            else:
                 logging.error(f"{log_prefix} Initialization sequence failed. Background tasks will NOT start.")
                 fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_UN)
                 _file_lock_handle.close()
                 _file_lock_handle = None

        except Exception as e: # Catches MySQLError from initialization
             logging.critical(f"{log_prefix} CRITICAL ERROR during initialization or task startup after acquiring lock: {e}", exc_info=True)
             try:
                 fcntl.flock(_file_lock_handle.fileno(), fcntl.LOCK_UN)
                 _file_lock_handle.close()
                 _file_lock_handle = None
             except Exception as lock_release_err:
                  logging.error(f"{log_prefix} Failed to release lock after error: {lock_release_err}")

    except BlockingIOError:
        logging.debug(f"{log_prefix} File lock already held by another process. Skipping resource initialization.")
        if _file_lock_handle:
            _file_lock_handle.close()
            _file_lock_handle = None
    except Exception as e:
        logging.error(f"{log_prefix} Error acquiring file lock: {e}", exc_info=True)
        if _file_lock_handle:
            try: _file_lock_handle.close()
            except Exception: pass
            _file_lock_handle = None

# --- Timezone Formatting Filter ---
def format_datetime_tz(value, format=None): # format arg is now ignored
    """
    Jinja filter to parse a datetime string/object and convert it to a
    standardized UTC ISO 8601 string, ready for client-side processing.
    """
    if not value:
        return ""
    try:
        if isinstance(value, str):
            dt_object = isoparse(value)
        elif isinstance(value, datetime):
            dt_object = value
        else:
            return "Invalid Date Type"

        # Ensure the datetime object is timezone-aware (assume UTC if naive)
        if dt_object.tzinfo is None:
            dt_object = dt_object.replace(tzinfo=timezone.utc)

        # Convert to UTC and format as ISO 8601 string with 'Z' for UTC
        return dt_object.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    except (ValueError, TypeError) as e:
        logging.error(f"Could not parse or format datetime '{value}': {e}")
        return "Invalid Date"

# --- Contrast Color Filter ---
def get_contrast_color(hex_color: Optional[str]) -> str:
    """
    Jinja filter to determine if black or white text provides better contrast
    against a given background hex color.
    """
    if not hex_color or not hex_color.startswith('#') or len(hex_color) != 7:
        return 'black'
    try:
        hex_val = hex_color.lstrip('#')
        rgb = tuple(int(hex_val[i:i+2], 16) for i in (0, 2, 4))
        luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255
        return 'black' if luminance > 0.5 else 'white'
    except Exception as e:
        logging.error(f"Error calculating contrast color for '{hex_color}': {e}")
        return 'black'


# --- Application Factory ---
def create_app(config_class=Config) -> Flask:
    """
    Creates and configures the Flask application instance.
    """
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(config_class)
    configure_logging(app.config)
    logging.info(f"[SYSTEM] Flask app created. Deployment Mode: {app.config['DEPLOYMENT_MODE']}")
    logging.info(f"[SYSTEM] Configured Timezone (TZ): {app.config.get('TZ', 'Not Set - Defaulting to UTC')}")

    # --- MODIFIED: Define locale selector function before initializing Babel ---
    def get_locale_selector():
        supported_languages = current_app.config.get('SUPPORTED_LANGUAGES', [])
        
        # 1. If user is logged in, use their profile setting
        if (hasattr(g, 'user') and g.user and g.user.is_authenticated and
            hasattr(g.user, 'language') and
            g.user.language in supported_languages):
            return g.user.language
        
        # 2. For anonymous users, check if language was set in session by the switcher
        if 'language' in session and session['language'] in supported_languages:
            return session['language']
        
        # 3. Fallback to browser's preferred language
        if supported_languages:
            return request.accept_languages.best_match(supported_languages)
        
        # 4. Final fallback
        return 'en'  # or whatever your default language is

    # Initialize Flask Extensions
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    limiter.storage_uri = app.config['RATELIMIT_STORAGE_URI']
    limiter.default_limits = app.config['RATELIMIT_DEFAULT'].split(';')
    mail.init_app(app)
    # --- MODIFIED: Initialize Babel with the selector function ---
    babel.init_app(app, locale_selector=get_locale_selector)
    logging.debug("[SYSTEM] Flask extensions initialized (Bcrypt, LoginManager, CSRF, Limiter, Mail, Babel).")

    # Initialize Database Handling
    init_db(app)

    # Register Jinja Filters
    app.jinja_env.filters['datetime_tz'] = format_datetime_tz
    app.jinja_env.filters['contrast_color'] = get_contrast_color

    def raw_number(n):
        """Prevents Jinja from formatting a number, passing it as is."""
        return n
    app.jinja_env.filters['raw_number'] = raw_number
    logging.debug("[SYSTEM] Registered Jinja filters (datetime_tz, contrast_color, raw_number).")

    # Configure Flask-Login User Loader
    @login_manager.user_loader
    def load_user(user_id_str: str) -> Optional[User]:
        log_prefix = "[AUTH:UserLoader]"
        try:
            user_id = int(user_id_str)
            user = user_model.get_user_by_id(user_id)
            if user: logging.debug(f"{log_prefix} User {user_id} loaded successfully.")
            else: logging.warning(f"{log_prefix} User {user_id} not found in database.")
            return user
        except ValueError:
            logging.warning(f"{log_prefix} Invalid user_id format received: {user_id_str}")
            return None
        except Exception as e:
            if isinstance(e, MySQLError): logging.error(f"{log_prefix} MySQL error loading user {user_id_str}: {e}", exc_info=True)
            else: logging.error(f"{log_prefix} Error loading user {user_id_str}: {e}", exc_info=True)
            return None

    # Register Blueprints
    from app.main import main_bp
    from app.api.auth import auth_bp
    from app.api.transcriptions import transcriptions_bp
    from app.api.user_settings import user_settings_bp
    from app.api.admin import admin_bp
    from app.admin_panel import admin_panel_bp
    from app.api.workflows import workflows_bp
    from app.api.llm import llm_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(transcriptions_bp)
    app.register_blueprint(user_settings_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_panel_bp)
    app.register_blueprint(workflows_bp)
    app.register_blueprint(llm_bp)
    logging.debug("[SYSTEM] Blueprints registered.")


    # Register Request Hooks
    @app.before_request
    def before_request_func():
        g.user = current_user if current_user.is_authenticated else None
        g.role = g.user.role if g.user else None
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        logging.debug(f"Request started: {request.method} {request.path} from {request.remote_addr} ({user_info})")

        g.initialization_complete = False
        try: g.initialization_complete = check_initialization_marker()
        except Exception as init_check_err: logging.error(f"[SYSTEM] Error checking initialization marker during request: {init_check_err}")

        allowed_endpoints = ['static', 'auth.login', 'auth.register', 'auth.forgot_password', 'auth.reset_password_request', 'auth.google_callback', 'main.set_language']
        if (not g.initialization_complete and
                request.endpoint and
                request.endpoint not in allowed_endpoints and
                not request.endpoint.startswith('static')):
            logging.warning(f"Initialization pending. Blocking request to {request.endpoint}. Returning 503.")
            return jsonify({'error': _('Service temporarily unavailable. Initialization in progress.')}), 503

        if (app.config['DEPLOYMENT_MODE'] == 'multi' and
                not current_user.is_authenticated and
                request.endpoint and
                not request.endpoint.startswith('static') and
                request.endpoint not in allowed_endpoints):
            is_api_request = request.path.startswith('/api/') or \
                             ('Accept' in request.headers and 'application/json' in request.headers['Accept'])
            if is_api_request:
                 logging.warning(f"[AUTH] Unauthorized API access attempt: {request.method} {request.path}")
                 return jsonify({'error': _('Authentication required.')}), 401
            else:
                 logging.debug(f"Redirecting unauthenticated user to login page. Requested endpoint: {request.endpoint}")
                 flash(_("Please log in to access this page."), "info")
                 return redirect(url_for('auth.login', next=request.url))

    @app.after_request
    def after_request_func(response):
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        logging.debug(f"Request finished: {request.method} {request.path} - Status {response.status_code} ({user_info})")
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return response

    # Register Context Processors
    @app.context_processor
    def inject_global_vars():
        user: Optional[User] = current_user if current_user.is_authenticated else None
        role: Optional[Role] = user.role if user else None
        is_multi = app.config['DEPLOYMENT_MODE'] == 'multi'
        initial_key_status = {}
        user_permissions = {}
        supported_languages = app.config.get('SUPPORTED_LANGUAGE_NAMES', {})
        supported_ui_languages = app.config.get('SUPPORTED_LANGUAGES', [])

        all_provider_names_from_config = app.config.get('API_PROVIDER_NAME_MAP', {})
        transcription_provider_codes = app.config.get('TRANSCRIPTION_PROVIDERS', [])

        api_name_map_for_frontend_subset = {
            code: all_provider_names_from_config.get(code, code.replace('_', ' ').replace('-', ' ').title())
            for code in transcription_provider_codes
        }

        color_name_map = {
            "#ffffff": "Default", "#ffd1dc": "Pink", "#aec6cf": "Blue Grey",
            "#cfffd1": "Mint Green", "#fffacd": "Lemon", "#e6e6fa": "Lavender",
            "#ffb347": "Orange"
        }

        if is_multi and user:
            try: initial_key_status = user_service.get_user_api_key_status(user.id)
            except Exception as e: logging.error(f"Error fetching initial key status for user {user.id}: {e}", exc_info=True)
            if role:
                user_permissions = {
                    'use_api_assemblyai': role.use_api_assemblyai,
                    'use_api_openai_whisper': role.use_api_openai_whisper,
                    'use_api_openai_gpt_4o_transcribe': role.use_api_openai_gpt_4o_transcribe,
                    'use_api_google_gemini': role.use_api_google_gemini,
                    'allow_large_files': role.allow_large_files,
                    'allow_context_prompt': role.allow_context_prompt,
                    'allow_download_transcript': role.allow_download_transcript,
                    'allow_api_key_management': role.allow_api_key_management,
                    'access_admin_panel': role.access_admin_panel,
                    'allow_workflows': role.allow_workflows,
                    'manage_workflow_templates': role.manage_workflow_templates,
                    'allow_auto_title_generation': role.allow_auto_title_generation
                }
        elif not is_multi:
             initial_key_status = {
                 'openai': bool(app.config.get('OPENAI_API_KEY')),
                 'assemblyai': bool(app.config.get('ASSEMBLYAI_API_KEY')),
                 'gemini': bool(app.config.get('GEMINI_API_KEY'))
             }
             user_permissions = {
                 'use_api_assemblyai': True, 'use_api_openai_whisper': True,
                 'use_api_openai_gpt_4o_transcribe': True, 'use_api_google_gemini': True,
                 'allow_large_files': True, 'allow_context_prompt': True,
                 'allow_download_transcript': True, 'allow_api_key_management': False,
                 'access_admin_panel': False, 'allow_workflows': True,
                 'manage_workflow_templates': False, 'allow_auto_title_generation': True
             }

        display_name = user.first_name if user and user.first_name else user.username if user else None

        # --- NEW: Get current locale language ---
        locale = get_locale()
        current_language = locale.language if locale else 'en'
        # --- END NEW ---

        return dict(
            deployment_mode=app.config['DEPLOYMENT_MODE'],
            is_multi_user=is_multi,
            current_user=user,
            current_role=role,
            display_name=display_name,
            now=datetime.now(timezone.utc),
            initial_key_status=initial_key_status,
            user_permissions=user_permissions,
            google_client_id=app.config.get('GOOGLE_CLIENT_ID'),
            supported_languages=supported_languages,
            SUPPORTED_UI_LANGS_CONFIG=supported_ui_languages,
            API_NAME_MAP_FRONTEND=api_name_map_for_frontend_subset,
            API_PROVIDER_NAME_MAP=all_provider_names_from_config,
            COLOR_NAME_MAP=color_name_map,
            app_debug=app.debug,
            # --- MODIFIED: Remove babel, add current_language ---
            current_language=current_language
            # --- END MODIFIED ---
        )

    # Register Error Handlers
    @app.errorhandler(404)
    def not_found_error(error):
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        logging.warning(f"404 Not Found: {request.path} (Referer: {request.referrer}) ({user_info})")
        if request.path.startswith('/api/'): return jsonify({'error': _('Not Found')}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        original_exception = getattr(error, "original_exception", error)
        logging.error(f"500 Internal Server Error: {request.path} ({user_info})", exc_info=original_exception)
        try:
            db_conn = getattr(g, 'db_conn', None)
            if db_conn: logging.info("[DB:Error] Attempting rollback due to 500 error."); db_conn.rollback(); logging.info("[DB:Error] Rollback successful.")
        except MySQLError as db_err: logging.error(f"[DB:Error] MySQL error during rollback in 500 handler: {db_err}")
        except Exception as db_err: logging.error(f"[DB:Error] Non-MySQL error during rollback in 500 handler: {db_err}")
        if request.path.startswith('/api/'): return jsonify({'error': _('Internal Server Error')}), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        logging.warning(f"403 Forbidden: {request.path} ({user_info}). Reason: {error.description}")
        if request.path.startswith('/api/'): return jsonify({'error': _('Forbidden'), 'message': error.description}), 403
        flash(error.description or _("You do not have permission to access this page."), "danger")
        return render_template('errors/403.html'), 403

    @app.errorhandler(401)
    def unauthorized_error(error):
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        logging.warning(f"401 Unauthorized: {request.path} ({user_info}). Reason: {error.description}")
        if request.path.startswith('/api/'): return jsonify({'error': _('Unauthorized'), 'message': error.description or _('Authentication required.')}), 401
        else: flash(error.description or _("Authentication required to access this page."), "warning"); return redirect(url_for('auth.login', next=request.url))

    @app.errorhandler(429)
    def ratelimit_handler(e):
        g.user = current_user if current_user.is_authenticated else None
        logging.warning(f"Rate limit exceeded: {e.description} for {request.remote_addr} at {request.path}")
        if request.path.startswith('/api/'):
            return jsonify(error=f"Rate limit exceeded: {e.description}"), 429
        else:
            flash(_("Too many requests: %(description)s. Please try again later.", description=e.description), "warning")
            referrer = request.referrer; target_url = url_for('main.index')
            try:
                if referrer and urlparse(referrer).netloc == urlparse(request.url_root).netloc: target_url = referrer
            except Exception: pass
            return redirect(target_url)

    @app.errorhandler(413)
    def payload_too_large_error(error):
        user_info = f"User:{current_user.id}" if current_user.is_authenticated else "Anonymous"
        logging.warning(f"413 Payload Too Large: {request.path} ({user_info}). Request content length: {request.content_length}")
        # All file uploads go to API endpoints, so we can assume JSON response is desired.
        max_size_bytes = current_app.config.get('MAX_CONTENT_LENGTH', 0)
        max_size_mb = round(max_size_bytes / (1024*1024))
        error_message = _('File is too large. The maximum allowed file size is %(size)sMB.', size=max_size_mb)
        return jsonify({'error': error_message, 'code': 'SIZE_LIMIT_EXCEEDED'}), 413


    # Initialize Resources & Start Background Tasks
    initialize_app_resources(app)

    # --- MODIFIED: REMOVED old locale selector definition ---

    logging.info("[SYSTEM] Application initialization complete.")
    return app