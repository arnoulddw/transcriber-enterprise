# app/main/__init__.py
# This file makes the 'main' directory a Python package and defines the main Blueprint.

from flask import Blueprint

# Define the main blueprint.
# 'main' is the name used for url_for('main.index')
# __name__ helps Flask locate the blueprint's resources (like templates if they were here)
# template_folder='../templates' could be used if templates were specific to this blueprint,
# but we are using the global app/templates directory.
main_bp = Blueprint('main', __name__)

# Import the routes associated with this blueprint.
# This import is placed at the end to avoid circular dependencies,
# as routes.py might need to import 'main_bp'.
from . import routes