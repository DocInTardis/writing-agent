"""Resource Scheduler module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    gpu_available: bool
    model_service_load: float


@dataclass(frozen=True)
class SchedulingDecision:
    worker_count: int
    prefer_gpu: bool
    queue_backpressure: bool


def capture_resource_snapshot() -> ResourceSnapshot:
    cpu = float(os.environ.get("WRITING_AGENT_CPU_PERCENT", "35"))
    gpu = str(os.environ.get("WRITING_AGENT_GPU_AVAILABLE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    load = float(os.environ.get("WRITING_AGENT_MODEL_SERVICE_LOAD", "0.3"))
    return ResourceSnapshot(cpu_percent=cpu, gpu_available=gpu, model_service_load=load)


def schedule(snapshot: ResourceSnapshot) -> SchedulingDecision:
    prefer_gpu = snapshot.gpu_available and snapshot.model_service_load < 0.85
    if snapshot.cpu_percent > 85:
        return SchedulingDecision(worker_count=2, prefer_gpu=prefer_gpu, queue_backpressure=True)
    if snapshot.cpu_percent > 65:
        return SchedulingDecision(worker_count=4, prefer_gpu=prefer_gpu, queue_backpressure=False)
    return SchedulingDecision(worker_count=8, prefer_gpu=prefer_gpu, queue_backpressure=False)
