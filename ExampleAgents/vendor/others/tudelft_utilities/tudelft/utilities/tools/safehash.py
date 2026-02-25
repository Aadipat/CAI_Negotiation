"""
Safe hash function for Python objects.

This module provides a hash function that safely handles mutable objects
by converting them to immutable equivalents before hashing.
"""

from typing import Any


def safehash(obj: Any) -> int:
    """
    Calculate a hash for an object, handling mutable types safely.

    For mutable objects like lists and dicts, converts them to immutable
    equivalents (tuples, frozensets) before hashing.

    Args:
        obj: The object to hash.

    Returns:
        An integer hash value.
    """
    if obj is None:
        return 0

    # Handle lists by converting to tuple
    if isinstance(obj, list):
        return hash(tuple(safehash(item) for item in obj))

    # Handle dicts by converting to frozenset of tuples
    if isinstance(obj, dict):
        return hash(frozenset((k, safehash(v)) for k, v in obj.items()))

    # Handle sets by converting to frozenset
    if isinstance(obj, set):
        return hash(frozenset(safehash(item) for item in obj))

    # For objects with __hash__, use it directly
    try:
        return hash(obj)
    except TypeError:
        # Fallback: use id for unhashable objects
        return id(obj)
