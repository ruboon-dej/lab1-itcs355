"""Provider-neutral model-registry operations used by the gate, register and promote steps.
Only Azure is implemented; the other providers fail loudly instead of guessing."""
from __future__ import annotations


def _azure():
    from cloudlayer import azure_ops
    return azure_ops


def _backend(provider: str):
    if provider == "azure":
        return _azure()
    raise NotImplementedError(f"registry operations are not implemented for provider {provider!r}")


def incumbent(provider: str, name: str, stage: str):
    return _backend(provider).incumbent(name, stage)


def register(provider: str, model_dir: str, name: str, tags: dict, description: str) -> str:
    return _backend(provider).register_model(model_dir, name, tags, description)


def promote(provider: str, name: str, version: str, stage: str) -> None:
    _backend(provider).set_stage(name, version, stage)
