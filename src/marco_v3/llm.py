"""Azure OpenAI client for the Marco server.

Minimal httpx-based client that speaks the Azure OpenAI chat completions
endpoint. Imported lazily from the API routes so the CLI still works
without the LLM deps installed.

Configuration (env vars, read on demand):
  AZURE_OPENAI_API_KEY      required
  AZURE_OPENAI_ENDPOINT     required, e.g. https://myresource.openai.azure.com
  AZURE_OPENAI_DEPLOYMENT   default: gpt-4o-mini
  AZURE_OPENAI_API_VERSION  default: 2024-10-21
  MARCO_LLM_TIMEOUT         default: 60 (seconds)
  MARCO_LLM_MAX_RETRIES     default: 2
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


# Defaults tuned for Rudolph's Azure deployment (gpt-5.3-chat on
# blessed-abundance-resource). Override any of these via env vars at deploy time.
# gpt-4o-mini is too weak for reliable patch find/replace work — don't default to it.
DEFAULT_DEPLOYMENT = 'gpt-5.3-chat'
DEFAULT_API_VERSION = '2024-12-01-preview'
DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2

# GPT-5 / o-series models require `max_completion_tokens` instead of legacy
# `max_tokens`. We auto-select based on deployment name; override with
# MARCO_LLM_MAX_TOKEN_FIELD if your deployment needs the other.
def _max_tokens_field(deployment: str) -> str:
    override = os.environ.get('MARCO_LLM_MAX_TOKEN_FIELD', '').strip()
    if override in ('max_tokens', 'max_completion_tokens'):
        return override
    if any(tag in deployment.lower() for tag in ('gpt-5', 'gpt5', 'o1', 'o3', 'o4')):
        return 'max_completion_tokens'
    return 'max_tokens'


class LLMNotConfigured(RuntimeError):
    """Raised when AZURE_OPENAI_API_KEY / ENDPOINT are missing."""


class LLMError(RuntimeError):
    """Raised when the upstream Azure API returns an error."""


@dataclass(frozen=True)
class AzureConfig:
    api_key: str
    endpoint: str
    deployment: str
    api_version: str
    timeout: float
    max_retries: int


def load_config() -> AzureConfig:
    api_key = os.environ.get('AZURE_OPENAI_API_KEY', '').strip()
    endpoint = os.environ.get('AZURE_OPENAI_ENDPOINT', '').strip().rstrip('/')
    if not api_key or not endpoint:
        raise LLMNotConfigured(
            'AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are required. '
            'Set them in /etc/marco/marco.env and restart the service.'
        )
    return AzureConfig(
        api_key=api_key,
        endpoint=endpoint,
        deployment=os.environ.get('AZURE_OPENAI_DEPLOYMENT', DEFAULT_DEPLOYMENT).strip(),
        api_version=os.environ.get('AZURE_OPENAI_API_VERSION', DEFAULT_API_VERSION).strip(),
        timeout=float(os.environ.get('MARCO_LLM_TIMEOUT', DEFAULT_TIMEOUT)),
        max_retries=int(os.environ.get('MARCO_LLM_MAX_RETRIES', DEFAULT_MAX_RETRIES)),
    )


def is_configured() -> bool:
    try:
        load_config()
        return True
    except LLMNotConfigured:
        return False


def _build_url(config: AzureConfig) -> str:
    return (
        f'{config.endpoint}/openai/deployments/{config.deployment}'
        f'/chat/completions?api-version={config.api_version}'
    )


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    config: AzureConfig | None = None,
    response_format: dict[str, Any] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Send a chat completion request and return the parsed JSON response.

    Retries on 429 and 5xx with exponential backoff.
    """
    cfg = config or load_config()
    url = _build_url(cfg)
    # GPT-5 and o-series need `max_completion_tokens`, legacy needs `max_tokens`.
    tokens_field = _max_tokens_field(cfg.deployment)
    payload: dict[str, Any] = {
        'messages': messages,
        'temperature': temperature,
        tokens_field: max_tokens,
    }
    if response_format is not None:
        payload['response_format'] = response_format

    headers = {
        'api-key': cfg.api_key,
        'Content-Type': 'application/json',
    }

    owned_client = client is None
    if client is None:
        client = httpx.Client(timeout=cfg.timeout)

    try:
        attempt = 0
        while True:
            attempt += 1
            response = client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (429, 500, 502, 503, 504) and attempt <= cfg.max_retries:
                sleep_for = min(2 ** (attempt - 1), 10)
                logger.warning(
                    'Azure OpenAI returned %s (attempt %s); retrying in %ss',
                    response.status_code,
                    attempt,
                    sleep_for,
                )
                time.sleep(sleep_for)
                continue
            raise LLMError(
                f'Azure OpenAI error {response.status_code}: {response.text[:500]}'
            )
    finally:
        if owned_client:
            client.close()


def extract_message_text(response: dict[str, Any]) -> str:
    choices = response.get('choices') or []
    if not choices:
        raise LLMError('Azure OpenAI response had no choices')
    message = choices[0].get('message') or {}
    content = message.get('content')
    if not isinstance(content, str):
        raise LLMError('Azure OpenAI response content was not a string')
    return content


def extract_message_json(response: dict[str, Any]) -> dict[str, Any]:
    """Parse the assistant's content as JSON. Strict — the prompt asks for JSON."""
    text = extract_message_text(response)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage a JSON object embedded in the text.
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError(f'model did not return valid JSON: {exc}') from exc
        raise LLMError('model did not return JSON')


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
    config: AzureConfig | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Turn a goal into a structured plan using Azure OpenAI."""
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
    config: AzureConfig | None = None,
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
    # Force target to the requested path; model sometimes drifts.
    suggestion['target'] = target_path
    return suggestion
