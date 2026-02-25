from typing import TypeVar, Generic, List
from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList

E = TypeVar('E')

class JoinedList(Generic[E], AbstractImmutableList[E]):
	'''
	Creates conjunction of lists. Eg Join of [1,2],[3,4],[5] -> [1,2,3,4,5]
	
	@param <E> type of the elements
	'''

	def __init__(self,  items: List[ImmutableList[E]]):
		self._lists = items.copy()
		self._size= sum([l.size() for l in items ] )


	#Override
	def get(self , index:int) ->E :
		remaining = index

		for list in self._lists:
			s = list.size()
			if remaining < s:
				return list.get(remaining)
			remaining = remaining-s
		raise IndexError("" + str(index))

	def With( self, list:ImmutableList[E]) -> "JoinedList[E]" :
		'''
		@param list the list to add
		@return new JoinedList with the given list added at end of existing
		        lists.
		'''
		newlists = self._lists.copy()
		newlists.append(list)
		return JoinedList(newlists)

	#Override
	def size(self) ->int:
		return self._size

	#@Override
	def __hash__(self):
		return hash( (self._size, tuple(self._lists)))

	#Override
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._lists == other._lists

