mod client;
mod error;
mod mothership_v2;
mod providers;
mod sse;
mod types;

pub use client::{
    MessageStream, OAuthTokenSet, ProviderClient, oauth_token_is_expired,
    read_azure_openai_base_url, read_base_url, read_xai_base_url, resolve_saved_oauth_token,
    resolve_startup_auth_source,
};
pub use error::ApiError;
pub use providers::claw_provider::{
    mothership_startup_diagnostics, AuthSource, ClawApiClient, ClawApiClient as ApiClient,
    MothershipStartupDiagnostics,
};
pub use mothership_v2::{
    ActivityLogItem, ActivityLogRequest, ActivityLogResponse, ApproveActionRequest,
    ApproveActionResponse, DashboardTodayRequest, DashboardTodayResponse, EmailAiDraft,
    EmailAiDraftsRequest, EmailAiDraftsResponse, EmailRequest, EmailResponse, EmailSummary,
    FinanceOverviewRequest, FinanceOverviewResponse, MothershipV2Client, PatchTaskRequest,
    PatchTaskResponse, Task, TasksRequest, TasksResponse,
};
pub use providers::claw_provider::{AuthSource, ClawApiClient, ClawApiClient as ApiClient};
pub use providers::openai_compat::{OpenAiCompatClient, OpenAiCompatConfig};
pub use providers::{
    ProviderKind, detect_provider_kind, max_tokens_for_model, resolve_model_alias,
};
pub use sse::{SseParser, parse_frame};
pub use types::{
    ContentBlockDelta, ContentBlockDeltaEvent, ContentBlockStartEvent, ContentBlockStopEvent,
    InputContentBlock, InputMessage, MessageDelta, MessageDeltaEvent, MessageRequest,
    MessageResponse, MessageStartEvent, MessageStopEvent, OutputContentBlock, StreamEvent,
    ToolChoice, ToolDefinition, ToolResultContentBlock, Usage,
};
