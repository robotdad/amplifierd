"""Tests for ProblemDetail, ErrorTypeURI, and domain models."""

import pytest
from pydantic import ValidationError

from amplifierd.models import ErrorTypeURI, ProblemDetail
from amplifierd.models.agents import (
    AgentInfo,
    AgentListResponse,
    SpawnRequest,
    SpawnResponse,
    SpawnResumeRequest,
)
from amplifierd.models.bundles import (
    BundleDetail,
    BundleListResponse,
    BundleSummary,
    BundleUpdateCheck,
    ComposeBundlesRequest,
    LoadBundleRequest,
    PrepareBundleRequest,
    RegisterBundleRequest,
)
from amplifierd.models.events import (
    EventHistoryResponse,
    SSEEnvelope,
)
from amplifierd.models.modules import (
    ModuleListResponse,
    ModuleSummary,
    MountModuleRequest,
    UnmountModuleRequest,
    ValidateBundleRequest,
    ValidateModuleRequest,
    ValidateMountPlanRequest,
    ValidationResponse,
)
from amplifierd.models.sessions import (
    CancelRequest,
    CancelResponse,
    CancelStatusResponse,
    CreateSessionRequest,
    ExecuteRequest,
    ExecuteResponse,
    ExecuteStreamAccepted,
    ForkRequest,
    ForkResponse,
    PatchSessionRequest,
    ResumeSessionRequest,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
    SessionTreeNode,
    StaleRequest,
)


class TestProblemDetail:
    """Tests for the ProblemDetail Pydantic model."""

    def test_minimal(self) -> None:
        """ProblemDetail with only required fields."""
        pd = ProblemDetail(
            type="https://amplifier.dev/errors/rate-limit",
            title="Rate Limit Exceeded",
            status=429,
            detail="Too many requests",
            instance="/sessions/abc123",
        )
        assert pd.type == "https://amplifier.dev/errors/rate-limit"
        assert pd.title == "Rate Limit Exceeded"
        assert pd.status == 429
        assert pd.detail == "Too many requests"
        assert pd.instance == "/sessions/abc123"
        # All optional fields should be None
        assert pd.retryable is None
        assert pd.retry_after_seconds is None
        assert pd.provider is None
        assert pd.model is None
        assert pd.error_class is None
        assert pd.upstream_status is None
        assert pd.tool_name is None
        assert pd.raw_arguments is None

    def test_with_llm_fields(self) -> None:
        """ProblemDetail with LLM error extension fields."""
        pd = ProblemDetail(
            type="https://amplifier.dev/errors/rate-limit",
            title="Rate Limit Exceeded",
            status=429,
            detail="Too many requests",
            instance="/sessions/abc123",
            retryable=True,
            retry_after_seconds=30.0,
            provider="openai",
            model="gpt-4",
            error_class="RateLimitError",
            upstream_status=429,
        )
        assert pd.retryable is True
        assert pd.retry_after_seconds == 30.0
        assert pd.provider == "openai"
        assert pd.model == "gpt-4"
        assert pd.error_class == "RateLimitError"
        assert pd.upstream_status == 429

    def test_with_tool_call_fields(self) -> None:
        """ProblemDetail with InvalidToolCallError extension fields."""
        pd = ProblemDetail(
            type=ErrorTypeURI.INVALID_TOOL_CALL,
            title="Invalid Tool Call",
            status=400,
            detail="Could not parse arguments",
            instance="/sessions/abc123",
            tool_name="get_weather",
            raw_arguments='{"city": "London"',
        )
        assert pd.tool_name == "get_weather"
        assert pd.raw_arguments == '{"city": "London"'


class TestErrorTypeURI:
    """Tests for ErrorTypeURI constants."""

    def test_rate_limit_uri(self) -> None:
        """RATE_LIMIT URI follows base URI pattern."""
        assert ErrorTypeURI.RATE_LIMIT == "https://amplifier.dev/errors/rate-limit"

    def test_session_not_found_uri(self) -> None:
        """SESSION_NOT_FOUND URI follows base URI pattern."""
        assert ErrorTypeURI.SESSION_NOT_FOUND == "https://amplifier.dev/errors/session-not-found"

    @pytest.mark.parametrize(
        "attr",
        [name for name in dir(ErrorTypeURI) if not name.startswith("_")],
    )
    def test_all_uris_follow_base_pattern(self, attr: str) -> None:
        """Every constant starts with the base URI and has a non-empty slug."""
        base = "https://amplifier.dev/errors/"
        value = getattr(ErrorTypeURI, attr)
        assert isinstance(value, str)
        assert value.startswith(base), f"{attr} does not start with {base}"
        slug = value[len(base) :]
        assert slug, f"{attr} has empty slug"
        assert slug == slug.lower(), f"{attr} slug is not lowercase: {slug}"


