from typing import TypeVar, Generic, Callable
from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
IN1 = TypeVar('IN1')
OUT = TypeVar('OUT')

class MapList(Generic[IN1, OUT],  AbstractImmutableList[OUT]):
	'''
	@param <IN1> the type of the elements inside the argument list
	@param <OUT> the output type of the function
	
	'''

	def __init__(self,  f:Callable[[IN1], OUT], list1: ImmutableList[IN1]):
		'''
		creates a list [f(a1), f(a2) ,. ..., f(an)].
		
		@param f     {@link Function}. Note, previously this was our own Function
		             class, which was identical to the new one built in in Java.
		@param list1 a list of items [a1,a2,..., an]
		'''
		if f == None or list1 == None:
			raise ValueError("null argument")
		self._list1 = list1
		self._f = f

	#Override
	def get(self, index:int) -> OUT :
		return self._f(self._list1.get(index))

	#Override
	def size(self)->int:
		return self._list1.size()

	#Override
	def __hash__(self):
		return hash((self._list1, self._f))

	#Override
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._list1 == other._list1 \
			and self._f == other._f

