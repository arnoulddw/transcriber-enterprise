"""
User domain package.

This package splits the former `app.models.user` module into cohesive units:
- `model` keeps the `User` entity and mapping helpers.
- `schema` contains database-initialization helpers.
- `repository` holds persistence logic and user-related DB utilities.

The public API remains backward-compatible by re-exporting previous symbols.
"""

from .model import User, _map_row_to_user
from .schema import init_db_command
from .repository import (
    _get_default_transcription_model_for_new_user,
    add_user,
    add_oauth_user,
    get_user_by_username,
    get_user_by_email,
    get_user_by_id,
    get_user_by_oauth,
    get_user_by_public_api_key_hash,
    link_oauth_to_user,
    update_user_api_keys,
    update_public_api_key,
    clear_public_api_key,
    get_all_users,
    delete_user_by_id,
    update_user_password_hash,
    update_user_role,
    update_user_profile,
    update_user_preferences,
    count_users_by_role_id,
)

__all__ = [
    "User",
    "_map_row_to_user",
    "init_db_command",
    "_get_default_transcription_model_for_new_user",
    "add_user",
    "add_oauth_user",
    "get_user_by_username",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_by_oauth",
    "get_user_by_public_api_key_hash",
    "link_oauth_to_user",
    "update_user_api_keys",
    "update_public_api_key",
    "clear_public_api_key",
    "get_all_users",
    "delete_user_by_id",
    "update_user_password_hash",
    "update_user_role",
    "update_user_profile",
    "update_user_preferences",
    "count_users_by_role_id",
]