class TestSessionModels:
    """Tests for session request/response models."""

    def test_create_session_minimal(self) -> None:
        """CreateSessionRequest with no fields (all optional)."""
        req = CreateSessionRequest()
        assert req.bundle_name is None
        assert req.bundle_uri is None
        assert req.session_id is None
        assert req.parent_id is None
        assert req.working_dir is None
        assert req.config_overrides is None

    def test_create_session_full(self) -> None:
        """CreateSessionRequest with all fields populated."""
        req = CreateSessionRequest(
            bundle_name="my-bundle",
            bundle_uri="https://example.com/bundle",
            session_id="sess-123",
            parent_id="parent-456",
            working_dir="/tmp/work",
            config_overrides={"key": "value"},
        )
        assert req.bundle_name == "my-bundle"
        assert req.bundle_uri == "https://example.com/bundle"
        assert req.session_id == "sess-123"
        assert req.parent_id == "parent-456"
        assert req.working_dir == "/tmp/work"
        assert req.config_overrides == {"key": "value"}

    def test_execute_request(self) -> None:
        """ExecuteRequest requires prompt, metadata optional."""
        req = ExecuteRequest(prompt="Hello, world!")
        assert req.prompt == "Hello, world!"
        assert req.metadata is None

        req_with_meta = ExecuteRequest(prompt="Test", metadata={"source": "api"})
        assert req_with_meta.metadata == {"source": "api"}

    def test_execute_request_requires_prompt(self) -> None:
        """ExecuteRequest must have a prompt."""
        with pytest.raises(ValidationError):
            ExecuteRequest()  # type: ignore[call-arg]

    def test_session_summary(self) -> None:
        """SessionSummary fields with defaults."""
        summary = SessionSummary(
            session_id="sess-123",
            status="running",
            bundle="my-bundle",
            created_at="2025-01-01T00:00:00Z",
        )
        assert summary.session_id == "sess-123"
        assert summary.status == "running"
        assert summary.bundle == "my-bundle"
        assert summary.created_at == "2025-01-01T00:00:00Z"
        assert summary.last_activity is None
        assert summary.total_messages is None
        assert summary.tool_invocations is None
        assert summary.parent_session_id is None
        assert summary.stale is None

    def test_execute_stream_accepted(self) -> None:
        """ExecuteStreamAccepted has literal status 'accepted'."""
        resp = ExecuteStreamAccepted(
            correlation_id="corr-123",
            session_id="sess-456",
        )
        assert resp.correlation_id == "corr-123"
        assert resp.session_id == "sess-456"
        assert resp.status == "accepted"

    def test_patch_session(self) -> None:
        """PatchSessionRequest with optional fields."""
        req = PatchSessionRequest()
        assert req.working_dir is None
        assert req.name is None

        req_full = PatchSessionRequest(working_dir="/new/dir", name="my-session")
        assert req_full.working_dir == "/new/dir"
        assert req_full.name == "my-session"

    def test_resume_session_request(self) -> None:
        """ResumeSessionRequest requires session_dir."""
        req = ResumeSessionRequest(session_dir="/path/to/session")
        assert req.session_dir == "/path/to/session"

    def test_cancel_request(self) -> None:
        """CancelRequest with optional immediate flag."""
        req = CancelRequest()
        assert req.immediate is None

        req_imm = CancelRequest(immediate=True)
        assert req_imm.immediate is True

    def test_fork_request(self) -> None:
        """ForkRequest requires turn, handle_orphaned_tools optional."""
        req = ForkRequest(turn=5)
        assert req.turn == 5
        assert req.handle_orphaned_tools is None

        with pytest.raises(ValidationError):
            ForkRequest()  # type: ignore[call-arg]

    def test_stale_request(self) -> None:
        """StaleRequest is empty/extensible."""
        req = StaleRequest()
        assert req is not None

    def test_session_detail_extends_summary(self) -> None:
        """SessionDetail extends SessionSummary with extra fields."""
        detail = SessionDetail(
            session_id="sess-123",
            status="running",
            bundle="my-bundle",
            created_at="2025-01-01T00:00:00Z",
            working_dir="/tmp/work",
        )
        # Inherited from summary
        assert detail.session_id == "sess-123"
        assert detail.status == "running"
        # Detail-specific fields
        assert detail.working_dir == "/tmp/work"
        assert detail.stats is None
        assert detail.mounted_modules is None
        assert detail.capabilities is None

    def test_session_list_response(self) -> None:
        """SessionListResponse contains list and total."""
        resp = SessionListResponse(sessions=[], total=0)
        assert resp.sessions == []
        assert resp.total == 0

    def test_execute_response(self) -> None:
        """ExecuteResponse with all fields."""
        resp = ExecuteResponse(
            response="Hello!",
            usage={"tokens": 10},
            tool_calls=["tool1"],
            finish_reason="stop",
        )
        assert resp.response == "Hello!"
        assert resp.usage == {"tokens": 10}
        assert resp.tool_calls == ["tool1"]
        assert resp.finish_reason == "stop"

    def test_cancel_response(self) -> None:
        """CancelResponse with state and running_tools."""
        resp = CancelResponse(state="cancelling", running_tools=["tool1"])
        assert resp.state == "cancelling"
        assert resp.running_tools == ["tool1"]

    def test_cancel_status_response(self) -> None:
        """CancelStatusResponse with boolean flags."""
        resp = CancelStatusResponse(
            state="cancelled",
            is_cancelled=True,
            is_graceful=True,
            is_immediate=False,
            running_tools=[],
        )
        assert resp.state == "cancelled"
        assert resp.is_cancelled is True
        assert resp.is_graceful is True
        assert resp.is_immediate is False
        assert resp.running_tools == []

    def test_session_tree_node(self) -> None:
        """SessionTreeNode supports recursive children."""
        child = SessionTreeNode(
            session_id="child-1",
            agent="sub-agent",
            status="completed",
            children=[],
        )
        parent = SessionTreeNode(
            session_id="parent-1",
            agent="main",
            status="running",
            children=[child],
        )
        assert parent.session_id == "parent-1"
        assert len(parent.children) == 1
        assert parent.children[0].session_id == "child-1"

    def test_fork_response(self) -> None:
        """ForkResponse with required fields."""
        resp = ForkResponse(
            session_id="new-sess",
            parent_id="old-sess",
            forked_from_turn=3,
            message_count=10,
        )
        assert resp.session_id == "new-sess"
        assert resp.parent_id == "old-sess"
        assert resp.forked_from_turn == 3
        assert resp.message_count == 10


