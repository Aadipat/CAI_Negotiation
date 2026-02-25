"""
ProductOfValue - A Value that is the product of some existing values.

Simplified version without external dependencies.
"""

from __future__ import annotations

from typing import Any, List, Optional

from geniusweb.issuevalue.Value import Value


class ProductOfValue(Value):
    """
    A Value that is the product of some existing values. This is usually
    an intermediate representation of a possibly partial Bid.
    """

    def __init__(self, newvals: List[Optional[Value]]):
        self._values: List[Optional[Value]] = list(newvals)

    def getValues(self) -> List[Optional[Value]]:
        return list(self._values)

    def __repr__(self) -> str:
        return str(self._values)

    def merge(self, other: ProductOfValue) -> ProductOfValue:
        """
        Merge this ProductOfValue with another.

        Args:
            other: a ProductOfValue with more issues to be merged into this.

        Returns:
            new ProductOfValue that contains this and other values.
        """
        newvalues: List[Optional[Value]] = list(self._values)
        newvalues.extend(other.getValues())
        return ProductOfValue(newvalues)

    def getValue(self) -> Any:
        return self.getValues()

    def __hash__(self) -> int:
        # Convert list to tuple for hashing
        return hash(tuple(self._values))

    def __eq__(self, obj: Optional[Any]) -> bool:
        if self is obj:
            return True
        if obj is None:
            return False
        if type(self) is not type(obj):
            return False
        return self._values == obj._values
