from typing import TypeVar
from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from tudelft.utilities.immutablelist.SubList import SubList
T=TypeVar("T")

class PowerSet(AbstractImmutableList[ImmutableList[T]]):
	'''
	the power set (or powerset) of any set S is the set of all subsets of S,
	including the empty set and S itself. The given list is assumed to be a set,
	so without duplicates.
	
	@param T the element type of all lists that we receive.
	'''


	def __init__(self, list:ImmutableList[T] ) :
		self._list = list

	def get(self, index:int) -> ImmutableList[T] :
		if index >= self.size():
			raise IndexError("Index out of bounds:" + str(index))
		return SubList[T](self._list, index)

	def size(self)->int:
		return 1 << self._list.size()

	def __hash__(self):
		return 17*hash(list)


	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._list==other._list
