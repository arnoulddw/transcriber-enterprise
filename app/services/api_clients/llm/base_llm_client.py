# app/services/api_clients/llm/base_llm_client.py
# Defines the Abstract Base Class for Large Language Model (LLM) API clients.

from app.logging_config import get_logger
from abc import ABC, abstractmethod
# --- MODIFIED: Import Dict ---
from typing import Optional, Dict, Any, List, Tuple, Type
# --- END MODIFIED ---

# Import custom exceptions
from app.services.api_clients.exceptions import (
    LlmApiError,
    LlmConfigurationError,
    LlmGenerationError,
    LlmAuthenticationError,
    LlmRateLimitError,
    LlmSafetyError
)

class BaseLLMClient(ABC):
    """
    Abstract Base Class for LLM API clients.
    Defines the common interface for text generation, chat, embeddings, etc.
    """

    # --- MODIFIED: Accept config dictionary in __init__ ---
    def __init__(self, api_key: str, config: Dict[str, Any]) -> None:
        """
        Initializes the base LLM client.

        Args:
            api_key: The API key for the specific LLM service.
            config: The Flask application configuration dictionary.

        Raises:
            ValueError: If the API key is not provided.
            LlmConfigurationError: If client initialization fails.
        """
        if not api_key:
            api_name = self._get_api_name()
            get_logger(__name__).error(f"[{api_name}] API key is required but not provided.")
            raise ValueError(f"{api_name} API key is required.")
        self.api_key = api_key
        self.config = config # Store config
        self.client = None # Subclass initializer should set this
        self.logger = get_logger(__name__, component=self._get_api_name())
        try:
            # Pass config to the initialization method
            self._initialize_client(api_key, config)
        except Exception as e:
            api_name = self._get_api_name()
            self.logger.error(f"LLM Client initialization failed: {e}", exc_info=True)
            raise LlmConfigurationError(f"{api_name} client initialization failed: {e}", provider=api_name) from e
    # --- END MODIFIED ---

    # --- Abstract Methods (Must be implemented by subclasses) ---

    @abstractmethod
    def _get_api_name(self) -> str:
        """Return the display name of the LLM provider (e.g., "Google Gemini", "OpenAI GPT")."""
        pass

    # --- MODIFIED: Add config parameter to _initialize_client ---
    @abstractmethod
    def _initialize_client(self, api_key: str, config: Dict[str, Any]) -> None:
        """Initialize the specific SDK client (e.g., genai.Client(), openai.OpenAI())."""
        pass
    # --- END MODIFIED ---

    @abstractmethod
    def generate_text(self, prompt: str, **kwargs) -> str:
        """
        Generates text based on a single prompt.

        Args:
            prompt: The input prompt string.
            **kwargs: Additional provider-specific parameters (e.g., max_tokens, temperature).

        Returns:
            The generated text string.

        Raises:
            LlmAuthenticationError: If authentication fails.
            LlmRateLimitError: If rate limit is hit.
            LlmSafetyError: If content generation is blocked due to safety settings.
            LlmGenerationError: For other API call or processing errors.
            Exception: For unexpected errors.
        """
        pass

    @abstractmethod
    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generates a response based on a conversation history (list of messages).

        Args:
            messages: A list of message dictionaries, typically with 'role' and 'content' keys.
            **kwargs: Additional provider-specific parameters.

        Returns:
            The generated message content string.

        Raises:
            LlmAuthenticationError, LlmRateLimitError, LlmSafetyError, LlmGenerationError, Exception.
        """
        pass

    @abstractmethod
    def get_embedding(self, text: str, **kwargs) -> List[float]:
        """
        Generates an embedding vector for the given text.

        Args:
            text: The input text string.
            **kwargs: Additional provider-specific parameters (e.g., model name).

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            LlmAuthenticationError, LlmRateLimitError, LlmGenerationError, Exception.
        """
        pass

    @abstractmethod
    def _get_retryable_errors(self) -> Tuple[Type[Exception], ...]:
        """
        Return a tuple of API-specific exception classes that warrant a retry.
        These should typically be subclasses of LlmApiError.
        """
        pass

    # --- Optional Helper Methods (Can be overridden) ---

    def _prepare_generation_params(self, **kwargs) -> Dict[str, Any]:
        """Prepare common parameters for text generation."""
        params = {
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.7),
            # Add other common params like top_p, top_k if applicable
        }
        return params

    def _prepare_chat_params(self, **kwargs) -> Dict[str, Any]:
        """Prepare common parameters for chat completion."""
        params = {
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.7),
        }
        return params

    def _prepare_embedding_params(self, **kwargs) -> Dict[str, Any]:
        """Prepare common parameters for embedding generation."""
        params = {
            "model": kwargs.get("model", "default-embedding-model") # Subclass should specify default
        }
        return params