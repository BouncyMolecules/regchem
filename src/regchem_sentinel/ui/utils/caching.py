"""Caching helpers that keep Streamlit execution model explicit."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def idempotent_stub_cache(st: Any) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Placeholder decorator — swap for ``st.cache_data`` once expensive IO lands."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            _ = st
            return func(*args, **kwargs)

        return wrapped

    return decorator


def fingerprint_text(*chunks: Hashable | str) -> str:
    """Build a deterministic cache key fingerprint from hashable excerpts."""

    return "|".join(str(chunk) for chunk in chunks)
