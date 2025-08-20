# app/services/llm_service.py
# Handles business logic related to Large Language Model (LLM) interactions.

from app.logging_config import get_logger
from typing import Optional, Dict, Any, List, Tuple, Type
# --- MODIFIED: Import current_app ---
from flask import current_app
# --- END MODIFIED ---

# Import client factory and base client/exceptions
from app.services.api_clients import get_llm_client
from app.services.api_clients.llm.base_llm_client import BaseLLMClient
from app.services.api_clients.exceptions import LlmApiError, LlmConfigurationError, LlmGenerationError, LlmSafetyError

# Import user_service for fetching user-specific API keys
from app.services import user_service # Added import
# --- MODIFIED: Import user_model for fetching user object ---
from app.models import user as user_model
from app.models import llm_operation as llm_operation_model
from app.services.pricing_service import get_price as get_pricing_service_price, PricingServiceError
# --- END MODIFIED ---
 
 # Import models if needed (e.g., for logging operations)
 # from app.models import llm_operation as llm_operation_model

class LlmServiceError(Exception):
    """Custom exception for LLM service errors."""
    pass

def generate_text_via_llm(
    provider_name: str,
    prompt: str,
    user_id: Optional[int] = None, # Added user_id for user-specific key fetching
    api_key: Optional[str] = None, # Allow direct API key override
    **kwargs
) -> str:
    """
    Generates text using the specified LLM provider.
    If in 'multi' user mode and user_id is provided, attempts to use user's API key
    if their role permits API key management. Otherwise, falls back to global config API key.
    An explicitly passed api_key will override other fetching mechanisms.

    Args:
        provider_name: The identifier for the LLM provider (e.g., 'gemini', 'openai').
        prompt: The input prompt.
        user_id: Optional ID of the user making the request (for multi-user mode key fetching).
        api_key: Optional direct API key to use, bypassing other fetching logic.
        **kwargs: Additional arguments for the specific LLM client (e.g., model, max_tokens).

    Returns:
        The generated text.

    Raises:
        LlmConfigurationError: If the client cannot be initialized or API key is missing.
        LlmApiError: If the API call fails (includes subclasses like RateLimit, Safety, etc.).
        LlmServiceError: For other service-level errors.
        ValueError: If required arguments are missing (prompt, provider_name).
    """
    logger = get_logger(__name__, user_id=user_id, provider=provider_name, component="LlmService")
    logger.debug("Request received.")

    if not provider_name or not prompt:
        raise ValueError("Provider name and prompt are required.")

    # Determine API key to use
    effective_api_key: Optional[str] = api_key # Prioritize explicitly passed key

    if not effective_api_key:
        # --- MODIFICATION: Check 'allow_api_key_management' permission ---
        user_can_manage_keys = False
        if current_app.config['DEPLOYMENT_MODE'] == 'multi' and user_id is not None:
            user = user_model.get_user_by_id(user_id)
            if user and user.role:
                user_can_manage_keys = user.has_permission('allow_api_key_management')
            else:
                logger.warning(f"User or role not found for ID {user_id} when checking API key management permission.")

        if current_app.config['DEPLOYMENT_MODE'] == 'multi' and user_id is not None and user_can_manage_keys:
            # --- END MODIFICATION ---
            key_service_name: Optional[str] = None
            logger.debug(f"Checking for user-specific key for provider: {provider_name}")
            if provider_name.upper().startswith("GEMINI"):
                key_service_name = "gemini"
            elif provider_name.upper().startswith("OPENAI") or provider_name.upper().startswith("GPT"):
                key_service_name = "openai"
            # Add other providers as needed

            if key_service_name:
                try:
                    effective_api_key = user_service.get_decrypted_api_key(user_id, key_service_name)
                    if effective_api_key:
                        logger.debug(f"Using user-specific API key for '{key_service_name}'.")
                    else:
                        logger.debug(f"User-specific API key for '{key_service_name}' not found.")
                except Exception as e:
                    logger.warning(f"Error fetching user-specific API key for '{key_service_name}': {e}. Will try global key.")
                    effective_api_key = None # Ensure fallback if error occurs
        # --- MODIFICATION: Added else for when user cannot manage keys in multi-mode ---
        elif current_app.config['DEPLOYMENT_MODE'] == 'multi' and user_id is not None and not user_can_manage_keys:
            logger.debug("User key management disabled for role. Will attempt to use global API key.")
            effective_api_key = None # Ensure fallback to global key
        # --- END MODIFICATION ---


        # Fallback to global API key if not found for user or in single mode or user key management disabled
        if not effective_api_key:
            logger.debug(f"Checking for global key for provider: {provider_name}")
            if provider_name.upper().startswith("GEMINI"):
                effective_api_key = current_app.config.get('GEMINI_API_KEY')
            elif provider_name.upper().startswith("OPENAI") or provider_name.upper().startswith("GPT"):
                effective_api_key = current_app.config.get('OPENAI_API_KEY')
            # Add other providers...
            if effective_api_key:
                logger.debug(f"Using global API key for '{provider_name}'.")

    if not effective_api_key:
        raise LlmConfigurationError(f"API key for LLM provider '{provider_name}' is not configured (checked user-specific and global).", provider=provider_name)

    try:
        app_config = current_app.config
        llm_client: BaseLLMClient = get_llm_client(provider_name, effective_api_key, app_config)

        generated_text = llm_client.generate_text(prompt, **kwargs)

        logger.info("Text generation successful.")
        
        # Calculate and save cost
        if 'operation_id' in kwargs:
            operation_type = kwargs.get('operation_type')
            cost_logger = get_logger(__name__, **logger.extra, llm_op_id=kwargs.get('operation_id'))
            if not operation_type:
                cost_logger.warning(f"No operation_type provided; skipping cost calculation to avoid pricing error.")
            else:
                try:
                    # Pass the specific model being used to the pricing service
                    price = get_pricing_service_price(item_type=operation_type, item_key=provider_name)
                    if price is not None:
                        # Cost is per execution for LLM operations
                        llm_operation_model.update_llm_operation_cost(kwargs['operation_id'], price)
                        cost_logger.debug(f"Successfully calculated and saved cost: {price} (type={operation_type}, model={provider_name})")
                    else:
                        cost_logger.warning(f"No price found for provider '{provider_name}' and item_type '{operation_type}'. Cost not calculated.")
                except PricingServiceError as e:
                    cost_logger.error(f"Could not calculate or save cost for LLM operation: {e}", exc_info=True)

        return generated_text
 
    except (LlmConfigurationError, LlmApiError, ValueError) as e:
        logger.error(f"Error during text generation: {e}", exc_info=isinstance(e, LlmApiError))
        raise e
    except Exception as e:
        logger.error(f"Unexpected error during text generation: {e}", exc_info=True)
        raise LlmServiceError(f"An unexpected error occurred during LLM text generation: {e}") from e

