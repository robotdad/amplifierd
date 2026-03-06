"""Tests for LLM/Bundle error mapping to RFC 7807 Problem Details."""

from amplifier_core.llm_errors import (
    AbortError,
    ConfigurationError,
    ContextLengthError,
    LLMError,
    NetworkError,
    QuotaExceededError,
    RateLimitError,
)

from amplifierd.errors import build_problem_detail, map_llm_error


class TestLLMErrorMapping:
    """Tests for map_llm_error: exception -> (status_code, error_suffix)."""

    def test_rate_limit_maps_to_429(self) -> None:
        exc = RateLimitError("slow down", provider="anthropic", retryable=True)
        status, suffix = map_llm_error(exc)
        assert status == 429
        assert suffix == "rate-limit"

    def test_quota_exceeded_before_rate_limit(self) -> None:
        """QuotaExceededError (subclass of RateLimitError) must match first."""
        exc = QuotaExceededError("over quota", provider="openai")
        status, suffix = map_llm_error(exc)
        assert status == 429
        assert suffix == "quota-exceeded"

    def test_network_error_before_provider_unavailable(self) -> None:
        """NetworkError (subclass of ProviderUnavailableError) must match first."""
        exc = NetworkError("dns failed", provider="anthropic")
        status, suffix = map_llm_error(exc)
        assert status == 503
        assert suffix == "network-error"

    def test_context_length_maps_to_413(self) -> None:
        exc = ContextLengthError("too long", provider="openai")
        status, suffix = map_llm_error(exc)
        assert status == 413
        assert suffix == "context-too-large"

    def test_abort_maps_to_499(self) -> None:
        exc = AbortError("cancelled")
        status, suffix = map_llm_error(exc)
        assert status == 499
        assert suffix == "aborted"

    def test_configuration_maps_to_500(self) -> None:
        exc = ConfigurationError("bad config")
        status, suffix = map_llm_error(exc)
        assert status == 500
        assert suffix == "configuration-error"

    def test_base_llm_error_maps_to_502(self) -> None:
        exc = LLMError("generic llm error")
        status, suffix = map_llm_error(exc)
        assert status == 502
        assert suffix == "llm-error"


class TestBuildProblemDetail:
    """Tests for build_problem_detail: exception -> ProblemDetail."""

    def test_rate_limit_includes_retry_after(self) -> None:
        exc = RateLimitError(
            "rate limited",
            provider="anthropic",
            model="claude-3",
            retry_after=30.0,
            retryable=True,
        )
        pd = build_problem_detail(exc, instance="/v1/chat/abc123")
        assert pd.status == 429
        assert pd.retryable is True
        assert pd.retry_after_seconds == 30.0
        assert pd.provider == "anthropic"
        assert pd.model == "claude-3"
        assert "rate-limit" in pd.type

    def test_quota_exceeded_not_retryable(self) -> None:
        exc = QuotaExceededError(
            "quota exhausted",
            provider="openai",
            model="gpt-4",
            retryable=False,
        )
        pd = build_problem_detail(exc, instance="/v1/chat/xyz789")
        assert pd.status == 429
        assert pd.retryable is False
        assert pd.retry_after_seconds is None
        assert pd.provider == "openai"
        assert pd.model == "gpt-4"
        assert "quota-exceeded" in pd.type
