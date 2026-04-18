"""Marco v3 operator runtime package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from .cli import run_v3_command


def _load_llm_module() -> ModuleType:
    """Load the real ``src.marco_v3.llm`` module, replacing test-time stubs.

    Some tests inject ``MagicMock`` into ``sys.modules['src.marco_v3.llm']``.
    That can leak across the test process and break modules that expect the
    real exception classes/functions. We defensively reload from ``llm.py``
    when the cached module lacks core LLM symbols.
    """
    module_name = f"{__name__}.llm"
    candidate = sys.modules.get(module_name)
    if isinstance(candidate, ModuleType) and all(
        hasattr(candidate, attr) for attr in ("load_config", "LLMNotConfigured", "LLMError", "chat_completion")
    ):
        return candidate

    llm_path = Path(__file__).with_name("llm.py")
    spec = importlib.util.spec_from_file_location(module_name, llm_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec for {module_name} from {llm_path}")
    module = importlib.util.module_from_spec(spec)
    # Register before execution so decorators/types that inspect sys.modules
    # (e.g. dataclasses internals) see a valid module object. If a test has
    # injected a non-module sentinel (MagicMock), restore it after loading so
    # that tests relying on that sentinel keep working.
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is not None and not isinstance(previous, ModuleType):
            sys.modules[module_name] = previous
    return module


def __getattr__(name: str):
    if name == "llm":
        module = _load_llm_module()
        # Cache on package so future `from . import llm` resolves to the same
        # object (important for unittest.mock.patch target consistency).
        globals()["llm"] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["run_v3_command", "llm"]
