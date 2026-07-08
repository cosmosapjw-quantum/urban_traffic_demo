"""Adaptive policy plugin interface and registry (T061)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

__all__ = [
    "AdaptivePolicyPlugin",
    "PolicyPlugin",
    "register_policy_plugin",
    "register_adaptive_policy_plugin",
    "create_policy_plugin",
    "build_policy_plugin",
    "get_policy_plugin",
]


@runtime_checkable
class AdaptivePolicyPlugin(Protocol):
    """Contract boundary for adaptive routing plugins.

    The first concrete implementation will be OD-UCB, but the registry and
    interface are intentionally generic to support future plugins.
    """

    plugin_name: str
    plugin_version: str
    supports_online_update: bool
    supports_batch_context: bool

    def init(self, config, seed) -> Any:
        """Initialize plugin state from config + seed only."""

    def score_actions(self, plugin_state, routing_context_batch, rng_key):
        """Score legal actions/candidates for a routing context batch."""

    def update_online(self, plugin_state, experience_batch, rng_key):
        """Update plugin state from simulator-only online experience."""


# Alias kept for contract-test flexibility and future naming cleanup.
PolicyPlugin = AdaptivePolicyPlugin

_PLUGIN_REGISTRY: dict[str, type[Any]] = {}


def register_policy_plugin(plugin_cls: type[Any]) -> type[Any]:
    """Register an adaptive policy plugin class by its `plugin_name`.

    Raises:
        ValueError: if identity fields are missing/invalid or name is duplicate.
    """

    name = _coerce_plugin_name(getattr(plugin_cls, "plugin_name", None))
    if name in _PLUGIN_REGISTRY:
        raise ValueError(f"plugin already registered: {name}")

    # Minimal identity/contract checks; richer validation can be added later.
    _validate_plugin_identity_fields(plugin_cls)
    for method_name in ("init", "score_actions", "update_online"):
        if not callable(getattr(plugin_cls, method_name, None)):
            raise ValueError(f"plugin missing required method: {method_name}")

    _PLUGIN_REGISTRY[name] = plugin_cls
    return plugin_cls


def register_adaptive_policy_plugin(plugin_cls: type[Any]) -> type[Any]:
    """Alias for `register_policy_plugin`."""

    return register_policy_plugin(plugin_cls)


def create_policy_plugin(plugin_name: str, config: dict[str, Any] | None = None) -> Any:
    """Instantiate a registered plugin by name.

    `config` is best-effort constructor wiring only in T061:
    - if plugin constructor accepts `config`, it is passed through
    - otherwise it is instantiated with a zero-arg constructor
    """

    name = str(plugin_name)
    plugin_cls = _PLUGIN_REGISTRY[name]
    instance = _instantiate_plugin(plugin_cls, config)
    _validate_plugin_instance_identity(instance, expected_name=name)
    return instance


def build_policy_plugin(plugin_name: str, config: dict[str, Any] | None = None) -> Any:
    """Alias for `create_policy_plugin`."""

    return create_policy_plugin(plugin_name, config)


def get_policy_plugin(plugin_name: str):
    """Return a zero-arg factory for a registered plugin.

    This shape is accepted by the contract tests as an alternate registry API.
    """

    name = str(plugin_name)
    if name not in _PLUGIN_REGISTRY:
        raise KeyError(name)

    def _factory() -> Any:
        instance = _PLUGIN_REGISTRY[name]()
        _validate_plugin_instance_identity(instance, expected_name=name)
        return instance

    return _factory


def _coerce_plugin_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("plugin_name must be a non-empty string")
    return value.strip()


def _validate_plugin_identity_fields(plugin_cls: type[Any]) -> None:
    for attr in ("plugin_version", "supports_online_update", "supports_batch_context"):
        if not hasattr(plugin_cls, attr):
            raise ValueError(f"plugin missing required attribute: {attr}")
    plugin_version = getattr(plugin_cls, "plugin_version", None)
    if not isinstance(plugin_version, str) or not plugin_version.strip():
        raise ValueError("plugin_version must be a non-empty string")
    for attr in ("supports_online_update", "supports_batch_context"):
        value = getattr(plugin_cls, attr, None)
        if not isinstance(value, bool):
            raise ValueError(f"{attr} must be a bool")


def _instantiate_plugin(plugin_cls: type[Any], config: Mapping[str, Any] | None) -> Any:
    if config is not None:
        try:
            return plugin_cls(config=config)
        except TypeError:
            pass
    return plugin_cls()


def _validate_plugin_instance_identity(instance: Any, *, expected_name: str) -> None:
    actual_name = _coerce_plugin_name(getattr(instance, "plugin_name", None))
    if actual_name != expected_name:
        raise ValueError(
            f"plugin instance identity drift: expected plugin_name={expected_name!r}, got {actual_name!r}"
        )
    plugin_version = getattr(instance, "plugin_version", None)
    if not isinstance(plugin_version, str) or not plugin_version.strip():
        raise ValueError("plugin instance plugin_version must be a non-empty string")
    for attr in ("supports_online_update", "supports_batch_context"):
        if not isinstance(getattr(instance, attr, None), bool):
            raise ValueError(f"plugin instance {attr} must be a bool")