class TestBundleModels:
    """Tests for bundle request/response models."""

    def test_register_bundle_request(self) -> None:
        """RegisterBundleRequest with name and uri."""
        req = RegisterBundleRequest(name="my-bundle", uri="https://example.com")
        assert req.name == "my-bundle"
        assert req.uri == "https://example.com"

    def test_load_bundle_request(self) -> None:
        """LoadBundleRequest with source."""
        req = LoadBundleRequest(source="path/to/bundle")
        assert req.source == "path/to/bundle"

    def test_prepare_bundle_request(self) -> None:
        """PrepareBundleRequest with source and install_deps."""
        req = PrepareBundleRequest(source="path/to/bundle")
        assert req.source == "path/to/bundle"
        assert req.install_deps is None

    def test_compose_bundles_request(self) -> None:
        """ComposeBundlesRequest with bundles list and overrides."""
        req = ComposeBundlesRequest(bundles=["b1", "b2"])
        assert req.bundles == ["b1", "b2"]
        assert req.overrides is None

    def test_bundle_summary(self) -> None:
        """BundleSummary with all fields."""
        summary = BundleSummary(
            name="my-bundle",
            uri="https://example.com",
            version="1.0.0",
            loaded_at="2025-01-01T00:00:00Z",
        )
        assert summary.name == "my-bundle"
        assert summary.uri == "https://example.com"
        assert summary.version == "1.0.0"
        assert summary.loaded_at == "2025-01-01T00:00:00Z"
        assert summary.has_updates is None

    def test_bundle_list_response(self) -> None:
        """BundleListResponse contains list of bundles."""
        resp = BundleListResponse(bundles=[])
        assert resp.bundles == []

    def test_bundle_detail(self) -> None:
        """BundleDetail with comprehensive fields."""
        detail = BundleDetail(
            name="my-bundle",
            version="1.0.0",
        )
        assert detail.name == "my-bundle"
        assert detail.version == "1.0.0"
        assert detail.description is None
        assert detail.includes is None
        assert detail.providers is None
        assert detail.tools is None
        assert detail.hooks is None
        assert detail.agents is None
        assert detail.context_files is None

    def test_bundle_update_check(self) -> None:
        """BundleUpdateCheck with version comparison."""
        check = BundleUpdateCheck(
            name="my-bundle",
            current_version="1.0.0",
            available_version="1.1.0",
            has_update=True,
        )
        assert check.name == "my-bundle"
        assert check.current_version == "1.0.0"
        assert check.available_version == "1.1.0"
        assert check.has_update is True


