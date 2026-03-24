from __future__ import annotations

from writing_agent.web.runtime_bridge import (
    bind_runtime_namespace,
    build_runtime_skip_names,
    install_exported_functions,
    install_matching_callables,
    matches_private_local_callable,
    sync_prefixed_state_from_namespace,
    sync_prefixed_state_to_namespace,
)


def _module_with_code(name: str, source: str) -> dict[str, object]:
    module_globals: dict[str, object] = {"__name__": name}
    exec(source, module_globals)
    return module_globals


def test_install_exported_functions_rebinds_namespace_before_call() -> None:
    module_globals = _module_with_code(
        "runtime.test.forwarder",
        "def dep():\n    return 'module'\n\n"
        "def hello():\n    return dep()\n",
    )
    namespace = {"dep": lambda: "namespace"}

    def bind(ns: dict[str, object]) -> None:
        bind_runtime_namespace(module_globals, ns, skip_names={"bind", "install"})

    install_exported_functions(
        module_globals,
        namespace,
        exported_functions=["hello"],
        bind_fn=bind,
    )

    assert namespace["hello"]() == "namespace"


def test_build_runtime_skip_names_merges_common_names_and_extras() -> None:
    skip_names = build_runtime_skip_names("_BIND_SKIP_NAMES", "bind", "install")

    assert "__name__" in skip_names
    assert "bind" in skip_names
    assert "_BIND_SKIP_NAMES" in skip_names


def test_bind_runtime_namespace_restores_original_function_from_same_module_proxy() -> None:
    module_globals = _module_with_code(
        "runtime.test.restore",
        "def target():\n    return 'original'\n",
    )
    original = module_globals["target"]

    def _placeholder() -> str:
        return "proxy"

    _placeholder._wa_runtime_proxy = True
    _placeholder._wa_runtime_proxy_target_module = "runtime.test.restore"
    _placeholder._wa_runtime_proxy_target_name = "target"

    module_globals["target"] = lambda: "mutated"
    bind_runtime_namespace(
        module_globals,
        {"target": _placeholder},
        skip_names=set(),
        original_funcs={"target": original},
    )

    assert module_globals["target"] is original


def test_matches_private_local_callable_filters_by_name_and_module() -> None:
    module_globals = _module_with_code(
        "runtime.test.predicates",
        "def _local():\n    return 'ok'\n",
    )

    assert matches_private_local_callable(
        "_local",
        module_globals["_local"],
        module_name="runtime.test.predicates",
        excluded_names={"bind"},
    )
    assert not matches_private_local_callable(
        "bind",
        module_globals["_local"],
        module_name="runtime.test.predicates",
        excluded_names={"bind"},
    )
    assert not matches_private_local_callable(
        "_local",
        lambda: None,
        module_name="runtime.test.predicates",
    )


def test_install_matching_callables_syncs_state_back_to_namespace() -> None:
    module_globals = _module_with_code(
        "runtime.test.stateful",
        "_STATE = 0\n\n"
        "def _step():\n"
        "    global _STATE\n"
        "    _STATE += 1\n"
        "    return _STATE\n",
    )
    original_funcs: dict[str, object] = {}
    namespace: dict[str, object] = {}

    def _state_from(ns: dict[str, object]) -> None:
        if "_STATE" in ns:
            module_globals["_STATE"] = ns["_STATE"]

    def _state_to(ns: dict[str, object]) -> None:
        ns["_STATE"] = module_globals["_STATE"]

    def bind(ns: dict[str, object]) -> None:
        bind_runtime_namespace(
            module_globals,
            ns,
            skip_names={"bind", "install"},
            original_funcs=original_funcs,
            state_from_namespace=_state_from,
        )

    install_matching_callables(
        module_globals,
        namespace,
        bind_fn=bind,
        predicate=lambda fn_name, fn: fn_name == "_step" and callable(fn),
        original_funcs=original_funcs,
        before_install=_state_to,
        after_call=_state_to,
    )

    assert namespace["_STATE"] == 0
    assert namespace["_step"]() == 1
    assert namespace["_STATE"] == 1


def test_sync_prefixed_state_helpers_support_non_overwrite_mode() -> None:
    module_globals = {"_STATE": 1, "_DEBUG_FLAG": "module", "plain": 99}
    namespace = {"_STATE": 4, "_DEBUG_FLAG": "namespace"}

    sync_prefixed_state_from_namespace(
        module_globals,
        namespace,
        prefixes=("_STATE", "_DEBUG_"),
    )

    assert module_globals["_STATE"] == 4
    assert module_globals["_DEBUG_FLAG"] == "namespace"

    module_globals["_STATE"] = 6
    module_globals["_DEBUG_FLAG"] = "next"
    sync_prefixed_state_to_namespace(
        module_globals,
        namespace,
        prefixes=("_STATE", "_DEBUG_"),
        overwrite=False,
    )

    assert namespace["_STATE"] == 4
    assert namespace["_DEBUG_FLAG"] == "namespace"

    sync_prefixed_state_to_namespace(
        module_globals,
        namespace,
        prefixes=("_STATE", "_DEBUG_"),
    )

    assert namespace["_STATE"] == 6
    assert namespace["_DEBUG_FLAG"] == "next"
