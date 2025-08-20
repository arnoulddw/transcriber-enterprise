# app/services/api_clients/transcription/openai_gpt_4o_transcribe.py
# Client for interacting with the OpenAI GPT-4o transcription model.

from app.logging_config import get_logger
from typing import Tuple, Optional, Dict, Any, Type

# Import OpenAI library and specific errors
from openai import OpenAI, OpenAIError, APIError, APIConnectionError, RateLimitError, AuthenticationError, BadRequestError

# Import Base Class and project config/exceptions
from .base_transcription_client import BaseTranscriptionClient
from app.config import Config # To access language codes
from app.services.api_clients.exceptions import (
    TranscriptionApiError,
    TranscriptionConfigurationError,
    TranscriptionProcessingError,
    TranscriptionAuthenticationError,
    TranscriptionRateLimitError,
    TranscriptionQuotaExceededError
)

class OpenAIGPT4OTranscribeClient(BaseTranscriptionClient):
    """
    Handles transcription requests using the OpenAI GPT-4o model via the transcriptions endpoint.
    Inherits common workflow from BaseTranscriptionClient.
    """
    API_MODEL_PARAM = "gpt-4o-transcribe"

    def __init__(self, api_key: str, config: Dict[str, Any]) -> None:
        """Initializes the client and sets API-specific limits from config."""
        super().__init__(api_key, config)
        api_limits = self.config.get('API_LIMITS', {}).get('gpt-4o-transcribe', {})
        self.SPLIT_THRESHOLD_SECONDS = api_limits.get('duration_s')
        size_mb = api_limits.get('size_mb')
        if size_mb is not None:
            self.SPLIT_THRESHOLD_BYTES = size_mb * 1024 * 1024
        self.logger.debug(f"Limits set - Duration: {self.SPLIT_THRESHOLD_SECONDS}s, Size: {size_mb}MB")

    # --- Implementation of Abstract Methods ---

    def _get_api_name(self) -> str:
        return "OpenAI GPT-4o Transcribe"

    def _initialize_client(self, api_key: str) -> None:
        """Initializes the OpenAI API client."""
        try:
            self.client = OpenAI(api_key=api_key)
            self.logger.debug(f"Client initialized successfully (using model param '{self.API_MODEL_PARAM}').")
        except OpenAIError as e:
            raise ValueError(f"OpenAI client initialization failed: {e}") from e

    def _prepare_api_params(self, language_code: str, context_prompt: str, response_format: str, is_chunk: bool) -> Dict[str, Any]:
        """Prepare the dictionary of parameters for the OpenAI transcriptions API call."""
        api_params: Dict[str, Any] = {
            "model": self.API_MODEL_PARAM,
            "prompt": context_prompt
        }
        log_lang_param_desc = ""
        ui_lang_msg = ""

        if language_code == 'auto':
            api_params["response_format"] = "json"
            log_lang_param_desc = "'auto' (detection requested, format: json)"
            ui_lang_msg = "Language detection requested."
        elif language_code in Config.SUPPORTED_LANGUAGE_CODES:
            api_params["language"] = language_code
            api_params["response_format"] = "text"
            log_lang_param_desc = f"'{language_code}'"
            ui_lang_msg = f"Language set to '{language_code}'."
        else:
            self.logger.warning(f"Invalid language code '{language_code}'. Using auto-detection as fallback.")
            ui_lang_msg = f"Invalid language code '{language_code}'. Using auto-detection as fallback."
            api_params["response_format"] = "json"
            log_lang_param_desc = "'auto' (fallback detection, format: json)"
            language_code = 'auto'

        if not is_chunk or (is_chunk and language_code == 'auto'):
             if ui_lang_msg: self._report_progress(ui_lang_msg, False)

        self.logger.debug(f"Prepared API params (Lang: {log_lang_param_desc}): { {k:v for k,v in api_params.items() if k != 'prompt'} }")
        return api_params

    def _call_api(self, file_handle: Any, api_params: Dict[str, Any]) -> Any:
        """
        Make the actual transcription API call using the OpenAI client.
        Raises:
            TranscriptionAuthenticationError, TranscriptionRateLimitError, TranscriptionQuotaExceededError,
            TranscriptionProcessingError, Exception.
        """
        api_params_with_file = api_params.copy()
        api_params_with_file["file"] = file_handle
        try:
            transcript_response = self.client.audio.transcriptions.create(**api_params_with_file)
            return transcript_response
        except AuthenticationError as e:
            self.logger.error(f"Authentication error: {e}")
            raise TranscriptionAuthenticationError(f"OpenAI: {e}", provider=self._get_api_name()) from e
        except RateLimitError as e:
            error_body = getattr(e, 'body', {})
            error_type = error_body.get('type') if isinstance(error_body, dict) else None
            if error_type == 'insufficient_quota':
                self.logger.error(f"Insufficient Quota error: {e}")
                raise TranscriptionQuotaExceededError(f"OpenAI: {e}", provider=self._get_api_name()) from e
            else:
                self.logger.warning(f"Rate limit error: {e}")
                raise TranscriptionRateLimitError(f"OpenAI: {e}", provider=self._get_api_name()) from e
        except BadRequestError as e:
            error_body_str = str(e)
            self.logger.error(f"API call failed with Bad Request: {error_body_str}")
            # Check if the error is a generic HTML response, which can happen for invalid chunks
            if error_body_str.strip().startswith("<html>"):
                msg = "The API rejected an audio chunk as invalid (it may be silent or corrupted)."
                raise TranscriptionProcessingError(msg, provider=self._get_api_name()) from e
            else:
                raise TranscriptionProcessingError(f"OpenAI API Error: {error_body_str}", provider=self._get_api_name()) from e
        except (APIConnectionError, APIError, OpenAIError) as e:
            self.logger.error(f"API call failed: {e}")
            raise TranscriptionProcessingError(f"OpenAI API Error: {e}", provider=self._get_api_name()) from e
        except Exception as e:
            self.logger.error(f"Unexpected error during API call: {e}", exc_info=True)
            raise TranscriptionProcessingError(f"Unexpected error during OpenAI API call: {e}", provider=self._get_api_name()) from e

    def _process_response(self, response: Any, response_format: str) -> Tuple[str, Optional[str]]:
        """
        Parse the OpenAI API response.
        Raises:
            TranscriptionProcessingError: If the response cannot be parsed.
        """
        transcription_text: str = ""
        detected_language: Optional[str] = None

        try:
            if response_format == "json":
                transcription_text = response.text
                self.logger.debug("Received 'json' response format (language not specified by API).")
            elif response_format == "text":
                transcription_text = response if isinstance(response, str) else str(response)
            else:
                self.logger.warning(f"Unexpected response format '{response_format}'. Attempting string conversion.")
                transcription_text = str(response)
        except AttributeError as e:
             self.logger.error(f"Failed to parse API response object (format: {response_format}): {e}. Response: {response}", exc_info=True)
             raise TranscriptionProcessingError(f"Failed to parse OpenAI response (format: {response_format}).", provider=self._get_api_name()) from e
        except Exception as e:
             self.logger.error(f"Unexpected error processing API response: {e}", exc_info=True)
             raise TranscriptionProcessingError(f"Unexpected error processing OpenAI response: {e}", provider=self._get_api_name()) from e

        return transcription_text, None

    def _get_retryable_errors(self) -> Tuple[Type[Exception], ...]:
        """Return OpenAI-specific retryable errors."""
        return (TranscriptionRateLimitError, APIConnectionError)