class TestEventModels:
    """Tests for event models."""

    def test_sse_envelope(self) -> None:
        """SSEEnvelope with all fields."""
        env = SSEEnvelope(
            event="message",
            data={"content": "hello"},
            session_id="sess-123",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert env.event == "message"
        assert env.data == {"content": "hello"}
        assert env.session_id == "sess-123"
        assert env.timestamp == "2025-01-01T00:00:00Z"
        assert env.correlation_id is None
        assert env.sequence is None

    def test_event_history_response(self) -> None:
        """EventHistoryResponse with events list."""
        resp = EventHistoryResponse(events=[], total=0, has_more=False)
        assert resp.events == []
        assert resp.total == 0
        assert resp.has_more is False


class TestAgentModels:
    """Tests for agent models."""

    def test_spawn_request(self) -> None:
        """SpawnRequest with required and optional fields."""
        req = SpawnRequest(agent="code-reviewer", instruction="Review this code")
        assert req.agent == "code-reviewer"
        assert req.instruction == "Review this code"
        assert req.context_depth is None
        assert req.context_scope is None
        assert req.context_turns is None
        assert req.provider_preferences is None
        assert req.model_role is None

    def test_spawn_resume_request(self) -> None:
        """SpawnResumeRequest with instruction."""
        req = SpawnResumeRequest(instruction="Continue review")
        assert req.instruction == "Continue review"

    def test_spawn_response(self) -> None:
        """SpawnResponse with output fields."""
        resp = SpawnResponse(
            output="Review complete",
            session_id="agent-sess-123",
            status="completed",
        )
        assert resp.output == "Review complete"
        assert resp.session_id == "agent-sess-123"
        assert resp.status == "completed"
        assert resp.turn_count is None
        assert resp.metadata is None

    def test_agent_info(self) -> None:
        """AgentInfo with description and model_role."""
        info = AgentInfo(description="A code reviewer agent")
        assert info.description == "A code reviewer agent"
        assert info.model_role is None

    def test_agent_list_response(self) -> None:
        """AgentListResponse with agents dict."""
        resp = AgentListResponse(agents={"reviewer": AgentInfo(description="Reviewer")})
        assert "reviewer" in resp.agents
        assert resp.agents["reviewer"].description == "Reviewer"


class TestModuleModels:
    """Tests for module models."""

    def test_mount_module_request(self) -> None:
        """MountModuleRequest with module_id and optional fields."""
        req = MountModuleRequest(module_id="my-module")
        assert req.module_id == "my-module"
        assert req.config is None
        assert req.source is None

    def test_unmount_module_request(self) -> None:
        """UnmountModuleRequest with mount_point and name."""
        req = UnmountModuleRequest()
        assert req.mount_point is None
        assert req.name is None

    def test_module_summary(self) -> None:
        """ModuleSummary with all fields."""
        summary = ModuleSummary(
            id="mod-1",
            name="test-module",
            version="1.0.0",
            type="tool",
        )
        assert summary.id == "mod-1"
        assert summary.name == "test-module"
        assert summary.version == "1.0.0"
        assert summary.type == "tool"
        assert summary.mount_point is None
        assert summary.description is None

    def test_module_list_response(self) -> None:
        """ModuleListResponse with modules list."""
        resp = ModuleListResponse(modules=[])
        assert resp.modules == []

    def test_validate_mount_plan_request(self) -> None:
        """ValidateMountPlanRequest with mount_plan."""
        req = ValidateMountPlanRequest(mount_plan={"step": "install"})
        assert req.mount_plan == {"step": "install"}

    def test_validate_module_request(self) -> None:
        """ValidateModuleRequest with fields."""
        req = ValidateModuleRequest(module_id="mod-1", type="tool")
        assert req.module_id == "mod-1"
        assert req.type == "tool"
        assert req.source is None
        assert req.config is None

    def test_validate_bundle_request(self) -> None:
        """ValidateBundleRequest with source."""
        req = ValidateBundleRequest(source="path/to/bundle")
        assert req.source == "path/to/bundle"

    def test_validation_response(self) -> None:
        """ValidationResponse with valid and diagnostic fields."""
        resp = ValidationResponse(valid=True)
        assert resp.valid is True
        assert resp.errors is None
        assert resp.warnings is None
        assert resp.checks is None

        resp_invalid = ValidationResponse(
            valid=False,
            errors=["missing field"],
            warnings=["deprecated usage"],
            checks=[{"name": "schema", "passed": False}],
        )
        assert resp_invalid.valid is False
        assert resp_invalid.errors == ["missing field"]
        assert resp_invalid.warnings == ["deprecated usage"]
        assert resp_invalid.checks is not None
        assert len(resp_invalid.checks) == 1
