from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Generic, Iterator, TypeVar


E = TypeVar("E")


class ImmutableList(ABC, Generic[E]):
    """
    Immutable (read-only) list. Implementations are possibly procedural, and can
    therefore "hold" infinite number of items.

    @param <E> type of the contained elements
    """

    @abstractmethod
    def get(self, index: int) -> E:
        """
        Returns the element at the specified position in this list. 0 based
        @param index index of the element to return, 0 is the first element.
        @return the element at the specified position in this list.
        Notice that the python int is not limited in size.
        @throws IndexOutOfBoundsException if the index is out of range
                          (<tt>index &lt; 0 || index &gt;= size()</tt>)
        """

    @abstractmethod
    def size(self) -> int:
        """
        @return the number of elements in this list.
        """

    @abstractmethod
    def __iter__(self) -> Iterator[E]:
        """
        iterates over the objects in the list
        """
