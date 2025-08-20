# app/services/api_clients/transcription/base_transcription_client.py
# Defines the Abstract Base Class for transcription API clients.

import os
import logging
from app.logging_config import get_logger
import time
import concurrent.futures
import threading
from abc import ABC, abstractmethod
from typing import Tuple, Optional, Callable, Dict, List, Any, Type

# Import project-specific services and config
from app.services import file_service
from app.config import Config # To access language codes if needed
from app.services.api_clients.exceptions import (
    TranscriptionApiError,
    TranscriptionConfigurationError,
    TranscriptionProcessingError,
    TranscriptionAuthenticationError,
    TranscriptionRateLimitError
)

# Define type hint for the progress callback function
ProgressCallback = Optional[Callable[[str, bool], None]] # Args: message, is_error

class BaseTranscriptionClient(ABC):
    """
    Abstract Base Class for transcription API clients.
    Handles the common workflow: file size checks, splitting,
    parallel/sequential processing, retries, progress reporting,
    cancellation checks, and cleanup.
    """
    # Default file size threshold for splitting (can be overridden if needed)
    SPLIT_THRESHOLD_BYTES: int = 25 * 1024 * 1024 # Default 25MB
    # NEW: Add duration threshold, can be overridden by subclasses
    SPLIT_THRESHOLD_SECONDS: Optional[int] = None

    def __init__(self, api_key: str, config: Dict[str, Any]) -> None:
        """
        Initializes the base client and calls the subclass's initializer.

        Args:
            api_key: The API key for the specific service.
            config: The Flask application configuration dictionary.

        Raises:
            ValueError: If the API key is not provided.
            TranscriptionConfigurationError: If client initialization fails.
        """
        if not api_key:
            api_name = self._get_api_name() # Get name from subclass
            get_logger(__name__).error(f"[{api_name}] API key is required but not provided.")
            raise ValueError(f"{api_name} API key is required.")
        self.api_key = api_key
        self.config = config # Store config
        self.client = None # Subclass initializer should set this
        self.logger = get_logger(__name__, component=self._get_api_name())
        try:
            self._initialize_client(api_key) # Call abstract method for subclass setup
        except Exception as e:
            api_name = self._get_api_name()
            self.logger.error(f"Client initialization failed: {e}", exc_info=True)
            raise TranscriptionConfigurationError(f"{api_name} client initialization failed: {e}", provider=api_name) from e

        self.progress_callback: ProgressCallback = None # Store callback per transcribe call
        self.cancel_event: Optional[threading.Event] = None # Store cancel event per transcribe call
        # Get MAX_CONCURRENT_CHUNKS from app config
        self.max_concurrent_chunks = self.config.get('TRANSCRIPTION_WORKERS', 4)


    # --- Abstract Methods (Must be implemented by subclasses) ---

    @abstractmethod
    def _get_api_name(self) -> str:
        """Return the display name of the API (e.g., "OpenAI Whisper", "AssemblyAI")."""
        pass

    @abstractmethod
    def _initialize_client(self, api_key: str) -> None:
        """Initialize the specific SDK client (e.g., OpenAI(), aai.Transcriber())."""
        pass

    @abstractmethod
    def _prepare_api_params(self, language_code: str, context_prompt: str, response_format: str, is_chunk: bool) -> Dict[str, Any]:
        """
        Prepare the dictionary of parameters for the API call, excluding the file handle.
        Args:
            language_code: Requested language code ('auto' or specific).
            context_prompt: User-provided context.
            response_format: Desired response format ('text', 'json', 'verbose_json', etc.).
            is_chunk: Boolean indicating if this is for a chunk (True) or a single file (False).
        Returns:
            Dictionary of API parameters.
        """
        pass

    @abstractmethod
    def _call_api(self, file_handle: Any, api_params: Dict[str, Any]) -> Any:
        """
        Make the actual transcription API call using the initialized client.
        Args:
            file_handle: The opened file handle (e.g., opened with 'rb').
            api_params: Dictionary of parameters prepared by _prepare_api_params.
        Returns:
            The raw response object from the API call.
        Raises:
            TranscriptionAuthenticationError: If authentication fails.
            TranscriptionRateLimitError: If rate limit is hit.
            TranscriptionProcessingError: For other API call errors.
            Exception: For unexpected errors.
        """
        pass

    @abstractmethod
    def _process_response(self, response: Any, response_format: str) -> Tuple[str, Optional[str]]:
        """
        Parse the raw API response to extract the transcription text and detected language.
        Args:
            response: The raw response object from _call_api.
            response_format: The response format requested (helps in parsing).
        Returns:
            Tuple (transcription_text: str, detected_language: Optional[str]).
            detected_language should be the language code string (e.g., 'en') or None.
        Raises:
            TranscriptionProcessingError: If the response indicates an error or cannot be parsed.
        """
        pass

    @abstractmethod
    def _get_retryable_errors(self) -> Tuple[Type[Exception], ...]:
        """
        Return a tuple of API-specific exception classes that warrant a retry.
        These should typically be subclasses of TranscriptionApiError.
        (e.g., TranscriptionRateLimitError, specific connection errors).
        """
        pass

    # --- Methods from Proposed Architecture (Placeholder Implementations) ---
    # These might be implemented here or within the main `transcribe` method logic.
    # For now, let's keep the core logic in `transcribe` and its helpers.

    def upload_file(self, file_path: str) -> Any:
        """(Optional) Uploads a file to the provider's storage if needed."""
        # Default implementation: Assume direct upload in _call_api
        self.logger.debug("Upload handled directly during transcription call.")
        return file_path # Return path or an ID if uploaded

    def split_audio(self, file_path: str, output_dir: str) -> List[str]:
        """(Optional) Splits audio using file_service."""
        # This logic is currently handled within _split_and_transcribe
        self.logger.debug("Audio splitting handled by internal transcribe logic.")
        # Placeholder: return file_service.split_audio_file(file_path, output_dir, self._report_progress)
        return []

    def get_transcription_status(self, job_id: Any) -> str:
        """(Optional) Gets the status of an async job if the provider uses one."""
        # Default implementation: Assume synchronous processing or SDK handles polling
        self.logger.debug("Status check not applicable or handled by SDK.")
        return "completed" # Placeholder

    def get_transcription_result(self, job_id: Any) -> Tuple[Optional[str], Optional[str]]:
        """(Optional) Gets the result of an async job if the provider uses one."""
        # Default implementation: Result obtained directly from _call_api/_process_response
        self.logger.debug("Result obtained directly from transcription call.")
        return None, None # Placeholder

    # --- Common Workflow Methods ---

    def _report_progress(self, message: str, is_error: bool = False) -> None:
        """
        Internal helper to report progress via logging and the callback.
        Checks for cancellation via the stored event and callback.
        """
        api_name = self._get_api_name()
        # Check internal cancel_event first
        if self.cancel_event and self.cancel_event.is_set():
            self.logger.info("Cancellation detected by internal event.")
            raise InterruptedError("Job cancelled (event set).")

        if is_error:
            self.logger.error(message)
        else:
            self.logger.info(message)

        if self.progress_callback:
            try:
                # The callback itself might raise InterruptedError if it checks external signals
                self.progress_callback(message, is_error)
            except InterruptedError as ie:
                self.logger.info("Cancellation detected by progress callback.")
                if self.cancel_event: self.cancel_event.set() # Ensure event is set
                raise ie
            except Exception as cb_err:
                self.logger.error(f"Error executing progress callback: {cb_err}", exc_info=True)
                # Do not raise other callback errors, just log them

    def transcribe(self, audio_file_path: str, language_code: str,
                   progress_callback: ProgressCallback = None,
                   context_prompt: str = "",
                   original_filename: Optional[str] = None,
                   cancel_event: Optional[threading.Event] = None,
                   audio_length_seconds: Optional[float] = None
                   ) -> Tuple[Optional[str], Optional[str]]:
        """
        Transcribes the audio file using the specific API implementation. Handles splitting.

        Args:
            audio_file_path: Absolute path to the audio file.
            language_code: Language code ('auto' or specific like 'en', 'es').
            progress_callback: Optional function to report progress.
            context_prompt: Optional context/prompt string.
            original_filename: Original name of the file for logging.
            cancel_event: Optional threading.Event to signal cancellation.
            audio_length_seconds: Optional duration of the audio in seconds.

        Returns:
            Tuple (transcription_text, detected_language).
            detected_language is the code used or detected.

        Raises:
            InterruptedError: If the job is cancelled during processing.
            TranscriptionApiError: For API-related errors (config, auth, processing, rate limit).
            ValueError: For invalid input parameters (e.g., file path).
            FileNotFoundError: If the audio file does not exist.
            Exception: For unexpected errors during the process.
        """
        # Store callback and cancel event for use by helper methods
        self.progress_callback = progress_callback
        self.cancel_event = cancel_event or threading.Event() # Use provided or create new

        api_name = self._get_api_name()
        requested_language = language_code
        display_filename = original_filename or os.path.basename(audio_file_path)
        log_prefix = f"[{api_name}:{display_filename}]"

        self._report_progress("Starting transcription process...")
        transcription_text: Optional[str] = None
        final_detected_language: Optional[str] = None

        try:
            # Validate file existence
            if not os.path.exists(audio_file_path):
                raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

            file_size = os.path.getsize(audio_file_path)
            duration_seconds = audio_length_seconds or 0

            # Check if file needs splitting based on size OR duration
            should_split_by_size = file_size > self.SPLIT_THRESHOLD_BYTES
            should_split_by_duration = self.SPLIT_THRESHOLD_SECONDS is not None and duration_seconds > self.SPLIT_THRESHOLD_SECONDS

            if should_split_by_size or should_split_by_duration:
                reason_parts = []
                if should_split_by_size:
                    reason_parts.append(f"size ({file_size / 1024 / 1024:.2f}MB)")
                if should_split_by_duration:
                    reason_parts.append(f"duration ({duration_seconds:.1f}s)")
                
                reason_text = " and ".join(reason_parts)
                mode = "PARALLEL (no prompt)" if not context_prompt else "SEQUENTIAL (prompt provided)"
                self._report_progress(f"File exceeds processing limit ({reason_text}). Starting {mode} chunked transcription.")
                # Delegate to splitting method
                return self._split_and_transcribe(audio_file_path, requested_language, context_prompt, display_filename)
            else:
                # Process single file
                self._report_progress(f"File size ({file_size / 1024 / 1024:.2f}MB) and duration ({duration_seconds:.1f}s) within limit. Processing as single file.")

                # Validate file path is within allowed directory (security measure)
                abs_path = os.path.abspath(audio_file_path)
                temp_dir = os.path.dirname(abs_path) # Assuming file is in a temp dir
                if not file_service.validate_file_path(abs_path, temp_dir):
                    raise ValueError(f"Audio file path is not allowed: {abs_path}")

                # --- Single File Transcription Attempt ---
                response_format = "verbose_json" if requested_language == 'auto' else "text" # Default logic

                api_params = self._prepare_api_params(
                    language_code=requested_language,
                    context_prompt=context_prompt,
                    response_format=response_format,
                    is_chunk=False
                )
                response_format = api_params.get("response_format", response_format)

                log_params = {k: v for k, v in api_params.items() if k != 'file'}
                self.logger.info(f"Calling API for single file with parameters: {log_params}")

                with open(abs_path, "rb") as audio_file:
                    self._report_progress(f"Transcribing with {api_name}...")
                    start_time = time.time()
                    self._report_progress("Checking cancellation before API call...") # Implicit check
                    raw_response = self._call_api(audio_file, api_params) # Can raise TranscriptionApiError subclasses
                    duration = time.time() - start_time
                    self.logger.debug(f"API call successful. Duration: {duration:.2f}s")

                transcription_text, final_detected_language = self._process_response(raw_response, response_format) # Can raise TranscriptionProcessingError

                if requested_language == 'auto' and not final_detected_language:
                    self.logger.warning("Language auto-detection requested, but final language not determined.")
                    final_detected_language = 'auto'
                elif requested_language != 'auto':
                    final_detected_language = requested_language

            log_lang_msg = f"Transcription finished. Final language: {final_detected_language}"
            self.logger.info(log_lang_msg)
            ui_finish_msg = f"{api_name} transcription finished. Final language: {final_detected_language}"
            self._report_progress(ui_finish_msg, False)
            self._report_progress("PHASE_MARKER:TRANSCRIPTION_COMPLETE", False)
            self._report_progress("Transcription completed.", False)

            return transcription_text, final_detected_language

        except InterruptedError:
            self.logger.info("Transcription interrupted by cancellation signal.")
            raise # Re-raise to be caught by the main service
        except (TranscriptionApiError, ValueError, FileNotFoundError) as specific_error:
            # Log and re-raise specific errors (API, input validation, file not found)
            self._report_progress(f"ERROR: {specific_error}", True)
            self.logger.error(f"Transcription failed: {specific_error}", exc_info=True if not isinstance(specific_error, FileNotFoundError) else False)
            raise
        except Exception as e:
            # Wrap unexpected errors
            self._report_progress(f"ERROR: Unexpected error during transcription: {e}", True)
            self.logger.exception("Unexpected error detail:")
            raise TranscriptionProcessingError(f"Unexpected error during transcription: {e}", provider=api_name) from e
        finally:
            # Reset instance variables after processing
            self.progress_callback = None
            self.cancel_event = None


    def _split_and_transcribe(self, audio_file_path: str, language_code: str,
                             context_prompt: str = "",
                             display_filename: Optional[str] = None
                             ) -> Tuple[Optional[str], Optional[str]]:
        """
        Handles splitting large files and transcribing chunks.
        Uses parallel execution if no context prompt is provided, otherwise sequential.
        Relies on the stored progress_callback and cancel_event.

        Raises:
            InterruptedError: If the job is cancelled during processing.
            TranscriptionApiError: For API-related errors (config, auth, processing, rate limit).
            Exception: For unexpected errors during the process (e.g., splitting failure).
        """
        api_name = self._get_api_name()
        requested_language = language_code
        mode_log = "Parallel" if not context_prompt else "Sequential"
        log_prefix = f"[{api_name}:{display_filename or os.path.basename(audio_file_path)}:{mode_log}]"

        temp_dir = os.path.dirname(audio_file_path)
        chunk_files: List[str] = []
        final_language_used: Optional[str] = None
        results: Dict[int, Optional[Tuple[str, Optional[str]]]] = {}
        overall_success = True

        try:
            self._report_progress("PHASE_MARKER:PROCESSING_START", False)
            chunk_files = file_service.split_audio_file(audio_file_path, temp_dir, self._report_progress)
            if not chunk_files:
                # Check if cancellation happened during splitting
                if self.cancel_event and self.cancel_event.is_set():
                    raise InterruptedError("Job cancelled during audio splitting.")
                else:
                    raise TranscriptionProcessingError("Audio splitting failed or resulted in no chunks.", provider=api_name)

            total_chunks = len(chunk_files)
            self._report_progress("PHASE_MARKER:TRANSCRIPTION_START", False)

            if not context_prompt:
                # --- PARALLEL Processing ---
                self._report_progress(f"Starting parallel transcription of {total_chunks} chunks (max workers: {self.max_concurrent_chunks})...")
                futures = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrent_chunks) as executor:
                    for idx, chunk_path in enumerate(chunk_files):
                        if self.cancel_event.is_set():
                            logging.info(f"{log_prefix} Cancellation detected, skipping submission of chunk {idx+1}.")
                            results[idx+1] = None; overall_success = False; continue

                        chunk_num = idx + 1
                        chunk_log_prefix = f"{log_prefix}:Chunk{chunk_num}"
                        current_chunk_lang_param = requested_language
                        response_format = "verbose_json" if requested_language == 'auto' else "text"
                        logging.info(f"{chunk_log_prefix} Submitting chunk {chunk_num} with language '{current_chunk_lang_param}'.")

                        future = executor.submit(
                            self._transcribe_single_chunk_with_retry,
                            chunk_path=chunk_path, idx=chunk_num, total_chunks=total_chunks,
                            language_code=current_chunk_lang_param, response_format=response_format,
                            context_prompt="", log_prefix=chunk_log_prefix
                        )
                        futures.append((chunk_num, future))

                    self._report_progress(f"Waiting for {len(futures)} submitted chunk(s) to complete...", False)
                    for chunk_num, future in futures:
                        try:
                            chunk_result = future.result()
                            results[chunk_num] = chunk_result
                            logging.info(f"{log_prefix}:Chunk{chunk_num} completed successfully.")
                        except InterruptedError:
                             overall_success = False; results[chunk_num] = None
                             logging.info(f"{log_prefix}:Chunk{chunk_num} processing interrupted by cancellation.")
                             self._report_progress(f"Chunk {chunk_num} cancelled.", False)
                             self.cancel_event.set() # Ensure event is set for other threads
                        except Exception as exc:
                            overall_success = False; results[chunk_num] = None
                            logging.error(f"{log_prefix}:Chunk{chunk_num} failed: {exc}")
                            self._report_progress(f"ERROR: Chunk {chunk_num} failed: {exc}", True)
                            # Don't raise immediately in parallel, let others finish/cancel

                if self.cancel_event.is_set():
                    raise InterruptedError("Job cancelled during parallel chunk processing.")
            else:
                # --- SEQUENTIAL Processing ---
                self._report_progress(f"Starting sequential transcription of {total_chunks} chunks (prompt provided)...")
                for idx, chunk_path in enumerate(chunk_files):
                    chunk_num = idx + 1
                    chunk_log_prefix = f"{log_prefix}:Chunk{chunk_num}"
                    current_chunk_lang_param = requested_language
                    response_format = "verbose_json" if requested_language == 'auto' else "text"
                    logging.info(f"{chunk_log_prefix} Starting chunk {chunk_num} with language '{current_chunk_lang_param}'.")

                    try:
                        chunk_result = self._transcribe_single_chunk_with_retry(
                            chunk_path=chunk_path, idx=chunk_num, total_chunks=total_chunks,
                            language_code=current_chunk_lang_param, response_format=response_format,
                            context_prompt=context_prompt, log_prefix=chunk_log_prefix
                        )
                        results[chunk_num] = chunk_result
                        logging.info(f"{chunk_log_prefix} completed successfully.")
                        if requested_language == 'auto' and idx == 0:
                            _, detected_lang = chunk_result
                            if detected_lang: self._report_progress(f"Detected language: {detected_lang}", False)
                            else: self._report_progress("First chunk language detection failed or returned None.", False)
                    except InterruptedError:
                         overall_success = False; results[chunk_num] = None
                         logging.info(f"{log_prefix}:Chunk{chunk_num} processing interrupted by cancellation.")
                         self._report_progress(f"Chunk {chunk_num} cancelled.", False)
                         raise # Stop sequential processing
                    except Exception as exc:
                        overall_success = False; results[chunk_num] = None
                        logging.error(f"{chunk_log_prefix} failed: {exc}")
                        self._report_progress(f"ERROR: Chunk {chunk_num} failed: {exc}", True)
                        raise TranscriptionProcessingError(f"Sequential chunk {chunk_num} failed.", provider=api_name) from exc

            # --- Aggregation ---
            if not overall_success:
                if self.cancel_event.is_set():
                    raise InterruptedError("Job cancelled during chunk processing.")
                else:
                    raise TranscriptionProcessingError("One or more chunks failed transcription.", provider=api_name)

            transcription_texts = []
            detected_languages = []
            first_successful_lang = None
            successful_chunks = 0
            for i in range(total_chunks):
                chunk_num = i + 1
                result_tuple = results.get(chunk_num)
                if result_tuple:
                    text, lang = result_tuple
                    transcription_texts.append(text)
                    successful_chunks += 1
                    if lang:
                        detected_languages.append(lang)
                        if first_successful_lang is None: first_successful_lang = lang

            full_transcription = " ".join(filter(None, transcription_texts))
            logging.debug(f"{log_prefix} Successfully aggregated transcriptions from {successful_chunks} completed chunks.")

            if requested_language == 'auto':
                final_language_used = first_successful_lang or 'auto'
                log_lang_msg = f"{mode_log} chunked transcription aggregated. Final language (detected/fallback): {final_language_used}"
                ui_lang_msg = f"Aggregated chunk transcriptions. Final language (detected/fallback): {final_language_used}"
            else:
                final_language_used = requested_language
                log_lang_msg = f"{mode_log} chunked transcription aggregated. Used requested language: {final_language_used}"
                ui_lang_msg = f"Aggregated chunk transcriptions. Used requested language: {final_language_used}"

            logging.info(f"{log_prefix} {log_lang_msg}")
            self._report_progress(ui_lang_msg, False)
            self._report_progress("PHASE_MARKER:TRANSCRIPTION_COMPLETE", False)
            self._report_progress("Transcription completed.", False)

            return full_transcription, final_language_used

        except InterruptedError:
             logging.info(f"{log_prefix} Split/transcribe process interrupted by cancellation.")
             raise
        except Exception as e:
            error_msg = f"Error during {mode_log.lower()} split/transcribe process: {e}"
            if overall_success: # Only report if no chunk error was reported before
                 self._report_progress(f"ERROR: {error_msg}", True)
            logging.exception(f"{log_prefix} Error detail in _split_and_transcribe:")
            # Wrap unexpected errors
            if isinstance(e, TranscriptionApiError): raise e
            else: raise TranscriptionProcessingError(error_msg, provider=api_name) from e
        finally:
            if chunk_files:
                self._report_progress("Cleaning up temporary chunk files...", False)
                removed_count = file_service.remove_files(chunk_files)
                logging.info(f"{log_prefix} Cleaned up {removed_count} temporary chunk file(s).")


    def _transcribe_single_chunk_with_retry(self, chunk_path: str, idx: int, total_chunks: int,
                                            language_code: str, response_format: str,
                                            context_prompt: str = "", log_prefix: str = "", max_retries: int = 3
                                            ) -> Tuple[str, Optional[str]]:
        """
        Transcribes a single audio chunk with retry logic.
        Relies on the stored progress_callback and cancel_event from the instance.

        Raises:
            InterruptedError: If cancellation is detected.
            TranscriptionApiError: For API-related errors (config, auth, processing, rate limit).
            Exception: For unexpected errors during the process (e.g., file not found).
        """
        last_error: Optional[Exception] = None
        api_name = self._get_api_name()
        chunk_base_name = os.path.basename(chunk_path)
        effective_log_prefix = log_prefix or f"[{api_name}:Chunk{idx}]"

        for attempt in range(max_retries + 1):
            try:
                self._report_progress(f"Starting chunk {idx}/{total_chunks} (Attempt {attempt+1})", False)

                abs_chunk_path = os.path.abspath(chunk_path)
                temp_dir = os.path.dirname(abs_chunk_path)
                if not file_service.validate_file_path(abs_chunk_path, temp_dir):
                    raise ValueError(f"Chunk file path is not allowed: {abs_chunk_path}")
                if not os.path.exists(abs_chunk_path):
                    raise FileNotFoundError(f"Chunk file not found: {chunk_base_name}")

                api_params = self._prepare_api_params(
                    language_code=language_code, context_prompt=context_prompt,
                    response_format=response_format, is_chunk=True
                )
                actual_response_format = api_params.get("response_format", response_format)

                log_params = {k: v for k, v in api_params.items() if k != 'file'}
                prompt_log = f", Prompt: '{context_prompt[:30]}...'" if context_prompt else ""
                logging.debug(f"{effective_log_prefix} Attempt {attempt+1}: Calling API with parameters: {log_params}{prompt_log}")

                with open(abs_chunk_path, "rb") as audio_file:
                    start_time = time.time()
                    self._report_progress("Checking cancellation before API call...") # Implicit check
                    raw_response = self._call_api(audio_file, api_params) # Can raise TranscriptionApiError subclasses
                    duration = time.time() - start_time
                    logging.debug(f"{effective_log_prefix} Attempt {attempt+1}: API call successful. Duration: {duration:.2f}s")

                text, detected_lang = self._process_response(raw_response, actual_response_format) # Can raise TranscriptionProcessingError

                self._report_progress(f"Finished chunk {idx}/{total_chunks}.", False)
                return (text.strip() if text else ""), detected_lang

            except InterruptedError:
                 logging.info(f"{effective_log_prefix} Chunk {idx} cancelled during attempt {attempt+1}.")
                 raise
            except tuple(self._get_retryable_errors()) as retry_err:
                last_error = retry_err
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    error_detail = f"Retryable error on chunk {idx}, attempt {attempt+1}. Retrying in {wait_time}s... ({type(retry_err).__name__})"
                    self._report_progress(error_detail, False)
                    logging.warning(f"{effective_log_prefix} {error_detail}: {retry_err}")
                    time.sleep(wait_time)
                else:
                    logging.error(f"{effective_log_prefix} Max retries ({max_retries}) reached for chunk {idx}. Last error: {retry_err}")
                    raise TranscriptionProcessingError(f"Chunk {idx} failed after {max_retries} retries: {retry_err}", provider=api_name) from retry_err
            except (TranscriptionApiError, ValueError, FileNotFoundError) as specific_error:
                last_error = specific_error
                error_detail = f"ERROR: Error processing chunk {idx}: {specific_error}"
                self._report_progress(error_detail, True)
                logging.error(f"{effective_log_prefix} {error_detail}")
                raise specific_error # Re-raise specific errors to fail fast
            except Exception as e:
                last_error = e
                error_detail = f"ERROR: Unexpected error transcribing chunk {idx}: {e}"
                self._report_progress(error_detail, True)
                logging.exception(f"{effective_log_prefix} Unexpected error detail on attempt {attempt+1}:")
                raise TranscriptionProcessingError(f"Unexpected error transcribing chunk {idx}: {e}", provider=api_name) from e

        # Should not be reached if exceptions are raised correctly
        final_error_msg = f"Chunk {idx} ('{chunk_base_name}') failed after {max_retries} attempts. Last error: {last_error}"
        raise TranscriptionProcessingError(final_error_msg, provider=api_name)