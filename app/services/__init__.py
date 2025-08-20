# app/services/__init__.py
# This file makes the 'services' directory a Python package.

# You can optionally import services here for convenience,
# but be mindful of potential circular dependencies if services call each other.
# Example:
# from .auth_service import create_user, verify_password
# from .transcription_service import process_transcription
# from .user_service import get_decrypted_api_key, save_user_api_key
# from .admin_service import list_all_users
# from .file_service import allowed_file, split_audio_file
# from .security_service import get_security_service

# It's often safer to import directly where needed, e.g.,
# `from app.services import auth_service`
# or `from app.services.auth_service import verify_password`