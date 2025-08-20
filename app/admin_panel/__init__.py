# app/admin_panel/__init__.py
# Defines the Blueprint for the new admin panel section.

from flask import Blueprint

# Define the admin panel blueprint
# 'admin_panel' is the name used for url_for() calls (e.g., url_for('admin_panel.dashboard'))
# __name__ helps Flask locate the blueprint's resources
# url_prefix='/admin' sets the base URL for all routes in this blueprint
admin_panel_bp = Blueprint(
    'admin_panel',
    __name__,
    template_folder='../templates/admin', # Point to the admin templates directory
    url_prefix='/admin'
)

# Import the routes associated with this blueprint
# This import is placed at the end to avoid circular dependencies
from . import routes