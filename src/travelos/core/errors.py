"""Error taxonomy. Anything raised towards the API layer is a TravelOSError with a user-safe message."""
from __future__ import annotations


class TravelOSError(Exception):
    code = "error"
    status = 500

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ValidationError(TravelOSError):
    code, status = "validation_error", 400


class NotFound(TravelOSError):
    code, status = "not_found", 404


class ProviderError(TravelOSError):
    """An external source failed (network, HTTP status, bad payload, missing key...)."""
    code, status = "provider_error", 502

    def __init__(self, message: str, *, provider: str = "", retryable: bool = False, detail: str | None = None):
        super().__init__(message, detail=detail)
        self.provider = provider
        self.retryable = retryable


class ProviderUnavailable(ProviderError):
    """Provider is not configured (e.g. missing API key) - not an error worth alarming the user."""
    code = "provider_unavailable"


class AllProvidersFailed(ProviderError):
    code = "all_providers_failed"

    def __init__(self, capability: str, attempts: list):
        super().__init__(f"No {capability} source could answer right now.", provider=capability)
        self.attempts = attempts
