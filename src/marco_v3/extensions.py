from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubAgentHook:
    name: str
    enabled: bool
    description: str


@dataclass(frozen=True)
class ScheduleHook:
    name: str
    cron: str
    enabled: bool


def default_subagents() -> list[SubAgentHook]:
    return [
        SubAgentHook(name='research-agent', enabled=False, description='Future deep research decomposition agent'),
        SubAgentHook(name='validation-agent', enabled=False, description='Future autonomous validation and triage agent'),
    ]


def default_schedules() -> list[ScheduleHook]:
    return [
        ScheduleHook(name='nightly-validate', cron='0 2 * * *', enabled=False),
        ScheduleHook(name='weekly-repo-map-refresh', cron='0 5 * * 1', enabled=False),
    ]
