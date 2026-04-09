use std::ffi::OsString;
use std::sync::{Mutex, OnceLock};

use api::{
    read_azure_openai_base_url, read_xai_base_url, ApiError, AuthSource, ProviderClient,
    ProviderKind,
};

#[test]
fn provider_client_routes_grok_aliases_through_xai() {
    let _lock = env_lock();
    let _xai_api_key = EnvVarGuard::set("XAI_API_KEY", Some("xai-test-key"));

    let client = ProviderClient::from_model("grok-mini").expect("grok alias should resolve");

    assert_eq!(client.provider_kind(), ProviderKind::Xai);
}

#[test]
fn provider_client_reports_missing_xai_credentials_for_grok_models() {
    let _lock = env_lock();
    let _xai_api_key = EnvVarGuard::set("XAI_API_KEY", None);

    let error = ProviderClient::from_model("grok-3")
        .expect_err("grok requests without XAI_API_KEY should fail fast");

    match error {
        ApiError::MissingCredentials { provider, env_vars } => {
            assert_eq!(provider, "xAI");
            assert_eq!(env_vars, &["XAI_API_KEY"]);
        }
        other => panic!("expected missing xAI credentials, got {other:?}"),
    }
}

#[test]
fn provider_client_uses_explicit_auth_without_env_lookup() {
    let _lock = env_lock();
    let _api_key = EnvVarGuard::set("ANTHROPIC_API_KEY", None);
    let _auth_token = EnvVarGuard::set("ANTHROPIC_AUTH_TOKEN", None);

    let client = ProviderClient::from_model_with_default_auth(
        "claude-sonnet-4-6",
        Some(AuthSource::ApiKey("claw-test-key".to_string())),
    )
    .expect("explicit auth should avoid env lookup");

    assert_eq!(client.provider_kind(), ProviderKind::ClawApi);
}

#[test]
fn read_xai_base_url_prefers_env_override() {
    let _lock = env_lock();
    let _xai_base_url = EnvVarGuard::set("XAI_BASE_URL", Some("https://example.xai.test/v1"));

    assert_eq!(read_xai_base_url(), "https://example.xai.test/v1");
}

#[test]
fn provider_client_routes_unknown_models_through_azure_when_configured() {
    let _lock = env_lock();
    let _openai_api_key = EnvVarGuard::set("OPENAI_API_KEY", None);
    let _azure_api_key = EnvVarGuard::set("AZURE_OPENAI_API_KEY", Some("azure-test-key"));
    let _azure_base_url = EnvVarGuard::set(
        "AZURE_OPENAI_BASE_URL",
        Some("https://example.openai.azure.com/openai/v1"),
    );

    let client = ProviderClient::from_model("gpt-4.1").expect("azure provider should resolve");

    assert_eq!(client.provider_kind(), ProviderKind::AzureOpenAi);
}

#[test]
fn provider_client_reports_missing_azure_configuration() {
    let _lock = env_lock();
    let _openai_api_key = EnvVarGuard::set("OPENAI_API_KEY", None);
    let _azure_api_key = EnvVarGuard::set("AZURE_OPENAI_API_KEY", Some("azure-test-key"));
    let _azure_base_url = EnvVarGuard::set("AZURE_OPENAI_BASE_URL", None);
    let _azure_endpoint = EnvVarGuard::set("AZURE_OPENAI_ENDPOINT", None);

    let error =
        ProviderClient::from_model("gpt-4.1").expect_err("missing azure base URL should fail fast");

    match error {
        ApiError::Configuration(message) => {
            assert!(message.contains("AZURE_OPENAI_BASE_URL"));
        }
        other => panic!("expected azure configuration error, got {other:?}"),
    }
}

#[test]
fn read_azure_base_url_prefers_endpoint_fallback() {
    let _lock = env_lock();
    let _azure_base_url = EnvVarGuard::set("AZURE_OPENAI_BASE_URL", None);
    let _azure_endpoint = EnvVarGuard::set(
        "AZURE_OPENAI_ENDPOINT",
        Some("https://example.openai.azure.com"),
    );

    assert_eq!(
        read_azure_openai_base_url(),
        "https://example.openai.azure.com"
    );
}

fn env_lock() -> std::sync::MutexGuard<'static, ()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

struct EnvVarGuard {
    key: &'static str,
    original: Option<OsString>,
}

impl EnvVarGuard {
    fn set(key: &'static str, value: Option<&str>) -> Self {
        let original = std::env::var_os(key);
        match value {
            Some(value) => std::env::set_var(key, value),
            None => std::env::remove_var(key),
        }
        Self { key, original }
    }
}

impl Drop for EnvVarGuard {
    fn drop(&mut self) {
        match &self.original {
            Some(value) => std::env::set_var(self.key, value),
            None => std::env::remove_var(self.key),
        }
    }
}
