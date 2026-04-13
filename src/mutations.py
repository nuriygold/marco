from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import perf_counter


class MutationMode(str, Enum):
    DRY_RUN = 'DRY_RUN'
    EXECUTED = 'EXECUTED'


@dataclass(frozen=True)
class MutationIntent:
    action: str
    target: str
    execute: bool = False

    @property
    def mode(self) -> MutationMode:
        return MutationMode.EXECUTED if self.execute else MutationMode.DRY_RUN

    @property
    def preview_payload(self) -> dict[str, str]:
        return {'action': self.action, 'target': self.target}


@dataclass(frozen=True)
class MutationResult:
    mode: MutationMode
    status: str
    latency_ms: int
    message: str
    payload: dict[str, str]


_HIGH_IMPACT_ACTIONS = frozenset({'task complete', 'approve'})


def requires_confirmation(intent: MutationIntent) -> bool:
    return intent.execute and intent.action in _HIGH_IMPACT_ACTIONS


def render_mutation_result(result: MutationResult) -> str:
    return (
        f'[{result.mode.value}] status={result.status} latency_ms={result.latency_ms} '
        f'payload={result.payload} message={result.message}'
    )


def run_mutation_intent(intent: MutationIntent, *, confirmed: bool = False) -> MutationResult:
    started = perf_counter()
    if requires_confirmation(intent) and not confirmed:
        latency_ms = int((perf_counter() - started) * 1000)
        return MutationResult(
            mode=intent.mode,
            status='cancelled',
            latency_ms=latency_ms,
            message='confirmation required',
            payload=intent.preview_payload,
        )

    latency_ms = int((perf_counter() - started) * 1000)
    if intent.execute:
        return MutationResult(
            mode=MutationMode.EXECUTED,
            status='success',
            latency_ms=latency_ms,
            message=f'executed {intent.action} for {intent.target}',
            payload=intent.preview_payload,
        )
    return MutationResult(
        mode=MutationMode.DRY_RUN,
        status='preview',
        latency_ms=latency_ms,
        message=f'preview {intent.action} for {intent.target}',
        payload=intent.preview_payload,
    )
