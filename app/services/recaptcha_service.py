# app/services/recaptcha_service.py
# Helpers for verifying Google reCAPTCHA v3 tokens.

import logging
from typing import List, Optional, Tuple

import requests
from flask import current_app


VERIFY_ENDPOINT = "https://www.google.com/recaptcha/api/siteverify"
ENTERPRISE_ENDPOINT_TEMPLATE = "https://recaptchaenterprise.googleapis.com/v1/projects/{project_id}/assessments?key={api_key}"


def is_configured() -> bool:
    """Return True when required keys are configured for the active mode."""
    site_key = _get_site_key()
    if not site_key:
        return False
    if _use_enterprise():
        return True
    secret_key = current_app.config.get('RECAPTCHA_V3_SECRET_KEY')
    return bool(secret_key)


def verify_token(
    token: Optional[str],
    *,
    action: Optional[str] = None,
    remote_ip: Optional[str] = None,
    min_score: Optional[float] = None
) -> Tuple[bool, float, List[str]]:
    """Validate the provided token against Google's reCAPTCHA endpoint."""
    if not token:
        logging.warning("[Recaptcha] Missing token supplied for verification.")
        return False, 0.0, ["missing-input-response"]

    if not is_configured():
        logging.debug("[Recaptcha] Verification skipped; keys are not configured.")
        return False, 0.0, ["recaptcha-not-configured"]
    if _use_enterprise():
        return _verify_enterprise(token, action=action, remote_ip=remote_ip, min_score=min_score)
    return _verify_classic(token, action=action, remote_ip=remote_ip, min_score=min_score)


def _verify_classic(
    token: Optional[str],
    *,
    action: Optional[str],
    remote_ip: Optional[str],
    min_score: Optional[float]
) -> Tuple[bool, float, List[str]]:
    secret_key = current_app.config.get('RECAPTCHA_V3_SECRET_KEY')
    payload = {
        'secret': secret_key,
        'response': token
    }
    if remote_ip:
        payload['remoteip'] = remote_ip

    try:
        response = requests.post(VERIFY_ENDPOINT, data=payload, timeout=5)
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        logging.error(f"[Recaptcha] Verification request failed: {exc}")
        return False, 0.0, ["recaptcha-unreachable"]
    except ValueError as exc:
        logging.error(f"[Recaptcha] Invalid JSON in verification response: {exc}")
        return False, 0.0, ["recaptcha-invalid-response"]

    score = float(result.get('score', 0.0) or 0.0)
    errors = result.get('error-codes', []) or []
    response_action = result.get('action')

    if action and response_action != action:
        logging.warning(
            f"[Recaptcha] Action mismatch. Expected '{action}', got '{response_action}'."
        )
        if not errors:
            errors = ["recaptcha-action-mismatch"]
        return False, score, errors

    if not result.get('success', False):
        logging.warning(f"[Recaptcha] Verification failed. Errors: {errors}")
        if not errors:
            errors = ["recaptcha-verification-failed"]
        return False, score, errors

    threshold = _resolve_threshold(min_score)
    if score < threshold:
        logging.warning(
            f"[Recaptcha] Score {score} below threshold {threshold}. Possible bot traffic."
        )
        return False, score, errors or ["recaptcha-low-score"]

    logging.debug(
        f"[Recaptcha] Verification succeeded with score {score} for action '{response_action}'."
    )
    return True, score, errors


def _verify_enterprise(
    token: Optional[str],
    *,
    action: Optional[str],
    remote_ip: Optional[str],
    min_score: Optional[float]
) -> Tuple[bool, float, List[str]]:
    site_key = _get_site_key()
    api_key = current_app.config.get('RECAPTCHA_ENTERPRISE_API_KEY')
    project_id = current_app.config.get('RECAPTCHA_ENTERPRISE_PROJECT_ID')
    if not (site_key and api_key and project_id):
        logging.error("[Recaptcha] Enterprise mode enabled but configuration is incomplete.")
        return False, 0.0, ["recaptcha-not-configured"]

    payload = {
        'event': {
            'token': token,
            'siteKey': site_key
        }
    }
    if action:
        payload['event']['expectedAction'] = action
    if remote_ip:
        payload['event']['userIpAddress'] = remote_ip

    endpoint = ENTERPRISE_ENDPOINT_TEMPLATE.format(project_id=project_id, api_key=api_key)

    try:
        response = requests.post(endpoint, json=payload, timeout=5)
        response.raise_for_status()
        result = response.json()
    except requests.RequestException as exc:
        logging.error(f"[Recaptcha] Enterprise verification request failed: {exc}")
        return False, 0.0, ["recaptcha-unreachable"]
    except ValueError as exc:
        logging.error(f"[Recaptcha] Enterprise response JSON error: {exc}")
        return False, 0.0, ["recaptcha-invalid-response"]

    token_props = result.get('tokenProperties', {}) or {}
    if not token_props.get('valid', False):
        reason = token_props.get('invalidReason') or "recaptcha-token-invalid"
        logging.warning(f"[Recaptcha] Enterprise token invalid: {reason}")
        return False, 0.0, [reason]

    response_action = token_props.get('action')
    if action and response_action != action:
        logging.warning(
            f"[Recaptcha] Enterprise action mismatch. Expected '{action}', got '{response_action}'."
        )
        return False, 0.0, ["recaptcha-action-mismatch"]

    risk = result.get('riskAnalysis', {}) or {}
    score = float(risk.get('score', 0.0) or 0.0)
    reasons = risk.get('reasons', []) or []

    threshold = _resolve_threshold(min_score)
    if score < threshold:
        logging.warning(
            f"[Recaptcha] Enterprise score {score} below threshold {threshold}."
        )
        return False, score, reasons or ["recaptcha-low-score"]

    logging.debug(
        f"[Recaptcha] Enterprise verification succeeded with score {score} for action '{response_action}'."
    )
    return True, score, reasons


def _resolve_threshold(explicit: Optional[float]) -> float:
    try:
        threshold = float(explicit if explicit is not None else current_app.config.get('RECAPTCHA_V3_LOGIN_THRESHOLD', 0.5))
    except (TypeError, ValueError):
        threshold = 0.5
    return max(0.0, min(1.0, threshold))


def _get_site_key() -> Optional[str]:
    return current_app.config.get('RECAPTCHA_V3_SITE_KEY')


def _use_enterprise() -> bool:
    return bool(current_app.config.get('RECAPTCHA_USE_ENTERPRISE'))
