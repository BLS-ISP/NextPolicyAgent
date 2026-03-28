"""Storage interface for NPA.

Defines the abstract storage contract that all backends must implement.
Supports transactions with isolation for concurrent access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Generator


class StorageError(Exception):
    pass


class NotFoundError(StorageError):
    pass


class ConflictError(StorageError):
    """Raised on write conflicts in transactions."""


class TxnMode(Enum):
    READ = auto()
    WRITE = auto()


@dataclass
class StorageEvent:
    """Describes a mutation to the store."""
    op: str  # "add", "remove", "replace"
    path: list[str]
    value: Any = None


class Transaction(ABC):
    """Abstract transaction with read/write operations."""

    @abstractmethod
    def read(self, path: list[str]) -> Any:
        """Read a value at the given path."""

    @abstractmethod
    def write(self, op: str, path: list[str], value: Any = None) -> None:
        """Write (add/remove/replace) a value at the given path."""

    @abstractmethod
    def commit(self) -> list[StorageEvent]:
        """Commit the transaction, returning all events."""

    @abstractmethod
    def abort(self) -> None:
        """Abort the transaction, discarding all changes."""


class Storage(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def read(self, path: list[str]) -> Any:
        """Read a value at the given path (outside transaction)."""

    @abstractmethod
    def begin(self, mode: TxnMode = TxnMode.READ) -> Transaction:
        """Begin a new transaction."""

    @contextmanager
    def transaction(self, mode: TxnMode = TxnMode.READ) -> Generator[Transaction, None, None]:
        """Context manager for transactions with automatic commit/abort."""
        txn = self.begin(mode)
        try:
            yield txn
            txn.commit()
        except Exception:
            txn.abort()
            raise

    @abstractmethod
    def list_policies(self) -> dict[str, str]:
        """Return all stored policies as {id: raw_rego}."""

    @abstractmethod
    def upsert_policy(self, policy_id: str, raw: str) -> None:
        """Store or update a policy."""

    @abstractmethod
    def delete_policy(self, policy_id: str) -> None:
        """Delete a policy."""

    @abstractmethod
    def get_policy(self, policy_id: str) -> str:
        """Get a specific policy's raw Rego source."""
