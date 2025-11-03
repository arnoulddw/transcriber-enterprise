# app/services/api_clients/transcription/openai_gpt_4o_diarize_transcribe.py
# Client for interacting with the OpenAI GPT-4o transcription model.

from typing import Tuple, Optional, Dict, Any, List

try:
    from openai.resources.audio import transcriptions as _openai_audio_transcriptions
    from openai.types.audio.transcription_verbose import TranscriptionVerbose as _OpenAITranscriptionVerbose
except ImportError:  # Fallback for older SDK versions that may not expose these helpers.
    _openai_audio_transcriptions = None
    _OpenAITranscriptionVerbose = None

# Shared OpenAI behaviours
from .openai_base import OpenAIBaseTranscriptionClient
from app.config import Config # To access language codes
from app.services.api_clients.exceptions import TranscriptionProcessingError

# Extend the OpenAI SDK response format handling so diarized_json responses do not trigger warnings.
if _openai_audio_transcriptions and _OpenAITranscriptionVerbose:
    _existing_get_response_format_type = getattr(_openai_audio_transcriptions, "_get_response_format_type", None)
    if callable(_existing_get_response_format_type) and not getattr(_existing_get_response_format_type, "_diarized_json_supported", False):
        def _get_response_format_type_with_diarized(response_format: str):
            if response_format == "diarized_json":
                return _OpenAITranscriptionVerbose
            return _existing_get_response_format_type(response_format)

        _get_response_format_type_with_diarized._diarized_json_supported = True
        _openai_audio_transcriptions._get_response_format_type = _get_response_format_type_with_diarized


class OpenAIGPT4ODiarizeTranscribeClient(OpenAIBaseTranscriptionClient):
    """
    Handles transcription requests using the OpenAI gpt-4o-transcribe-diarize model.
    This model supports speaker diarization.
    """
    API_MODEL_PARAM = "gpt-4o-transcribe-diarize"

    def __init__(self, api_key: str, config: Dict[str, Any]) -> None:
        """Initializes the client and sets API-specific limits from config."""
        api_limits = config.get('API_LIMITS', {}).get('gpt-4o-transcribe-diarize', {}) or {}
        self.openai_client_max_retries: Optional[int] = api_limits.get('openai_client_max_retries')
        self.single_file_max_retries_override: Optional[int] = api_limits.get('single_file_max_retries')
        self.chunk_max_retries_override: Optional[int] = api_limits.get('chunk_max_retries')
        self.single_file_retry_delays: List[float] = [float(d) for d in api_limits.get('single_file_retry_delays', [])]
        self.chunk_retry_delays: List[float] = [float(d) for d in api_limits.get('chunk_retry_delays', [])]

        super().__init__(api_key, config)

        api_limits = self.config.get('API_LIMITS', {}).get('gpt-4o-transcribe-diarize', {}) or {}
        # This model requires chunking for files > 30s, which is handled by the base client's splitting logic.
        # We set the threshold here, which the base client will use.
        self.SPLIT_THRESHOLD_SECONDS = api_limits.get('duration_s', 240) # Default to 4 minutes if not set
        size_mb = api_limits.get('size_mb')
        if size_mb is not None:
            self.SPLIT_THRESHOLD_BYTES = size_mb * 1024 * 1024
        self.logger.debug(
            "Limits set - Duration: %ss, Size: %sMB, Single file retries: %s, Chunk retries: %s",
            self.SPLIT_THRESHOLD_SECONDS,
            size_mb,
            self.single_file_max_retries_override,
            self.chunk_max_retries_override
        )

    # --- Implementation of Abstract Methods ---

    def _get_api_name(self) -> str:
        return "OpenAI GPT-4o Diarize Transcribe"

    def _get_timeout_config_override_key(self) -> Optional[str]:
        return 'OPENAI_HTTP_TIMEOUT_DIARIZE'

    def _get_additional_openai_client_kwargs(self) -> Dict[str, Any]:
        if self.openai_client_max_retries is None:
            return {}
        return {'max_retries': int(self.openai_client_max_retries)}

    def _prepare_api_params(self, language_code: str, context_prompt: str, response_format: str, is_chunk: bool) -> Dict[str, Any]:
        """Prepare the dictionary of parameters for the OpenAI transcriptions API call."""
        api_params: Dict[str, Any] = {
            "model": self.API_MODEL_PARAM,
            "prompt": context_prompt,
            "response_format": "diarized_json",
            "chunking_strategy": "auto"  # Required for diarization
        }
        
        log_lang_param_desc = ""
        ui_lang_msg = ""

        if language_code and language_code != 'auto':
            if language_code in Config.SUPPORTED_LANGUAGE_CODES:
                api_params["language"] = language_code
                log_lang_param_desc = f"'{language_code}'"
                ui_lang_msg = f"Language set to '{language_code}'."
            else:
                self.logger.warning(f"Invalid language code '{language_code}'. Ignoring and using auto-detection.")
                ui_lang_msg = f"Invalid language code '{language_code}'. Using auto-detection."
                log_lang_param_desc = "'auto' (fallback detection)"
        else:
            log_lang_param_desc = "'auto' (detection requested)"
            ui_lang_msg = "Language detection requested."

        if not is_chunk:
            if ui_lang_msg:
                self._report_progress(ui_lang_msg, False)

        self.logger.debug(f"Prepared API params (Lang: {log_lang_param_desc}): { {k:v for k,v in api_params.items() if k != 'prompt'} }")
        return api_params

    def _process_response(self, response: Any, response_format: str) -> Tuple[str, Optional[str]]:
        """
        Parse the OpenAI API response, which is expected to be in 'diarized_json' format.
        Raises:
            TranscriptionProcessingError: If the response cannot be parsed.
        """
        transcription_text: str = ""
        detected_language: Optional[str] = None # Diarized response does not provide a language field

        try:
            if not hasattr(response, 'segments') or not isinstance(response.segments, list):
                self.logger.error(f"API response is missing 'segments' list. Response: {response}")
                raise TranscriptionProcessingError("Response is missing 'segments' array.", provider=self._get_api_name())

            # --- END DIAGNOSTICS ---

            formatted_segments = []
            for segment in response.segments:
                speaker = "Unknown"
                text = ""
                
                # Robustly get speaker and text, whether segment is a dict or an object
                if isinstance(segment, dict):
                    speaker = segment.get('speaker') or "Unknown"
                    text = segment.get('text', '')
                else:
                    speaker = getattr(segment, 'speaker', "Unknown") or "Unknown"
                    text = getattr(segment, 'text', '')
                
                formatted_segments.append(f"{speaker}: {text.strip()}")
            
            transcription_text = "\n".join(formatted_segments)
            self.logger.debug(f"Successfully processed {len(response.segments)} diarized segments.")

        except (AttributeError, TypeError) as e:
            self.logger.error(f"Failed to parse API response object (format: {response_format}): {e}. Response: {response}", exc_info=True)
            raise TranscriptionProcessingError(f"Failed to parse OpenAI diarized response (format: {response_format}).", provider=self._get_api_name()) from e
        except Exception as e:
            self.logger.error(f"Unexpected error processing API response: {e}", exc_info=True)
            raise TranscriptionProcessingError(f"Unexpected error processing OpenAI diarized response: {e}", provider=self._get_api_name()) from e

        # The diarized response does not include a top-level language detection field.
        # The language is implicitly detected but not returned.
        return transcription_text, None
