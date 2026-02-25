from typing import TypeVar

from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList


def  bitCount(n:int):
	'''
	@return number of 1's in binary representation of number 
	'''
	count = 0
	while (n):
		count += n & 1
		n >>= 1
	return count
   
   
T=TypeVar("T")
class SubList(AbstractImmutableList[T]):
	'''
	Selects a specific sublist of the given list.
	This is a sort of subset, but the original order of the elements is
	maintained. Notice this is not a cheap operation.
	
	@param T the element type of all lists that we receive.
	'''
	
	def __init__(self, lis: ImmutableList[T], selection:int):
		'''
		@param lis      the list to take the subset of. The list size must be
		     &le; {@link Integer#MAX_VALUE} elements
		@param selection a number. When interpreted binary, eg 1011, the 1's
		     indicate selected elements and 0's non-selected
		     elements. This number should be in the range
		     0..2^(|list|+1).
		'''
		self._list = lis
		self._selection = selection

	def get(self, index:int) -> T:
		return self._list.get(self._getIndex(index))


	def _getIndex(self, n1:int)->int:
		'''
		@param n the index in our list. We use int as int's are used anyway
		         internally in BigInteger for indexing bits.
		@return the index in the original array, which is the index of the nth 1
		        in the selection number. NOTICE this is expensive operation as we
		        have to iterate to get to the required element.
		'''
		n = n1
		for i in range(self._selection.bit_length()):
			if self._selection >>i & 1:
				if n == 0:
					return i
				n-=1
		raise IndexError("Index out of bounds:" + str(n1))

	def  size(self) -> int:
		return bitCount(self._selection)

	def getSelection(self) -> int:
		return self._selection

	def complement(self)-> "SubList[T]" :
		'''
		@return list with all elements from list that were not selected now
		        selected, and those that were selected now not selected.
		'''
		# do 111111 XOR the selection.
		sel = (1<<self._list.size()) - 1
		sel = sel ^ self._selection
		return SubList[T](self._list,sel)

	def __hash__(self):
		return hash((self._list, self._selection))
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._list==other._list\
			and self._selection==other._selection
