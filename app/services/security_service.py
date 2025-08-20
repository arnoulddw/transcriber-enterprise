# app/services/security_service.py
# Provides encryption and decryption services, typically for sensitive data like API keys.
# (No changes needed for MySQL migration)

import logging
import base64
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app # To access SECRET_KEY from config

# --- Constants ---
DEFAULT_SALT = b'_tRaNsCrIbEr_sEcUrItY_sAlT_'
KDF_ITERATIONS = 480000

class SecurityService:
    """
    Handles symmetric encryption and decryption using Fernet.
    Derives a stable encryption key from the Flask application's SECRET_KEY.
    """

    def __init__(self, secret_key: str, salt: bytes = DEFAULT_SALT):
        """
        Initializes the SecurityService.

        Args:
            secret_key: The Flask application's SECRET_KEY.
            salt: A salt value used for key derivation. Must remain constant.

        Raises:
            ValueError: If secret_key is empty or salt is invalid.
        """
        if not secret_key:
            raise ValueError("SecurityService requires a non-empty secret_key.")
        if not salt or len(salt) < 16:
            logging.warning("SecurityService salt is short or missing. Using default. Ensure consistency!")
            salt = DEFAULT_SALT

        self.salt = salt
        try:
            self.key = self._derive_key(secret_key.encode('utf-8'), self.salt)
            self.fernet = Fernet(self.key)
            logging.debug("[SERVICE:Security] SecurityService initialized successfully.")
        except Exception as e:
             logging.critical(f"[SERVICE:Security] Failed to initialize Fernet: {e}", exc_info=True)
             raise ValueError("Failed to initialize encryption service.") from e

    def _derive_key(self, password: bytes, salt: bytes) -> bytes:
        """
        Derives a 32-byte key suitable for Fernet using PBKDF2HMAC-SHA256.
        """
        logging.debug("[SERVICE:Security] Deriving encryption key...")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=KDF_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        logging.debug("[SERVICE:Security] Encryption key derived.")
        return key

    def encrypt_data(self, data: str) -> str:
        """
        Encrypts a string using Fernet.

        Args:
            data: The plaintext string to encrypt.

        Returns:
            A URL-safe base64 encoded encrypted string.

        Raises:
            TypeError: If input data is not a string.
            ValueError: If encryption fails.
        """
        if not isinstance(data, str):
            raise TypeError("Data to encrypt must be a string.")
        try:
            encrypted_bytes = self.fernet.encrypt(data.encode('utf-8'))
            logging.debug("[SERVICE:Security] Data encrypted successfully.")
            return encrypted_bytes.decode('utf-8')
        except Exception as e:
            logging.error(f"[SERVICE:Security] Failed to encrypt data: {e}", exc_info=True)
            raise ValueError("Encryption failed.") from e

    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decrypts a Fernet token (URL-safe base64 encoded string).

        Args:
            encrypted_data: The encrypted string token.

        Returns:
            The original plaintext string.

        Raises:
            InvalidToken: If the token is invalid, tampered with, or decryption fails (e.g., wrong key).
            TypeError: If input data is not a string.
            ValueError: For other unexpected decryption errors.
        """
        if not isinstance(encrypted_data, str):
            logging.warning(f"[SERVICE:Security] Invalid type passed for decryption: {type(encrypted_data)}. Expected string.")
            raise InvalidToken("Invalid encrypted data format.")
        try:
            decrypted_bytes = self.fernet.decrypt(encrypted_data.encode('utf-8'))
            logging.debug("[SERVICE:Security] Data decrypted successfully.")
            return decrypted_bytes.decode('utf-8')
        except InvalidToken:
            logging.error("[SERVICE:Security] Failed to decrypt data: Invalid token (likely wrong key, tampered data, or expired TTL if used).")
            raise
        except Exception as e:
            logging.error(f"[SERVICE:Security] Unexpected error during decryption: {e}", exc_info=True)
            raise ValueError("Decryption failed due to an unexpected error.") from e

# --- Singleton Instance Management ---
_security_service_instance: Optional[SecurityService] = None

def get_security_service() -> SecurityService:
    """
    Provides a singleton instance of the SecurityService.
    Initializes the service on first call using the app's SECRET_KEY.
    Requires an active Flask application context.

    Returns:
        The singleton SecurityService instance.

    Raises:
        RuntimeError: If called outside of an active Flask application context.
        ValueError: If SECRET_KEY is not configured or initialization fails.
    """
    global _security_service_instance
    if _security_service_instance is None:
        try:
            secret = current_app.config.get('SECRET_KEY')
            if not secret:
                logging.critical("[SYSTEM] SECRET_KEY is not configured. Cannot initialize SecurityService.")
                raise ValueError("SECRET_KEY is required for SecurityService but is not configured.")
            _security_service_instance = SecurityService(secret)
        except RuntimeError as e:
            logging.critical(f"[SYSTEM] Failed to get SecurityService: {e}. Ensure Flask app context is active.")
            raise RuntimeError("Cannot initialize SecurityService outside of Flask application context.") from e
        except ValueError as e:
             logging.critical(f"[SYSTEM] Failed to initialize SecurityService: {e}")
             raise e
        except Exception as e:
             logging.critical(f"[SYSTEM] Unexpected error initializing SecurityService: {e}", exc_info=True)
             raise ValueError("Unexpected error initializing SecurityService.") from e
    return _security_service_instance