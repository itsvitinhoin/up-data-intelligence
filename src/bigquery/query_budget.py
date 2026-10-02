"""Atomic execution accounting: reserve worst case, settle only confirmed billing."""

from dataclasses import dataclass
from threading import Lock


class QueryBudgetExceeded(ValueError):
    def __init__(self) -> None:
        super().__init__("query_budget_exhausted_or_invalid")


@dataclass(frozen=True, eq=False)
class Reservation:
    ceiling: int


class QueryBudget:
    def __init__(self, maximum_total_bytes: int | None):
        if maximum_total_bytes is not None and (
            type(maximum_total_bytes) is not int or maximum_total_bytes <= 0
        ):
            raise ValueError("invalid_execution_budget")
        self.maximum_total_bytes = maximum_total_bytes
        self._lock = Lock()
        self._active: set[Reservation] = set()
        self._settled = 0
        self._unresolved = 0
        self._invalid = False

    def reserve(self, maximum_query_bytes: int) -> Reservation:
        if type(maximum_query_bytes) is not int or maximum_query_bytes <= 0:
            raise ValueError("invalid_query_reservation")
        with self._lock:
            self._reserve_bytes(maximum_query_bytes)
            token = Reservation(maximum_query_bytes)
            self._active.add(token)
            return token

    def _reserve_bytes(self, value: int) -> None:
        if self._invalid or (
            self.maximum_total_bytes is not None
            and self._settled + self._unresolved + value > self.maximum_total_bytes
        ):
            raise QueryBudgetExceeded()
        self._unresolved += value

    def _owned(self, reservation: Reservation) -> None:
        if reservation not in self._active:
            raise ValueError("query_budget_reservation_not_active")

    def settle(self, reservation: Reservation, billed_bytes: object) -> bool:
        with self._lock:
            self._owned(reservation)
            if self._invalid:
                raise QueryBudgetExceeded()
            # bool, strings/floats and missing metadata are not confirmed billing.
            if type(billed_bytes) is not int or billed_bytes < 0:
                return False
            if billed_bytes > reservation.ceiling:
                self._invalid = True
                raise QueryBudgetExceeded()
            self._active.remove(reservation)
            self._unresolved -= reservation.ceiling
            self._settled += billed_bytes
            return True

    def retain(self, reservation: Reservation) -> None:
        with self._lock:
            self._owned(reservation)

    def import_accounted(self, value: int) -> None:
        """Legacy external reads may add unknown cost, never release tracked cost."""
        with self._lock:
            current = self._settled + self._unresolved
            if type(value) is not int or value < current:
                raise ValueError("invalid_imported_query_budget")
            if value > current:
                self._reserve_bytes(value - current)

    def metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "settled_billed_bytes": self._settled,
                "unresolved_reserved_bytes": self._unresolved,
                "budget_accounted_bytes": self._settled + self._unresolved,
            }

    @property
    def settled_billed_bytes(self) -> int:
        return self.metrics()["settled_billed_bytes"]

    @property
    def unresolved_reserved_bytes(self) -> int:
        return self.metrics()["unresolved_reserved_bytes"]

    @property
    def accounted_bytes(self) -> int:
        return self.metrics()["budget_accounted_bytes"]
