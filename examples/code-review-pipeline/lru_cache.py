# LRU Cache Implementation — FINAL (APPROVED)
# Uses collections.OrderedDict for O(1) get, put, and delete operations.
# Python 3.7+ (OrderedDict is guaranteed insertion-ordered in 3.7+)

from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar, Optional

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """A bounded Least Recently Used (LRU) cache.

    Stores key-value pairs up to a fixed *capacity*. When the cache is full,
    inserting a new key evicts the least recently used entry. Both ``get``
    and ``put`` refresh the recency of the accessed key.

    Thread safety: this implementation is **not** thread-safe. Wrap with
    ``threading.Lock`` or use ``functools.lru_cache`` for concurrency.

    Parameters
    ----------
    capacity : int
        Maximum number of entries. Must be >= 1.

    Raises
    ------
    ValueError
        If *capacity* < 1.
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be >= 1, got {capacity}")
        self._capacity: int = capacity
        self._store: OrderedDict[K, V] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Return the value for *key*, or *default* if the key is absent.

        Accessing a key marks it as most recently used.

        Using a caller-defined *default* (e.g. a unique sentinel) allows
        disambiguation between a missing key and a stored ``None`` value.

        Parameters
        ----------
        key : K
            Lookup key.
        default : Optional[V]
            Value to return when *key* is not found (default ``None``).

        Returns
        -------
        Optional[V]
            The cached value, or *default*.
        """
        if key not in self._store:
            return default
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: K, value: V) -> None:
        """Insert or update *key* with *value*.

        - If *key* already exists its value is updated and it becomes the
          most recently used entry.
        - If the cache is at capacity, the **least recently used** entry
          is evicted before insertion.

        Parameters
        ----------
        key : K
            Cache key.
        value : V
            Value to associate with *key*.
        """
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._capacity:
            self._store.popitem(last=False)

    def delete(self, key: K) -> bool:
        """Remove *key* from the cache.

        This operation does **not** affect recency order for remaining keys.

        Parameters
        ----------
        key : K
            Key to remove.

        Returns
        -------
        bool
            ``True`` if the key was present and removed, ``False`` otherwise.
        """
        if key not in self._store:
            return False
        del self._store[key]
        return True

    # ------------------------------------------------------------------
    # Introspection helpers (non-essential but useful)
    # ------------------------------------------------------------------

    @property
    def capacity(self) -> int:
        """Maximum number of entries the cache can hold."""
        return self._capacity

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._store)

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: K) -> bool:
        return key in self._store

    def __repr__(self) -> str:
        return f"LRUCache(capacity={self._capacity}, size={len(self._store)})"


# ------------------------------------------------------------------
# Quick smoketest (not part of the public API)
# ------------------------------------------------------------------
if __name__ == "__main__":
    cache = LRUCache[int, str](2)

    assert cache.get(1) is None
    cache.put(1, "a")
    assert cache.get(1) == "a"

    cache.put(2, "b")
    cache.put(3, "c")          # evicts key 1
    assert cache.get(1) is None
    assert cache.get(2) == "b"
    assert cache.get(3) == "c"

    cache.put(4, "d")          # evicts key 2 (3 was used more recently)
    assert cache.get(2) is None
    assert cache.get(3) == "c"
    assert cache.get(4) == "d"

    assert cache.delete(3) is True
    assert cache.delete(3) is False
    assert cache.get(3) is None
    assert cache.size == 1

    print("All smoketests passed.")
