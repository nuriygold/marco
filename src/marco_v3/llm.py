"""Provider-agnostic LLM client for the Marco server.

Supports two providers, selected via ``MARCO_LLM_PROVIDER``:

- ``azure-openai`` (default): Azure OpenAI chat completions.
- ``grok`` (xAI): OpenAI-compatible chat completions at api.x.ai.

Both providers speak the OpenAI chat-completions wire format, so a single
code path drives them. Per-provider details (URL construction, auth header,
token field, default model) are encapsulated in ``ProviderConfig``.

Env vars (read on demand; server refuses to do AI work unless required vars
are set for the selected provider):

  MARCO_LLM_PROVIDER          azure-openai | grok            (default: azure-openai)

  Azure:
    AZURE_OPENAI_API_KEY      required
    AZURE_OPENAI_ENDPOINT     required, e.g. https://x.cognitiveservices.azure.com
    AZURE_OPENAI_DEPLOYMENT   default: gpt-5.3-chat
    AZURE_OPENAI_API_VERSION  default: 2024-12-01-preview

  Grok:
    XAI_API_KEY               required
    XAI_BASE_URL              default: https://api.x.ai/v1
    XAI_MODEL                 default: grok-4-fast-reasoning

  Shared:
    MARCO_LLM_TIMEOUT         default: 60 (seconds)
    MARCO_LLM_MAX_RETRIES     default: 2
    MARCO_LLM_MAX_TOKEN_FIELD override max_tokens / max_completion_tokens auto-detect
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)


# --- Defaults -------------------------------------------------------------

AZURE_DEFAULT_DEPLOYMENT = 'gpt-5.3-chat'
AZURE_DEFAULT_API_VERSION = '2024-12-01-preview'
GROK_DEFAULT_BASE_URL = 'https://api.x.ai/v1'
# Rudolph has Grok 3, Grok 4 Fast Reasoning, and Grok 4 Fast Non-Reasoning.
# grok-4-fast-reasoning is the best default for Marco — reasoning helps with
# patch verbatim precision AND plan generation, and "fast" keeps costs sensible.
GROK_DEFAULT_MODEL = 'grok-4-fast-reasoning'

DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2

# Backwards-compat exports (some tests reference these).
DEFAULT_DEPLOYMENT = AZURE_DEFAULT_DEPLOYMENT
DEFAULT_API_VERSION = AZURE_DEFAULT_API_VERSION


# --- Errors ---------------------------------------------------------------


class LLMNotConfigured(RuntimeError):
    """Raised when required env vars for the selected provider are missing."""


class LLMError(RuntimeError):
    """Raised when the upstream provider returns an error."""


# --- Config ---------------------------------------------------------------


@dataclass(frozen=True)
class ProviderConfig:
    provider: str          # 'azure-openai' | 'grok'
    api_key: str
    url: str               # full chat-completions URL
    model: str             # deployment name (Azure) or model id (Grok)
    auth_header: str       # 'api-key' | 'Authorization'
    auth_prefix: str       # '' | 'Bearer '
    tokens_field: str      # 'max_tokens' | 'max_completion_tokens'
    timeout: float
    max_retries: int
    # For display / UI only. Never return api_key.
    display: dict[str, str]


# Legacy alias for existing code/tests referencing AzureConfig.
AzureConfig = ProviderConfig


def _pick_tokens_field(model_or_deployment: str) -> str:
    override = os.environ.get('MARCO_LLM_MAX_TOKEN_FIELD', '').strip()
    if override in ('max_tokens', 'max_completion_tokens'):
        return override
    low = model_or_deployment.lower()
    # GPT-5 / o-series / reasoning models need max_completion_tokens.
    if any(tag in low for tag in ('gpt-5', 'gpt5', 'o1', 'o3', 'o4', 'reasoning')):
        return 'max_completion_tokens'
    return 'max_tokens'


def _load_azure() -> ProviderConfig:
    api_key = os.environ.get('AZURE_OPENAI_API_KEY', '').strip()
    endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT', '').strip().rstrip('/')
    if not api_key or not endpoint:
        raise LLMNotConfigured(
            'AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are required for provider '
            "'azure-openai'. Set them in /etc/marco/marco.env and restart the service."
        )
    deployment = os.environ.get('AZURE_OPENAI_DEPLOYMENT', AZURE_DEFAULT_DEPLOYMENT).strip()
    api_version = os.environ.get('AZURE_OPENAI_API_VERSION', AZURE_DEFAULT_API_VERSION).strip()
    url = f'{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}'
    return ProviderConfig(
        provider='azure-openai',
        api_key=api_key,
        url=url,
        model=deployment,
        auth_header='api-key',
        auth_prefix='',
        tokens_field=_pick_tokens_field(deployment),
        timeout=float(os.environ.get('MARCO_LLM_TIMEOUT', DEFAULT_TIMEOUT)),
        max_retries=int(os.environ.get('MARCO_LLM_MAX_RETRIES', DEFAULT_MAX_RETRIES)),
        display={
            'provider': 'azure-openai',
            'endpoint': endpoint,
            'deployment': deployment,
            'api_version': api_version,
        },
    )


def _load_grok() -> ProviderConfig:
    api_key = os.environ.get('XAI_API_KEY', '').strip()
    if not api_key:
        raise LLMNotConfigured(
            "XAI_API_KEY is required for provider 'grok'. "
            'Set it in /etc/marco/marco.env and restart the service.'
        )
    base_url = os.environ.get('XAI_BASE_URL', GROK_DEFAULT_BASE_URL).strip().rstrip('/')
    model = os.environ.get('XAI_MODEL', GROK_DEFAULT_MODEL).strip()
    url = f'{base_url}/chat/completions'
    return ProviderConfig(
        provider='grok',
        api_key=api_key,
        url=url,
        model=model,
        auth_header='Authorization',
        auth_prefix='Bearer ',
        tokens_field=_pick_tokens_field(model),
        timeout=float(os.environ.get('MARCO_LLM_TIMEOUT', DEFAULT_TIMEOUT)),
        max_retries=int(os.environ.get('MARCO_LLM_MAX_RETRIES', DEFAULT_MAX_RETRIES)),
        display={
            'provider': 'grok',
            'base_url': base_url,
            'model': model,
        },
    )


def _load_azure_foundry() -> ProviderConfig:
    """Azure AI Foundry OpenAI-compatible endpoint.

    Used for Grok-4-Fast, GPT-OSS, Llama, and other non-classic-Azure-OpenAI
    models that Azure Foundry exposes through its unified OpenAI-compatible
    v1 API. Different from 'azure-openai' which targets the classic
    deployment-based API.
    """
    api_key = os.environ.get('AZURE_FOUNDRY_API_KEY', '').strip()
    endpoint = os.environ.get('AZURE_FOUNDRY_ENDPOINT', '').strip().rstrip('/')
    model = os.environ.get('AZURE_FOUNDRY_MODEL', '').strip()
    if not api_key or not endpoint or not model:
        raise LLMNotConfigured(
            'AZURE_FOUNDRY_API_KEY, AZURE_FOUNDRY_ENDPOINT, and AZURE_FOUNDRY_MODEL '
            "are required for provider 'azure-foundry'. Set them in /etc/marco/marco.env "
            'and restart the service. Example endpoint: '
            'https://myresource.services.ai.azure.com/openai/v1'
        )
    url = f'{endpoint}/chat/completions'
    return ProviderConfig(
        provider='azure-foundry',
        api_key=api_key,
        url=url,
        model=model,
        auth_header='Authorization',
        auth_prefix='Bearer ',
        tokens_field=_pick_tokens_field(model),
        timeout=float(os.environ.get('MARCO_LLM_TIMEOUT', DEFAULT_TIMEOUT)),
        max_retries=int(os.environ.get('MARCO_LLM_MAX_RETRIES', DEFAULT_MAX_RETRIES)),
        display={
            'provider': 'azure-foundry',
            'endpoint': endpoint,
            'model': model,
        },
    )


def load_config() -> ProviderConfig:
    provider = os.environ.get('MARCO_LLM_PROVIDER', 'azure-openai').strip().lower() or 'azure-openai'
    if provider in ('grok', 'xai'):
        return _load_grok()
    if provider in ('azure-foundry', 'azure_foundry', 'foundry', 'azure-ai-foundry'):
        return _load_azure_foundry()
    if provider in ('azure-openai', 'azure_openai', 'azure', 'openai-azure'):
        return _load_azure()
    raise LLMNotConfigured(
        f'Unknown MARCO_LLM_PROVIDER: {provider!r}. '
        'Use "azure-openai", "azure-foundry", or "grok".'
    )


def is_configured() -> bool:
    try:
        load_config()
        return True
    except LLMNotConfigured:
        return False


# --- Core chat completion -------------------------------------------------


def _build_url(config: ProviderConfig) -> str:
    """Back-compat helper for tests."""
    return config.url


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    config: ProviderConfig | None = None,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Send a chat completion request and return the parsed JSON response.

    Retries on 429 and 5xx with exponential backoff.

    Supports OpenAI-compatible tool calling when ``tools`` is provided.
    """
    cfg = config or load_config()

    payload: dict[str, Any] = {
        'messages': messages,
        'temperature': temperature,
        cfg.tokens_field: max_tokens,
    }
    if response_format is not None:
        payload['response_format'] = response_format
    if tools is not None:
        payload['tools'] = tools
    if tool_choice is not None:
        payload['tool_choice'] = tool_choice

    # Grok and Azure Foundry need the model field in body; classic Azure
    # OpenAI has the deployment in the URL path instead.
    if cfg.provider in ('grok', 'azure-foundry'):
        payload['model'] = cfg.model

    headers = {
        cfg.auth_header: f'{cfg.auth_prefix}{cfg.api_key}',
        'Content-Type': 'application/json',
    }

    owned_client = client is None
    if client is None:
        client = httpx.Client(timeout=cfg.timeout)

    try:
        attempt = 0
        while True:
            attempt += 1
            response = client.post(cfg.url, json=payload, headers=headers)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (429, 500, 502, 503, 504) and attempt <= cfg.max_retries:
                sleep_for = min(2 ** (attempt - 1), 10)
                logger.warning(
                    '%s returned %s (attempt %s); retrying in %ss',
                    cfg.provider, response.status_code, attempt, sleep_for,
                )
                time.sleep(sleep_for)
                continue
            raise LLMError(
                f'{cfg.provider} error {response.status_code}: {response.text[:500]}'
            )
    finally:
        if owned_client:
            client.close()


