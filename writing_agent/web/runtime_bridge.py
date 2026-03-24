"""Shared helpers for app_v2 runtime namespace bridging.

These modules export selected callables into ``app_v2`` while rebinding globals
from the composition root at call time.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any


COMMON_RUNTIME_BIND_SKIP_NAMES = frozenset(
    {
        "__builtins__",
        "__cached__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
    }
)


def build_runtime_skip_names(*extra_names: str) -> set[str]:
    return set(COMMON_RUNTIME_BIND_SKIP_NAMES).union(extra_names)


def matches_private_local_callable(
    fn_name: str,
    fn: Any,
    *,
    module_name: str,
    excluded_names: set[str] | frozenset[str] | None = None,
) -> bool:
    return (
        fn_name not in (excluded_names or set())
        and fn_name.startswith("_")
        and callable(fn)
        and str(getattr(fn, "__module__", "")) == module_name
    )


def state_key_matches_prefixes(name: object, *, prefixes: tuple[str, ...]) -> bool:
    key = str(name or "")
    return any(key.startswith(prefix) for prefix in prefixes)


def sync_prefixed_state_from_namespace(
    module_globals: dict[str, Any],
    namespace: dict[str, Any],
    *,
    prefixes: tuple[str, ...],
) -> None:
    for key, value in namespace.items():
        if state_key_matches_prefixes(key, prefixes=prefixes):
            module_globals[key] = value
    for key, value in list(module_globals.items()):
        if state_key_matches_prefixes(key, prefixes=prefixes):
            namespace.setdefault(key, value)


def sync_prefixed_state_to_namespace(
    module_globals: dict[str, Any],
    namespace: dict[str, Any],
    *,
    prefixes: tuple[str, ...],
    overwrite: bool = True,
) -> None:
    for key, value in list(module_globals.items()):
        if not state_key_matches_prefixes(key, prefixes=prefixes):
            continue
        if not overwrite and key in namespace:
            continue
        namespace[key] = value


def bind_runtime_namespace(
    module_globals: dict[str, Any],
    namespace: dict[str, Any],
    *,
    skip_names: set[str],
    original_funcs: dict[str, object] | None = None,
    state_from_namespace: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    module_name = str(module_globals.get("__name__", ""))
    for key, value in namespace.items():
        if key in skip_names:
            continue
        if callable(value) and bool(getattr(value, "_wa_runtime_proxy", False)):
            if str(getattr(value, "_wa_runtime_proxy_target_module", "")) == module_name and original_funcs is not None:
                original = original_funcs.get(key)
                if callable(original):
                    module_globals[key] = original
                continue
        local = module_globals.get(key)
        if key in module_globals and local is value:
            continue
        module_globals[key] = value
    if state_from_namespace is not None:
        state_from_namespace(namespace)


def build_runtime_proxy(
    *,
    fn_name: str,
    fn: Callable[..., Any],
    namespace: dict[str, Any],
    module_name: str,
    bind_fn: Callable[[dict[str, Any]], None],
    after_call: Callable[[dict[str, Any]], None] | None = None,
):
    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind_fn(namespace)
        try:
            return fn(*args, **kwargs)
        finally:
            if after_call is not None:
                after_call(namespace)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = module_name
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy


def install_exported_functions(
    module_globals: dict[str, Any],
    namespace: dict[str, Any],
    *,
    exported_functions: list[str],
    bind_fn: Callable[[dict[str, Any]], None],
    original_funcs: dict[str, object] | None = None,
    before_install: Callable[[dict[str, Any]], None] | None = None,
    after_call: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    bind_fn(namespace)
    if before_install is not None:
        before_install(namespace)
    module_name = str(module_globals.get("__name__", ""))
    for fn_name in exported_functions:
        fn = module_globals.get(fn_name)
        if original_funcs is not None:
            original_funcs.setdefault(fn_name, fn)
        if callable(fn):
            namespace[fn_name] = build_runtime_proxy(
                fn_name=fn_name,
                fn=fn,
                namespace=namespace,
                module_name=module_name,
                bind_fn=bind_fn,
                after_call=after_call,
            )


def install_matching_callables(
    module_globals: dict[str, Any],
    namespace: dict[str, Any],
    *,
    bind_fn: Callable[[dict[str, Any]], None],
    predicate: Callable[[str, Any], bool],
    original_funcs: dict[str, object] | None = None,
    before_install: Callable[[dict[str, Any]], None] | None = None,
    after_call: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    bind_fn(namespace)
    if before_install is not None:
        before_install(namespace)
    module_name = str(module_globals.get("__name__", ""))
    for fn_name, fn in list(module_globals.items()):
        if not predicate(fn_name, fn):
            continue
        if original_funcs is not None:
            original_funcs.setdefault(fn_name, fn)
        namespace[fn_name] = build_runtime_proxy(
            fn_name=fn_name,
            fn=fn,
            namespace=namespace,
            module_name=module_name,
            bind_fn=bind_fn,
            after_call=after_call,
        )
