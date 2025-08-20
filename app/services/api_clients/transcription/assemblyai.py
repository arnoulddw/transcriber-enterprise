# app/services/api_clients/transcription/assemblyai.py
# Client for interacting with the AssemblyAI transcription API.

import logging
import os
from typing import Tuple, Optional, Dict, Any, Type

import assemblyai as aai # Official AssemblyAI SDK
from assemblyai.types import TranscriptError, TranscriptStatus, LanguageCode

# Import Base Class and project config/exceptions
from .base_transcription_client import BaseTranscriptionClient
from app.config import Config # To access language codes
from app.services.api_clients.exceptions import (
    TranscriptionApiError,
    TranscriptionConfigurationError,
    TranscriptionProcessingError,
    TranscriptionAuthenticationError # AssemblyAI SDK might raise TranscriptError for auth issues too
)

class AssemblyAITranscriptionAPI(BaseTranscriptionClient):
    """
    Handles transcription requests using the AssemblyAI API.
    Inherits common workflow from BaseTranscriptionClient.
    Note: AssemblyAI SDK handles chunking internally for large files via transcribe(),
          so the base class splitting logic might not be strictly necessary if only using this.
          The base class's `transcribe` will call this class's `_call_api` directly.
    """
    # AssemblyAI handles concurrency internally, so we set this to 1.
    # The base class will still use this value if its _split_and_transcribe is called,
    # but for AssemblyAI, it's more of a formality as the SDK manages it.
    # We override the max_concurrent_chunks in the __init__ for this client.

    def __init__(self, api_key: str, config: Dict[str, Any]) -> None:
        """Initializes the client and sets API-specific limits from config."""
        super().__init__(api_key, config)
        # Override max_concurrent_chunks for AssemblyAI as it handles this internally
        self.max_concurrent_chunks = 1
        logging.info(f"[{self._get_api_name()}] Max concurrent chunks set to 1 (handled by SDK).")

        api_limits = self.config.get('API_LIMITS', {}).get('assemblyai', {})
        self.SPLIT_THRESHOLD_SECONDS = api_limits.get('duration_s')
        size_mb = api_limits.get('size_mb')
        if size_mb is not None:
            self.SPLIT_THRESHOLD_BYTES = size_mb * 1024 * 1024
        else:
            # AssemblyAI has no hard size limit, so we can set it very high
            # to prevent the base client from splitting based on size.
            self.SPLIT_THRESHOLD_BYTES = 1024 * 1024 * 1024 # 1 GB
        logging.info(f"[{self._get_api_name()}] Limits set - Duration: {self.SPLIT_THRESHOLD_SECONDS}s, Size: {size_mb}MB")


    # --- Implementation of Abstract Methods ---

    def _get_api_name(self) -> str:
        return "AssemblyAI"

    def _initialize_client(self, api_key: str) -> None:
        """Configures the AssemblyAI SDK."""
        try:
            # Configure the AssemblyAI SDK globally with the provided key
            aai.settings.api_key = self.api_key
            # Store an instance for consistency, though SDK often uses global settings
            self.client = aai.Transcriber()
            logging.info(f"[{self._get_api_name()}] Client initialized and SDK configured.")
        except Exception as e:
            # Let the Base Class __init__ handle raising TranscriptionConfigurationError
            raise ValueError(f"AssemblyAI SDK configuration failed: {e}") from e

    def _prepare_api_params(self, language_code: str, context_prompt: str, response_format: str, is_chunk: bool) -> Dict[str, Any]:
        """Prepare the TranscriptionConfig parameters for AssemblyAI."""
        config_params = {}
        log_lang_param_desc = ""
        ui_lang_msg = ""

        if context_prompt:
             logging.warning(f"[{self._get_api_name()}] Context prompt provided but not directly used by AssemblyAI standard transcription.")
             # Could potentially use word_boost here if needed in the future

        if language_code == 'auto':
            config_params['language_detection'] = True
            log_lang_param_desc = "'auto' (detection requested)"
            ui_lang_msg = "Language detection enabled."
        elif language_code in Config.SUPPORTED_LANGUAGE_CODES:
            try:
                config_params['language_code'] = LanguageCode(language_code) # Use SDK enum
                log_lang_param_desc = f"'{language_code}'"
                ui_lang_msg = f"Language set to '{language_code}'."
            except ValueError:
                 logging.warning(f"[{self._get_api_name()}] Language code '{language_code}' not recognized by AssemblyAI SDK enum. Falling back to auto-detection.")
                 ui_lang_msg = f"Language code '{language_code}' not recognized by AssemblyAI SDK. Using auto-detection."
                 config_params['language_detection'] = True
                 log_lang_param_desc = "'auto' (fallback detection)"
                 language_code = 'auto' # Update effective code
        else:
            logging.warning(f"[{self._get_api_name()}] Invalid language code '{language_code}'. Using auto-detection as fallback.")
            ui_lang_msg = f"Invalid language code '{language_code}'. Using auto-detection as fallback."
            config_params['language_detection'] = True
            log_lang_param_desc = "'auto' (fallback detection)"
            language_code = 'auto' # Update effective code

        # Report language choice progress only once per file/chunk set
        if not is_chunk: # AssemblyAI handles splitting internally, only report once
             if ui_lang_msg: self._report_progress(ui_lang_msg, False)

        logging.debug(f"[{self._get_api_name()}] Prepared API config params (Lang: {log_lang_param_desc}): {config_params}")
        # Return the config params, which will be used to create TranscriptionConfig in _call_api
        return config_params

    def _call_api(self, file_handle: Any, api_params: Dict[str, Any]) -> Any:
        """
        Submits the transcription job using the AssemblyAI SDK.
        The SDK handles uploading the file from the handle's path.
        Args:
            file_handle: The opened file handle (used to get the file path).
            api_params: Dictionary containing parameters for TranscriptionConfig.
        Raises:
            TranscriptionAuthenticationError: If authentication fails.
            TranscriptionProcessingError: For other API call errors.
            FileNotFoundError: If the file path is invalid.
            Exception: For unexpected errors.
        """
        try:
            file_path = file_handle.name
            if not file_path or not os.path.exists(file_path):
                 raise FileNotFoundError(f"File path not available or file does not exist: {file_path}")

            config_obj = aai.TranscriptionConfig(**api_params)
            transcriber = aai.Transcriber(config=config_obj)

            self._report_progress(f"Uploading and processing audio with {self._get_api_name()}...")
            transcript = transcriber.transcribe(file_path) # This blocks until completion or error
            logging.info(f"[{self._get_api_name()}] API request finished. Transcript status: {transcript.status}")
            return transcript # Return the completed Transcript object

        except TranscriptError as aai_error:
            error_msg = str(aai_error)
            logging.error(f"[{self._get_api_name()}] AssemblyAI API Error: {error_msg}", exc_info=True)
            # Attempt to map AssemblyAI errors to our custom exceptions
            if "authorization" in error_msg.lower() or "authentication" in error_msg.lower():
                raise TranscriptionAuthenticationError(f"AssemblyAI: {error_msg}", provider=self._get_api_name()) from aai_error
            # Add more specific error mappings if needed (e.g., for rate limits if identifiable)
            else:
                raise TranscriptionProcessingError(f"AssemblyAI: {error_msg}", provider=self._get_api_name()) from aai_error
        except FileNotFoundError as fnf:
             logging.error(f"[{self._get_api_name()}] File not found during API call: {fnf}", exc_info=True)
             raise fnf # Re-raise FileNotFoundError
        except Exception as e:
            logging.error(f"[{self._get_api_name()}] Unexpected error during API call: {e}", exc_info=True)
            # Wrap unexpected errors in our custom exception
            raise TranscriptionProcessingError(f"Unexpected error during AssemblyAI API call: {e}", provider=self._get_api_name()) from e

    def _process_response(self, response: Any, response_format: str) -> Tuple[str, Optional[str]]:
        """
        Parse the AssemblyAI Transcript object.
        Raises:
            TranscriptionProcessingError: If the transcript status is 'error'.
        """
        transcript: aai.Transcript = response
        transcription_text: Optional[str] = None
        detected_language: Optional[str] = None

        if transcript.status == TranscriptStatus.error:
            error_detail = transcript.error or "Unknown AssemblyAI error"
            raise TranscriptionProcessingError(f"AssemblyAI transcription failed: {error_detail}", provider=self._get_api_name())

        if transcript.status != TranscriptStatus.completed:
            raise TranscriptionProcessingError(f"AssemblyAI transcription finished with unexpected status: {transcript.status}", provider=self._get_api_name())

        transcription_text = transcript.text
        detected_lang_val = getattr(transcript, 'language_code', None)
        if detected_lang_val:
            detected_language = str(detected_lang_val)
            logging.info(f"[{self._get_api_name()}] Detected language: {detected_language}")
        else:
             logging.info(f"[{self._get_api_name()}] Language code not found in transcript response.")

        return transcription_text or "", detected_language

    def _get_retryable_errors(self) -> Tuple[Type[Exception], ...]:
        """Return AssemblyAI-specific retryable errors (if any identified)."""
        # AssemblyAI SDK handles many retries internally.
        # We might add specific TranscriptError cases here if needed, but start with none.
        return ()