# --- Placeholder for other LLM-related functions ---

# def get_chat_completion(...) -> str:
#     """Handles chat completion logic."""
#     # ... get client, call client.chat_completion ...
#     pass

# def get_text_embedding(...) -> List[float]:
#     """Handles embedding generation logic."""
#     # ... get client, call client.get_embedding ...
#     pass

# Example: A function specifically for workflow analysis, which might log to LLMOperation
# This could potentially live here or in workflow_service.py depending on responsibility split.
# For now, let's assume workflow_service.py coordinates this.

# def run_llm_analysis(
#     provider_name: str,
#     api_key: str,
#     prompt: str,
#     input_data: str, # e.g., transcript text
#     operation_type: str, # e.g., 'workflow'
#     user_id: int,
#     transcription_id: Optional[str] = None,
#     prompt_id: Optional[int] = None
# ) -> str:
#     """Runs an LLM analysis task and logs the operation."""
#     log_prefix = f"[SERVICE:LLM:Analysis:{provider_name}]"
#     operation_record_id = None
#     try:
#         # 1. Create initial LLMOperation record
#         operation_record_id = llm_operation_model.create_llm_operation(
#             user_id=user_id,
#             provider=provider_name,
#             operation_type=operation_type,
#             input_text=prompt, # Or maybe combine prompt + input_data?
#             transcription_id=transcription_id,
#             prompt_id=prompt_id,
#             status='processing'
#         )
#         if not operation_record_id:
#             raise LlmServiceError("Failed to create LLM operation log record.")

#         # 2. Get client and generate text
#         # Combine prompt and input_data as needed for the specific LLM
#         full_prompt = f"Prompt: {prompt}\n\nData:\n{input_data}" # Example combination
#         result_text = generate_text_via_llm(provider_name, api_key, full_prompt)

#         # 3. Update LLMOperation record with success
#         llm_operation_model.update_llm_operation_status(
#             operation_id=operation_record_id,
#             status='finished',
#             result=result_text
#         )
#         return result_text

#     except (LlmApiError, LlmServiceError, ValueError) as e:
#         logging.error(f"{log_prefix} LLM analysis failed: {e}")
#         # Update LLMOperation record with error
#         if operation_record_id:
#             llm_operation_model.update_llm_operation_status(
#                 operation_id=operation_record_id,
#                 status='error',
#                 error=str(e)
#             )
#         raise # Re-raise the error for the caller (e.g., workflow_service)
#     except Exception as e:
#         logging.error(f"{log_prefix} Unexpected error during LLM analysis: {e}", exc_info=True)
#         # Update LLMOperation record with error
#         if operation_record_id:
#             llm_operation_model.update_llm_operation_status(
#                 operation_id=operation_record_id,
#                 status='error',
#                 error=f"Unexpected error: {e}"
#             )
#         raise LlmServiceError(f"An unexpected error occurred during LLM analysis: {e}") from e
