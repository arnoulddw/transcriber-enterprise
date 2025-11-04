# app/extensions.py
# Instantiation of Flask extensions.

from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail # <<< ADDED
from flask_babel import Babel

# Custom Babel class to force American-style number formatting

# Bcrypt for password hashing
bcrypt = Bcrypt()

# LoginManager for handling user sessions
login_manager = LoginManager()
# Configure login view and messages (can also be done in __init__.py during init_app)
login_manager.login_view = 'auth.login' # Blueprint name 'auth', route name 'login'
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info" # Flash message category

# CSRFProtect for Cross-Site Request Forgery protection
csrf = CSRFProtect()

# Limiter for rate limiting requests
# The key function determines how users are identified for rate limiting (e.g., by IP)
# Default limits and storage URI will be configured in __init__.py using app.config
limiter = Limiter(
    key_func=get_remote_address,
    # storage_uri will be set during init_app
    # default_limits will be set during init_app
    strategy="fixed-window" # Strategy for rate limiting window
)

# Mail for sending emails (e.g., password recovery) # <<< ADDED
mail = Mail()

# If using Flask-SQLAlchemy in the future, it would be instantiated here:
# from flask_sqlalchemy import SQLAlchemy
# db = SQLAlchemy()

# If using Flask-Migrate in the future:
# from flask_migrate import Migrate
# migrate = Migrate()

# Babel for internationalization (i18n)
babel = Babel()
