"""Azure ML helpers shared by pipeline steps and scripts.

Layer 3: provider SDKs may be imported here and nowhere in src/. Everything is imported
lazily so that `import cloudlayer.azure_ops` costs nothing on a machine without the SDK.
"""
from __future__ import annotations

import os
from typing import Any


def credential():
    """Inside a pipeline step the compute cluster carries a user-assigned identity;
    UAI_CLIENT_ID selects it. On your laptop this falls back to `az login`."""
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

    client_id = os.environ.get("UAI_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return DefaultAzureCredential()


def ml_client():
    from azure.ai.ml import MLClient

    return MLClient(
        credential(),
        os.environ["AZURE_SUBSCRIPTION_ID"],
        os.environ["AZURE_RESOURCE_GROUP"],
        os.environ["AZURE_ML_WORKSPACE"],
    )


def incumbent(name: str, stage: str) -> tuple[str, dict[str, str]] | None:
    """Newest registered version of `name` tagged stage=<stage>, as (version, tags).
    None when no such version exists. Raises when the registry cannot be read."""
    best: tuple[int, Any] | None = None
    for model in ml_client().models.list(name=name):
        if (model.tags or {}).get("stage") != stage:
            continue
        if best is None or int(model.version) > best[0]:
            best = (int(model.version), model)
    if best is None:
        return None
    return str(best[0]), dict(best[1].tags or {})


def register_model(model_dir: str, name: str, tags: dict[str, str], description: str) -> str:
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.entities import Model

    model = Model(path=model_dir, name=name, type=AssetTypes.CUSTOM_MODEL,
                  tags=tags, description=description)
    return str(ml_client().models.create_or_update(model).version)


def set_stage(name: str, version: str, stage: str) -> None:
    client = ml_client()
    model = client.models.get(name=name, version=version)
    tags = dict(model.tags or {})
    tags["stage"] = stage
    model.tags = tags
    client.models.create_or_update(model)


def ensure_cluster(name: str, size: str, tags: dict[str, str], uai_resource_id: str,
                   min_nodes: int = 0, max_nodes: int = 1, idle_seconds: int = 120):
    """Dedicated cluster, scales to zero, carries the training identity and the lab tags."""
    from azure.ai.ml.entities import AmlCompute, IdentityConfiguration, ManagedIdentityConfiguration

    compute = AmlCompute(
        name=name, size=size, tier="dedicated",
        min_instances=min_nodes, max_instances=max_nodes,
        idle_time_before_scale_down=idle_seconds, tags=tags,
        identity=IdentityConfiguration(
            type="user_assigned",
            user_assigned_identities=[ManagedIdentityConfiguration(resource_id=uai_resource_id)],
        ),
    )
    return ml_client().compute.begin_create_or_update(compute).result()


def delete_schedules(prefix: str) -> list[str]:
    from azure.ai.ml.operations._schedule_operations import ScheduleListViewType

    client = ml_client()
    gone = []
    # the default view lists ENABLED schedules only; disabled ones must be removed too
    for sched in client.schedules.list(list_view_type=ScheduleListViewType.ALL):
        if sched.name.startswith(prefix):
            client.schedules.begin_delete(sched.name).result()
            gone.append(f"schedule:{sched.name}")
    return gone
