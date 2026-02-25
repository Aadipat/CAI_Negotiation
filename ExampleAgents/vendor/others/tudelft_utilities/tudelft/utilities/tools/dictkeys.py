"""
Dictionary keys utility module.

Provides a Keys class for iterating over dictionary keys in a type-safe way.
"""

from typing import Any, Iterator, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class Keys:
    """
    A wrapper for dictionary keys that provides iteration.

    This is used for Java compatibility where Maps have a keySet() method.
    In Python, we just wrap dict.keys() but provide a class interface.
    """

    def __init__(self, d: dict[K, V]):
        """
        Initialize with a dictionary.

        Args:
            d: The dictionary to get keys from.
        """
        self._keys = list(d.keys())

    def __iter__(self) -> Iterator[K]:
        """Iterate over the keys."""
        return iter(self._keys)

    def __len__(self) -> int:
        """Get number of keys."""
        return len(self._keys)

    def __contains__(self, item: Any) -> bool:
        """Check if key exists."""
        return item in self._keys
