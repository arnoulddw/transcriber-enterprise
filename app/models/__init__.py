# app/models/__init__.py
# This file makes the 'models' directory a Python package.

# You can optionally import models here for easier access elsewhere,
# but be cautious of circular imports if models depend on each other.
# Example (use with care):
# from .user import User
# from .role import Role
# from .transcription import Transcription
# --- ADDED: Import LLMOperation ---
# from .llm_operation import LLMOperation
# --- END ADDED ---

# It's often safer to import directly where needed, e.g., `from app.models.user import User`.

# Define a base model class if common functionality is identified later (e.g., common fields like id, created_at)
# class BaseModel:
#     pass

# You could also define common database initialization logic here,
# although it's currently handled in the respective model files and coordinated by app/cli.py.