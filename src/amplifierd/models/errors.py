"""RFC 7807 ProblemDetail model and ErrorTypeURI constants."""

from pydantic import BaseModel

_BASE_URI = "https://amplifier.dev/errors"


class ErrorTypeURI:
    """String constants for all error type URIs."""

    # LLM errors
    RATE_LIMIT = f"{_BASE_URI}/rate-limit"
    QUOTA_EXCEEDED = f"{_BASE_URI}/quota-exceeded"
    PROVIDER_AUTH = f"{_BASE_URI}/provider-auth"
    PROVIDER_ACCESS_DENIED = f"{_BASE_URI}/provider-access-denied"
    CONTEXT_TOO_LARGE = f"{_BASE_URI}/context-too-large"
    CONTENT_FILTERED = f"{_BASE_URI}/content-filtered"
    INVALID_REQUEST = f"{_BASE_URI}/invalid-request"
    PROVIDER_UNAVAILABLE = f"{_BASE_URI}/provider-unavailable"
    NETWORK_ERROR = f"{_BASE_URI}/network-error"
    PROVIDER_TIMEOUT = f"{_BASE_URI}/provider-timeout"
    PROVIDER_NOT_FOUND = f"{_BASE_URI}/provider-not-found"
    STREAM_ERROR = f"{_BASE_URI}/stream-error"
    ABORTED = f"{_BASE_URI}/aborted"
    INVALID_TOOL_CALL = f"{_BASE_URI}/invalid-tool-call"
    CONFIGURATION_ERROR = f"{_BASE_URI}/configuration-error"
    LLM_ERROR = f"{_BASE_URI}/llm-error"

    # Bundle errors
    BUNDLE_NOT_FOUND = f"{_BASE_URI}/bundle-not-found"
    BUNDLE_LOAD_ERROR = f"{_BASE_URI}/bundle-load-error"
    BUNDLE_VALIDATION_ERROR = f"{_BASE_URI}/bundle-validation-error"
    BUNDLE_DEPENDENCY_ERROR = f"{_BASE_URI}/bundle-dependency-error"
    BUNDLE_ERROR = f"{_BASE_URI}/bundle-error"

    # Module errors
    MODULE_NOT_FOUND = f"{_BASE_URI}/module-not-found"
    MODULE_LOAD_ERROR = f"{_BASE_URI}/module-load-error"
    MODULE_VALIDATION_ERROR = f"{_BASE_URI}/module-validation-error"
    MODULE_ACTIVATION_ERROR = f"{_BASE_URI}/module-activation-error"

    # Session errors
    SESSION_NOT_FOUND = f"{_BASE_URI}/session-not-found"
    SESSION_NOT_RUNNING = f"{_BASE_URI}/session-not-running"
    SESSION_ALREADY_EXISTS = f"{_BASE_URI}/session-already-exists"
    EXECUTION_IN_PROGRESS = f"{_BASE_URI}/execution-in-progress"
    APPROVAL_NOT_FOUND = f"{_BASE_URI}/approval-not-found"
    APPROVAL_ALREADY_RESOLVED = f"{_BASE_URI}/approval-already-resolved"
    APPROVAL_TIMEOUT = f"{_BASE_URI}/approval-timeout"

    # Request validation
    VALIDATION_ERROR = f"{_BASE_URI}/validation-error"
    MALFORMED_REQUEST = f"{_BASE_URI}/malformed-request"


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Detail response model."""

    # Required fields
    type: str
    title: str
    status: int
    detail: str
    instance: str

    # Optional LLM error extensions
    retryable: bool | None = None
    retry_after_seconds: float | None = None
    provider: str | None = None
    model: str | None = None
    error_class: str | None = None
    upstream_status: int | None = None

    # Optional InvalidToolCallError extensions
    tool_name: str | None = None
    raw_arguments: str | None = None
