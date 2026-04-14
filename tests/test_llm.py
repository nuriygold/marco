from __future__ import annotations

import json
import unittest
from unittest import mock

import httpx

from src.marco_v3 import llm


class LoadConfigTests(unittest.TestCase):
    def test_missing_key_raises(self) -> None:
        with mock.patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(llm.LLMNotConfigured):
                llm.load_config()

    def test_missing_endpoint_raises(self) -> None:
        with mock.patch.dict('os.environ', {'AZURE_OPENAI_API_KEY': 'x'}, clear=True):
            with self.assertRaises(llm.LLMNotConfigured):
                llm.load_config()

    def test_defaults_applied(self) -> None:
        env = {
            'AZURE_OPENAI_API_KEY': 'sk-abc',
            'AZURE_OPENAI_ENDPOINT': 'https://foo.openai.azure.com/',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = llm.load_config()
            self.assertEqual(cfg.api_key, 'sk-abc')
            self.assertEqual(cfg.provider, 'azure-openai')
            self.assertEqual(cfg.model, llm.AZURE_DEFAULT_DEPLOYMENT)
            self.assertIn('2024-12-01-preview', cfg.url)

    def test_sensible_defaults_for_marco_use_case(self) -> None:
        # Default should NOT be gpt-4o-mini — too weak for patch verbatim work.
        self.assertNotEqual(llm.AZURE_DEFAULT_DEPLOYMENT, 'gpt-4o-mini')

    def test_overrides(self) -> None:
        env = {
            'AZURE_OPENAI_API_KEY': 'sk',
            'AZURE_OPENAI_ENDPOINT': 'https://a.openai.azure.com',
            'AZURE_OPENAI_DEPLOYMENT': 'gpt-4o',
            'AZURE_OPENAI_API_VERSION': '2024-11-01',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = llm.load_config()
            self.assertEqual(cfg.model, 'gpt-4o')
            self.assertIn('2024-11-01', cfg.url)


def _azure_cfg(**overrides) -> llm.ProviderConfig:
    base = dict(
        provider='azure-openai',
        api_key='sk-test',
        url='https://r.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-10-21',
        model='gpt-4o-mini',
        auth_header='api-key',
        auth_prefix='',
        tokens_field='max_tokens',
        timeout=5.0,
        max_retries=2,
        display={'provider': 'azure-openai'},
    )
    base.update(overrides)
    return llm.ProviderConfig(**base)


def _grok_cfg(**overrides) -> llm.ProviderConfig:
    base = dict(
        provider='grok',
        api_key='xai-test',
        url='https://api.x.ai/v1/chat/completions',
        model='grok-4-fast-reasoning',
        auth_header='Authorization',
        auth_prefix='Bearer ',
        tokens_field='max_tokens',
        timeout=5.0,
        max_retries=2,
        display={'provider': 'grok'},
    )
    base.update(overrides)
    return llm.ProviderConfig(**base)


class UrlBuildingTests(unittest.TestCase):
    def test_azure_url_shape(self) -> None:
        env = {
            'AZURE_OPENAI_API_KEY': 'k',
            'AZURE_OPENAI_ENDPOINT': 'https://r.cognitiveservices.azure.com',
            'AZURE_OPENAI_DEPLOYMENT': 'gpt-5.3-chat',
            'AZURE_OPENAI_API_VERSION': '2024-12-01-preview',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = llm.load_config()
        self.assertEqual(
            cfg.url,
            'https://r.cognitiveservices.azure.com/openai/deployments/gpt-5.3-chat'
            '/chat/completions?api-version=2024-12-01-preview',
        )
        self.assertEqual(cfg.auth_header, 'api-key')
        self.assertEqual(cfg.tokens_field, 'max_completion_tokens')

    def test_grok_url_shape(self) -> None:
        env = {
            'MARCO_LLM_PROVIDER': 'grok',
            'XAI_API_KEY': 'xai-abc',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = llm.load_config()
        self.assertEqual(cfg.url, 'https://api.x.ai/v1/chat/completions')
        self.assertEqual(cfg.auth_header, 'Authorization')
        self.assertEqual(cfg.auth_prefix, 'Bearer ')
        self.assertEqual(cfg.model, 'grok-4-fast-reasoning')

    def test_grok_requires_key(self) -> None:
        with mock.patch.dict('os.environ', {'MARCO_LLM_PROVIDER': 'grok'}, clear=True):
            with self.assertRaises(llm.LLMNotConfigured):
                llm.load_config()

    def test_azure_foundry_shape(self) -> None:
        env = {
            'MARCO_LLM_PROVIDER': 'azure-foundry',
            'AZURE_FOUNDRY_API_KEY': 'k',
            'AZURE_FOUNDRY_ENDPOINT': 'https://blessed.services.ai.azure.com/openai/v1',
            'AZURE_FOUNDRY_MODEL': 'grok-4-fast-reasoning',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            cfg = llm.load_config()
        self.assertEqual(cfg.provider, 'azure-foundry')
        self.assertEqual(
            cfg.url,
            'https://blessed.services.ai.azure.com/openai/v1/chat/completions',
        )
        self.assertEqual(cfg.auth_header, 'Authorization')
        self.assertEqual(cfg.auth_prefix, 'Bearer ')
        self.assertEqual(cfg.model, 'grok-4-fast-reasoning')

    def test_azure_foundry_requires_all_three(self) -> None:
        # Missing model.
        env = {
            'MARCO_LLM_PROVIDER': 'azure-foundry',
            'AZURE_FOUNDRY_API_KEY': 'k',
            'AZURE_FOUNDRY_ENDPOINT': 'https://x.services.ai.azure.com/openai/v1',
        }
        with mock.patch.dict('os.environ', env, clear=True):
            with self.assertRaises(llm.LLMNotConfigured):
                llm.load_config()

    def test_unknown_provider_raises(self) -> None:
        with mock.patch.dict('os.environ', {'MARCO_LLM_PROVIDER': 'bogus'}, clear=True):
            with self.assertRaises(llm.LLMNotConfigured):
                llm.load_config()


class ChatCompletionTests(unittest.TestCase):
    CFG = _azure_cfg()

    def _mock_client(self, status: int, body: dict | str) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            if isinstance(body, dict):
                return httpx.Response(status, json=body, request=request)
            return httpx.Response(status, text=str(body), request=request)

        transport = httpx.MockTransport(handler)
        return httpx.Client(transport=transport, timeout=5.0)

    def test_success_returns_parsed_json(self) -> None:
        body = {
            'choices': [{'message': {'content': '{"ok": true}'}}],
            'usage': {'total_tokens': 5},
        }
        with self._mock_client(200, body) as client:
            res = llm.chat_completion(
                messages=[{'role': 'user', 'content': 'hi'}],
                config=self.CFG,
                client=client,
            )
        self.assertEqual(res['choices'][0]['message']['content'], '{"ok": true}')

    def test_azure_sends_api_key_header(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={'choices': [{'message': {'content': '{}'}}]},
                request=request,
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            llm.chat_completion(
                messages=[{'role': 'user', 'content': 'x'}],
                config=self.CFG,
                client=client,
            )
        self.assertEqual(captured[0].headers['api-key'], 'sk-test')
        self.assertEqual(captured[0].headers['content-type'], 'application/json')

    def test_grok_sends_bearer_and_model_in_body(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={'choices': [{'message': {'content': '{}'}}]},
                request=request,
            )

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            llm.chat_completion(
                messages=[{'role': 'user', 'content': 'hi'}],
                config=_grok_cfg(),
                client=client,
            )
        req = captured[0]
        self.assertEqual(req.headers['authorization'], 'Bearer xai-test')
        body = json.loads(req.read().decode())
        self.assertEqual(body['model'], 'grok-4-fast-reasoning')
        self.assertIn('max_tokens', body)

    def test_retry_on_503_then_success(self) -> None:
        call_count = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count['n'] += 1
            if call_count['n'] == 1:
                return httpx.Response(503, text='Service Unavailable', request=request)
            return httpx.Response(
                200,
                json={'choices': [{'message': {'content': '{"retry": true}'}}]},
                request=request,
            )

        transport = httpx.MockTransport(handler)
        with mock.patch('time.sleep'):  # speed up
            with httpx.Client(transport=transport) as client:
                res = llm.chat_completion(
                    messages=[{'role': 'user', 'content': 'x'}],
                    config=self.CFG,
                    client=client,
                )
        self.assertEqual(call_count['n'], 2)
        self.assertIn('retry', res['choices'][0]['message']['content'])

    def test_error_after_retries_exhausted(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text='still down', request=request)

        transport = httpx.MockTransport(handler)
        with mock.patch('time.sleep'):
            with httpx.Client(transport=transport) as client:
                with self.assertRaises(llm.LLMError):
                    llm.chat_completion(
                        messages=[{'role': 'user', 'content': 'x'}],
                        config=self.CFG,
                        client=client,
                    )

    def test_non_retriable_4xx_raises_immediately(self) -> None:
        calls = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls['n'] += 1
            return httpx.Response(401, text='unauthorized', request=request)

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            with self.assertRaises(llm.LLMError):
                llm.chat_completion(
                    messages=[{'role': 'user', 'content': 'x'}],
                    config=self.CFG,
                    client=client,
                )
        self.assertEqual(calls['n'], 1)


class HighLevelTests(unittest.TestCase):
    CFG = _azure_cfg(max_retries=0)

    def _client_returning(self, content: str) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={'choices': [{'message': {'content': content}}]},
                request=request,
            )

        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_generate_plan_parses_json(self) -> None:
        plan_json = json.dumps({
            'goal': 'x', 'steps': ['a', 'b'],
            'edit_targets': ['src/x.py'], 'risks': ['r'], 'validation': 'v',
        })
        with self._client_returning(plan_json) as client:
            plan = llm.generate_plan('goal', {'file_count': 1}, config=self.CFG, client=client)
        self.assertEqual(plan['steps'], ['a', 'b'])

    def test_suggest_patch_forces_target(self) -> None:
        suggestion_json = json.dumps({
            'name': 'rename', 'target': 'WRONG.py',
            'find': 'foo', 'replace': 'bar', 'rationale': 'test',
        })
        with self._client_returning(suggestion_json) as client:
            res = llm.suggest_patch(
                'rename foo to bar', 'src/real.py', 'def foo(): pass',
                config=self.CFG, client=client,
            )
        # Target is forced back to the requested path.
        self.assertEqual(res['target'], 'src/real.py')
        self.assertEqual(res['find'], 'foo')

    def test_suggest_patch_extracts_json_from_prose(self) -> None:
        # Model returns prose around JSON — we should still parse.
        messy = 'Sure! Here is the patch: {"name": "x", "find": "a", "replace": "b"} Done.'
        with self._client_returning(messy) as client:
            res = llm.suggest_patch(
                'desc', 'f.py', 'content with a',
                config=self.CFG, client=client,
            )
        self.assertEqual(res['find'], 'a')


if __name__ == '__main__':
    unittest.main()