def extract_message_text(response: dict[str, Any]) -> str:
    choices = response.get('choices') or []
    if not choices:
        raise LLMError('response had no choices')
    message = choices[0].get('message') or {}
    content = message.get('content')
    if not isinstance(content, str):
        # Tool-call-only responses may have null content. Return empty string.
        return ''
    return content


def extract_message_json(response: dict[str, Any]) -> dict[str, Any]:
    """Parse the assistant's content as JSON. Strict — the prompt asks for JSON."""
    text = extract_message_text(response)
    if not text:
        raise LLMError('empty response content')
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f'model did not return valid JSON: {exc}') from exc
        raise LLMError('model did not return JSON')


def extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the tool calls (if any) from the first choice."""
    choices = response.get('choices') or []
    if not choices:
        return []
    message = choices[0].get('message') or {}
    tool_calls = message.get('tool_calls') or []
    return list(tool_calls)


# --- High-level operations ------------------------------------------------


PLAN_SYSTEM_PROMPT = (
    'You are Marco, a practical technical operator. Given a development goal '
    'and a repository summary, produce a concise, executable plan.\n\n'
    'Return STRICT JSON with this shape:\n'
    '{\n'
    '  "goal": "restated goal",\n'
    '  "steps": ["step 1", "step 2", ...],\n'
    '  "edit_targets": ["path/to/file.ext", ...],\n'
    '  "risks": ["risk 1", ...],\n'
    '  "validation": "how to verify success"\n'
    '}\n'
    '\n'
    'Rules: 3-8 steps, paths must be relative to repo root, max 6 edit_targets, '
    'max 4 risks, steps are imperative and specific. No prose outside the JSON.'
)


def generate_plan(
    goal: str,
    repo_summary: dict[str, Any],
    *,
    config: ProviderConfig | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Turn a goal into a structured plan using the configured LLM."""
    user_prompt = (
        f'Goal: {goal}\n\n'
        f'Repo summary:\n{json.dumps(repo_summary, indent=2)[:3000]}'
    )
    response = chat_completion(
        messages=[
            {'role': 'system', 'content': PLAN_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        response_format={'type': 'json_object'},
        temperature=0.2,
        max_tokens=1000,
        config=config,
        client=client,
    )
    return extract_message_json(response)


PATCH_SYSTEM_PROMPT = (
    'You are Marco, a precise code-patch assistant. Given a change request '
    'and the contents of a target file, propose a minimal, exact-match patch.\n\n'
    'Return STRICT JSON with this shape:\n'
    '{\n'
    '  "name": "short-kebab-case-name",\n'
    '  "target": "path/to/file.ext (same as input)",\n'
    '  "find": "EXACT text from the file that must be replaced. Must appear EXACTLY ONCE in the file.",\n'
    '  "replace": "replacement text",\n'
    '  "rationale": "one sentence explaining the change"\n'
    '}\n'
    '\n'
    'Rules:\n'
    '- find MUST be a verbatim substring of the file (copy it exactly).\n'
    '- find MUST occur exactly once in the file (add enough surrounding context if needed).\n'
    '- Keep find/replace as small as possible while remaining unambiguous.\n'
    '- Do not include line numbers or diff markers in find/replace.\n'
    '- No prose outside the JSON.'
)


def suggest_patch(
    description: str,
    target_path: str,
    file_contents: str,
    *,
    config: ProviderConfig | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Turn a change description + file contents into a patch proposal."""
    truncated = file_contents
    if len(truncated) > 12000:
        truncated = truncated[:12000] + '\n... [truncated for length]'
    user_prompt = (
        f'Change request: {description}\n\n'
        f'Target file path: {target_path}\n\n'
        f'Current contents:\n```\n{truncated}\n```'
    )
    response = chat_completion(
        messages=[
            {'role': 'system', 'content': PATCH_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
        response_format={'type': 'json_object'},
        temperature=0.1,
        max_tokens=2000,
        config=config,
        client=client,
    )
    suggestion = extract_message_json(response)
    suggestion['target'] = target_path
    return suggestion
