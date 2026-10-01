"""Bounded fan-out. A slot remains occupied until the worker execution terminates."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import dataclass
from threading import Event
from typing import Protocol

from src.control_plane.model import PIPELINES, StoreConfig, Window
from src.control_plane.registry import Registry
from src.domain.models import SafeError
from src.observability.logging import event


class Gateway(Protocol):
    def run_and_wait(self, pipeline: str, config: StoreConfig, window: Window) -> bool: ...


@dataclass(frozen=True)
class DispatchResult:
    store_id: str
    pipeline: str
    status: str


class Dispatcher:
    def __init__(
        self,
        registry: Registry,
        gateway: Gateway,
        prerequisites: Callable[[StoreConfig, str, Window], None],
        lease: Callable[[str], AbstractContextManager[None]],
        max_parallel_stores: int = 2,
    ):
        if type(max_parallel_stores) is not int or not 1 <= max_parallel_stores <= 10:
            raise SafeError("invalid_parallel_store_limit")
        self.registry, self.gateway, self.prerequisites, self.lease = (
            registry,
            gateway,
            prerequisites,
            lease,
        )
        self.max_parallel = max_parallel_stores

    def run(
        self, pipeline: str, windows: Callable[[StoreConfig], Window], limit: int = 1000
    ) -> list[DispatchResult]:
        if pipeline not in PIPELINES:
            raise SafeError("invalid_pipeline")
        # Shared across ALL central pipelines. Concurrent dispatchers cannot each launch N.
        with self.lease("store-dispatch-global"):
            stores = self.registry.eligible(pipeline, limit)
            if len({c.store_id for c in stores}) != len(stores) or any(
                not c.eligible(pipeline) for c in stores
            ):
                raise SafeError("invalid_dispatch_registry")

            stop = Event()

            def execute(config: StoreConfig) -> DispatchResult:
                if stop.is_set():
                    raise SafeError("worker_execution_outcome_unknown")
                try:
                    window = windows(config)
                    self.prerequisites(config, pipeline, window)
                    if stop.is_set():
                        raise SafeError("worker_execution_outcome_unknown")
                    status = (
                        "completed"
                        if self.gateway.run_and_wait(pipeline, config, window)
                        else "failed"
                    )
                except SafeError as exc:
                    if exc.code == "worker_execution_outcome_unknown":
                        stop.set()
                        raise
                    status = "blocked"
                except Exception:
                    status = "blocked"
                event(
                    "store_dispatch_finished",
                    store_id=config.store_id,
                    pipeline=pipeline,
                    status=status,
                )
                return DispatchResult(config.store_id, pipeline, status)

            with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
                # Futures may be queued, but only max_parallel remote executions are in flight.
                return list(pool.map(execute, stores))
