"""In-memory storage backend.

Thread-safe, copy-on-write store for development and testing.
Uses deep copy on write transactions for snapshot isolation.
"""

from __future__ import annotations

import copy
import threading
from typing import Any

from npa.storage.base import (
    ConflictError,
    NotFoundError,
    Storage,
    StorageEvent,
    Transaction,
    TxnMode,
)


class InMemoryTransaction(Transaction):
    """Transaction operating on a snapshot of the data."""

    def __init__(self, data: dict, policies: dict[str, str], mode: TxnMode) -> None:
        self._data = copy.deepcopy(data) if mode == TxnMode.WRITE else data
        self._policies = dict(policies) if mode == TxnMode.WRITE else policies
        self._mode = mode
        self._events: list[StorageEvent] = []
        self._committed = False
        self._aborted = False

    def read(self, path: list[str]) -> Any:
        return _walk(self._data, path)

    def write(self, op: str, path: list[str], value: Any = None) -> None:
        if self._mode == TxnMode.READ:
            raise ConflictError("Cannot write in a read transaction")
        if op == "add" or op == "replace":
            _set_path(self._data, path, value)
        elif op == "remove":
            _del_path(self._data, path)
        self._events.append(StorageEvent(op=op, path=list(path), value=value))

    def commit(self) -> list[StorageEvent]:
        self._committed = True
        return list(self._events)

    def abort(self) -> None:
        self._aborted = True
        self._events.clear()

    @property
    def data(self) -> dict:
        return self._data

    @property
    def policies(self) -> dict[str, str]:
        return self._policies


class InMemoryStorage(Storage):
    """Thread-safe in-memory storage with copy-on-write transactions."""

    def __init__(self, initial_data: dict | None = None) -> None:
        self._data: dict = initial_data or {}
        self._policies: dict[str, str] = {}
        self._lock = threading.RLock()

    def read(self, path: list[str]) -> Any:
        with self._lock:
            return _walk(self._data, path)

    def begin(self, mode: TxnMode = TxnMode.READ) -> InMemoryTransaction:
        with self._lock:
            return InMemoryTransaction(self._data, self._policies, mode)

    def list_policies(self) -> dict[str, str]:
        with self._lock:
            return dict(self._policies)

    def upsert_policy(self, policy_id: str, raw: str) -> None:
        with self._lock:
            self._policies[policy_id] = raw

    def delete_policy(self, policy_id: str) -> None:
        with self._lock:
            if policy_id not in self._policies:
                raise NotFoundError(f"Policy not found: {policy_id}")
            del self._policies[policy_id]

    def get_policy(self, policy_id: str) -> str:
        with self._lock:
            if policy_id not in self._policies:
                raise NotFoundError(f"Policy not found: {policy_id}")
            return self._policies[policy_id]

    def patch_data(self, path: list[str], value: Any) -> list[StorageEvent]:
        """Convenience method for simple data patches."""
        with self._lock:
            txn = self.begin(TxnMode.WRITE)
            txn.write("replace" if _path_exists(self._data, path) else "add", path, value)
            events = txn.commit()
            self._data = txn.data
            return events

    def remove_data(self, path: list[str]) -> list[StorageEvent]:
        with self._lock:
            txn = self.begin(TxnMode.WRITE)
            txn.write("remove", path, None)
            events = txn.commit()
            self._data = txn.data
            return events


# ===========================================================================
# Helpers
# ===========================================================================

def _walk(data: Any, path: list[str]) -> Any:
    """Walk into nested data following path segments."""
    current = data
    for segment in path:
        if isinstance(current, dict):
            if segment not in current:
                raise NotFoundError(f"Path not found: /{'/'.join(path)}")
            current = current[segment]
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise NotFoundError(f"Path not found: /{'/'.join(path)}") from exc
        else:
            raise NotFoundError(f"Cannot traverse into {type(current).__name__}")
    return current


def _set_path(data: dict, path: list[str], value: Any) -> None:
    """Set a value at a nested path, creating intermediate dicts."""
    if not path:
        return
    current = data
    for segment in path[:-1]:
        if segment not in current or not isinstance(current.get(segment), dict):
            current[segment] = {}
        current = current[segment]
    current[path[-1]] = value


def _del_path(data: dict, path: list[str]) -> None:
    """Delete a value at a nested path."""
    if not path:
        data.clear()
        return
    current = data
    for segment in path[:-1]:
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return
    if isinstance(current, dict):
        current.pop(path[-1], None)


def _path_exists(data: Any, path: list[str]) -> bool:
    try:
        _walk(data, path)
        return True
    except NotFoundError:
        return False
