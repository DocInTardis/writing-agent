"""Resource Scheduler module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.

Captures real system resource metrics via psutil and translates them into
scheduling decisions used by the graph runner to throttle section-level
concurrency and apply back-pressure when the host is under load.

Environment variable overrides (useful in tests / CI):
  WRITING_AGENT_CPU_PERCENT        - override CPU reading (float, 0-100)
  WRITING_AGENT_MEM_PERCENT        - override memory reading (float, 0-100)
  WRITING_AGENT_GPU_AVAILABLE      - override GPU flag (0/1)
  WRITING_AGENT_MODEL_SERVICE_LOAD - override model service load (float, 0-1)
  WRITING_AGENT_FAST_CPU           - high-pressure CPU threshold (default 85)
  WRITING_AGENT_FAST_MEM           - high-pressure memory threshold (default 85)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_snapshot_lock = threading.Lock()
_cached_snapshot: ResourceSnapshot | None = None
_cached_snapshot_ts: float = 0.0
_SNAPSHOT_TTL_S = 2.0  # reuse snapshot within 2 s to avoid repeated 100 ms psutil calls

# Thresholds read from env at module level for efficiency.
_CPU_HIGH_THRESHOLD = float(os.environ.get("WRITING_AGENT_FAST_CPU", "85") or "85")
_MEM_HIGH_THRESHOLD = float(os.environ.get("WRITING_AGENT_FAST_MEM", "85") or "85")
_CPU_MED_THRESHOLD = _CPU_HIGH_THRESHOLD * 0.76  # ~65% when default is 85


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    mem_percent: float
    gpu_available: bool
    model_service_load: float


@dataclass(frozen=True)
class SchedulingDecision:
    worker_count: int
    prefer_gpu: bool
    queue_backpressure: bool


def _read_real_cpu() -> float:
    """Return current CPU utilisation percent (non-blocking, 0.1s interval)."""
    try:
        import psutil
        return float(psutil.cpu_percent(interval=0.1))
    except Exception as exc:
        logger.debug("resource_scheduler: psutil cpu_percent failed: %s", exc)
        return 35.0


def _read_real_mem() -> float:
    """Return current memory utilisation percent."""
    try:
        import psutil
        return float(psutil.virtual_memory().percent)
    except Exception as exc:
        logger.debug("resource_scheduler: psutil virtual_memory failed: %s", exc)
        return 40.0


def _detect_gpu() -> bool:
    """Best-effort GPU detection: checks nvidia-smi availability."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, timeout=2,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def capture_resource_snapshot() -> ResourceSnapshot:
    """Read current host resource state.

    Environment variable overrides take precedence over psutil readings,
    allowing deterministic behaviour in tests and CI.
    """
    # CPU
    cpu_override = str(os.environ.get("WRITING_AGENT_CPU_PERCENT", "") or "").strip()
    if cpu_override:
        try:
            cpu = float(cpu_override)
        except ValueError:
            cpu = _read_real_cpu()
    else:
        cpu = _read_real_cpu()

    # Memory
    mem_override = str(os.environ.get("WRITING_AGENT_MEM_PERCENT", "") or "").strip()
    if mem_override:
        try:
            mem = float(mem_override)
        except ValueError:
            mem = _read_real_mem()
    else:
        mem = _read_real_mem()

    # GPU
    gpu_override = str(os.environ.get("WRITING_AGENT_GPU_AVAILABLE", "") or "").strip().lower()
    if gpu_override:
        gpu = gpu_override in {"1", "true", "yes", "on"}
    else:
        gpu = _detect_gpu()

    # Model service load (no real sensor yet — env override or default)
    try:
        load = float(str(os.environ.get("WRITING_AGENT_MODEL_SERVICE_LOAD", "0.3") or "0.3"))
    except ValueError:
        load = 0.3

    snapshot = ResourceSnapshot(
        cpu_percent=cpu,
        mem_percent=mem,
        gpu_available=gpu,
        model_service_load=load,
    )
    logger.debug(
        "resource_scheduler: cpu=%.1f%% mem=%.1f%% gpu=%s load=%.2f",
        snapshot.cpu_percent, snapshot.mem_percent, snapshot.gpu_available, snapshot.model_service_load,
    )
    return snapshot


def _cached_capture_resource_snapshot() -> ResourceSnapshot:
    """Return a recent ResourceSnapshot, reusing the cached value within _SNAPSHOT_TTL_S."""
    global _cached_snapshot, _cached_snapshot_ts
    now = time.monotonic()
    with _snapshot_lock:
        if _cached_snapshot is not None and (now - _cached_snapshot_ts) < _SNAPSHOT_TTL_S:
            return _cached_snapshot
        snapshot = capture_resource_snapshot()
        _cached_snapshot = snapshot
        _cached_snapshot_ts = now
        return snapshot


def recommended_workers() -> int:
    """Convenience wrapper: return the advised worker count.

    Uses a 2-second TTL cache to avoid repeated 100 ms psutil CPU measurements
    when called multiple times within a single request.
    """
    return schedule(_cached_capture_resource_snapshot()).worker_count


def schedule(snapshot: ResourceSnapshot) -> SchedulingDecision:
    """Translate a resource snapshot into a concrete scheduling decision.

    Worker count tiers:
      - High pressure (CPU or MEM above high threshold): 2 workers, back-pressure on
      - Medium pressure (CPU or MEM above medium threshold): 4 workers
      - Normal: use WRITING_AGENT_WORKERS env var (default 8)
    """
    try:
        max_workers = max(1, int(str(os.environ.get("WRITING_AGENT_WORKERS", "8") or "8")))
    except ValueError:
        max_workers = 8

    prefer_gpu = snapshot.gpu_available and snapshot.model_service_load < 0.85
    high_pressure = snapshot.cpu_percent > _CPU_HIGH_THRESHOLD or snapshot.mem_percent > _MEM_HIGH_THRESHOLD
    med_pressure = snapshot.cpu_percent > _CPU_MED_THRESHOLD or snapshot.mem_percent > (_MEM_HIGH_THRESHOLD * 0.76)

    if high_pressure:
        return SchedulingDecision(worker_count=min(2, max_workers), prefer_gpu=prefer_gpu, queue_backpressure=True)
    if med_pressure:
        return SchedulingDecision(worker_count=min(4, max_workers), prefer_gpu=prefer_gpu, queue_backpressure=False)
    return SchedulingDecision(worker_count=max_workers, prefer_gpu=prefer_gpu, queue_backpressure=False)
