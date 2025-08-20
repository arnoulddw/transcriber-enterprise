# app/services/api_clients/exceptions.py
# Defines custom exceptions for API client interactions.

class ApiClientError(Exception):
    """Base exception for all API client errors."""
    def __init__(self, message="An API client error occurred.", status_code=500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class TranscriptionApiError(ApiClientError):
    """Exception for transcription-specific API errors."""
    def __init__(self, message="A transcription API error occurred.", status_code=500, provider=None):
        self.provider = provider
        super().__init__(message, status_code)

    def __str__(self):
        provider_info = f" (Provider: {self.provider})" if self.provider else ""
        return f"{super().__str__()}{provider_info}"

class LlmApiError(ApiClientError):
    """Exception for LLM-specific API errors."""
    def __init__(self, message="An LLM API error occurred.", status_code=500, provider=None):
        self.provider = provider
        super().__init__(message, status_code)

    def __str__(self):
        provider_info = f" (Provider: {self.provider})" if self.provider else ""
        return f"{super().__str__()}{provider_info}"

# --- Specific Transcription Errors ---

class TranscriptionConfigurationError(TranscriptionApiError):
    """Error related to transcription configuration (e.g., invalid language)."""
    def __init__(self, message="Transcription configuration error.", provider=None):
        super().__init__(message, status_code=400, provider=provider)

class TranscriptionProcessingError(TranscriptionApiError):
    """Error during the transcription process itself (e.g., audio decoding, API call failure)."""
    def __init__(self, message="Transcription processing failed.", status_code=500, provider=None):
        super().__init__(message, status_code=status_code, provider=provider)

class TranscriptionAuthenticationError(TranscriptionApiError):
    """Authentication error with the transcription API provider."""
    def __init__(self, message="Transcription API authentication failed.", provider=None):
        super().__init__(message, status_code=401, provider=provider)

class TranscriptionRateLimitError(TranscriptionApiError):
    """Rate limit exceeded with the transcription API provider."""
    def __init__(self, message="Transcription API rate limit exceeded.", provider=None):
        super().__init__(message, status_code=429, provider=provider)

# --- NEW: Quota Exceeded Error ---
class TranscriptionQuotaExceededError(TranscriptionApiError):
    """Quota exceeded with the transcription API provider."""
    def __init__(self, message="Transcription API quota exceeded.", provider=None):
        # Use 429 status code like rate limits, but it's a distinct error type
        super().__init__(message, status_code=429, provider=provider)
# --- END NEW ---

# --- Specific LLM Errors ---

class LlmConfigurationError(LlmApiError):
    """Error related to LLM configuration (e.g., invalid model)."""
    def __init__(self, message="LLM configuration error.", provider=None):
        super().__init__(message, status_code=400, provider=provider)

class LlmGenerationError(LlmApiError):
    """Error during LLM text generation or processing."""
    def __init__(self, message="LLM generation failed.", status_code=500, provider=None):
        super().__init__(message, status_code=status_code, provider=provider)

class LlmAuthenticationError(LlmApiError):
    """Authentication error with the LLM API provider."""
    def __init__(self, message="LLM API authentication failed.", provider=None):
        super().__init__(message, status_code=401, provider=provider)

class LlmRateLimitError(LlmApiError):
    """Rate limit exceeded with the LLM API provider."""
    def __init__(self, message="LLM API rate limit exceeded.", provider=None):
        super().__init__(message, status_code=429, provider=provider)

class LlmSafetyError(LlmApiError):
    """Content blocked due to safety settings."""
    def __init__(self, message="LLM content blocked due to safety settings.", provider=None):
        super().__init__(message, status_code=400, provider=provider) # Often a 400 Bad Request