use std::collections::BTreeMap;

use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::error::ApiError;

pub const DEFAULT_BASE_URL: &str = "https://api.anthropic.com";

#[derive(Debug, Clone)]
pub struct MothershipV2Client {
    http: reqwest::Client,
    base_url: String,
    bearer_token: String,
}

impl MothershipV2Client {
    #[must_use]
    pub fn new(bearer_token: impl Into<String>) -> Self {
        Self {
            http: reqwest::Client::new(),
            base_url: DEFAULT_BASE_URL.to_string(),
            bearer_token: bearer_token.into(),
        }
    }

    #[must_use]
    pub fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into();
        self
    }

    pub async fn dashboard_today(
        &self,
        request: &DashboardTodayRequest,
    ) -> Result<DashboardTodayResponse, ApiError> {
        self.get("/api/v2/dashboard/today", request).await
    }

    pub async fn tasks(&self, request: &TasksRequest) -> Result<TasksResponse, ApiError> {
        self.get("/api/v2/tasks", request).await
    }

    pub async fn patch_task(
        &self,
        task_id: &str,
        request: &PatchTaskRequest,
    ) -> Result<PatchTaskResponse, ApiError> {
        let path = format!("/api/v2/tasks/{task_id}");
        self.patch_json(&path, request).await
    }

    pub async fn email(&self, request: &EmailRequest) -> Result<EmailResponse, ApiError> {
        self.get("/api/v2/email", request).await
    }

    pub async fn email_ai_drafts(
        &self,
        email_id: &str,
        request: &EmailAiDraftsRequest,
    ) -> Result<EmailAiDraftsResponse, ApiError> {
        let path = format!("/api/v2/email/{email_id}/ai-drafts");
        self.get(&path, request).await
    }

    pub async fn finance_overview(
        &self,
        request: &FinanceOverviewRequest,
    ) -> Result<FinanceOverviewResponse, ApiError> {
        self.get("/api/v2/finance/overview", request).await
    }

    pub async fn activity_log(
        &self,
        request: &ActivityLogRequest,
    ) -> Result<ActivityLogResponse, ApiError> {
        self.get("/api/v2/activity/log", request).await
    }

    pub async fn approve_action(
        &self,
        action_id: &str,
        request: &ApproveActionRequest,
    ) -> Result<ApproveActionResponse, ApiError> {
        let path = format!("/api/v2/actions/{action_id}/approve");
        self.post_json(&path, request).await
    }

    async fn get<Q, R>(&self, path: &str, query: &Q) -> Result<R, ApiError>
    where
        Q: Serialize + ?Sized,
        R: for<'de> Deserialize<'de>,
    {
        let response = self
            .request(self.http.get(self.url(path)).query(query))
            .await?;
        deserialize(response).await
    }

    async fn patch_json<B, R>(&self, path: &str, body: &B) -> Result<R, ApiError>
    where
        B: Serialize + ?Sized,
        R: for<'de> Deserialize<'de>,
    {
        let response = self
            .request(self.http.patch(self.url(path)).json(body))
            .await?;
        deserialize(response).await
    }

    async fn post_json<B, R>(&self, path: &str, body: &B) -> Result<R, ApiError>
    where
        B: Serialize + ?Sized,
        R: for<'de> Deserialize<'de>,
    {
        let response = self
            .request(self.http.post(self.url(path)).json(body))
            .await?;
        deserialize(response).await
    }

    async fn request(
        &self,
        request_builder: reqwest::RequestBuilder,
    ) -> Result<reqwest::Response, ApiError> {
        let response = request_builder
            .bearer_auth(&self.bearer_token)
            .header("content-type", "application/json")
            .send()
            .await
            .map_err(ApiError::from)?;
        expect_success(response).await
    }

    fn url(&self, path: &str) -> String {
        format!("{}{}", self.base_url.trim_end_matches('/'), path)
    }
}

async fn deserialize<T>(response: reqwest::Response) -> Result<T, ApiError>
where
    T: for<'de> Deserialize<'de>,
{
    response.json::<T>().await.map_err(ApiError::from)
}

async fn expect_success(response: reqwest::Response) -> Result<reqwest::Response, ApiError> {
    let status = response.status();
    if status.is_success() {
        return Ok(response);
    }

    let body = response.text().await.unwrap_or_default();
    Err(ApiError::api_from_error_envelope(
        status,
        body,
        is_retryable_status(status),
    ))
}

const fn is_retryable_status(status: StatusCode) -> bool {
    matches!(status.as_u16(), 408 | 409 | 429 | 500 | 502 | 503 | 504)
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct DashboardTodayRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub timezone: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DashboardTodayResponse {
    pub date: String,
    #[serde(default)]
    pub cards: Vec<Value>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct TasksRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TasksResponse {
    #[serde(default)]
    pub tasks: Vec<Task>,
    #[serde(default)]
    pub next_cursor: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Task {
    pub id: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PatchTaskRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub assignee_id: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PatchTaskResponse {
    pub task: Task,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct EmailRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub folder: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EmailResponse {
    #[serde(default)]
    pub emails: Vec<EmailSummary>,
    #[serde(default)]
    pub next_cursor: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EmailSummary {
    pub id: String,
    #[serde(default)]
    pub subject: Option<String>,
    #[serde(default)]
    pub from: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct EmailAiDraftsRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EmailAiDraftsResponse {
    #[serde(default)]
    pub drafts: Vec<EmailAiDraft>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EmailAiDraft {
    pub id: String,
    #[serde(default)]
    pub content: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct FinanceOverviewRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub range: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct FinanceOverviewResponse {
    #[serde(default)]
    pub summary: BTreeMap<String, Value>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ActivityLogRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub limit: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ActivityLogResponse {
    #[serde(default)]
    pub items: Vec<ActivityLogItem>,
    #[serde(default)]
    pub next_cursor: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ActivityLogItem {
    pub id: String,
    #[serde(default)]
    pub event_type: Option<String>,
    #[serde(default)]
    pub created_at: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ApproveActionRequest {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ApproveActionResponse {
    pub id: String,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}
