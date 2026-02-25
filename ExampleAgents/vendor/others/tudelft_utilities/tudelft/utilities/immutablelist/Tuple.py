from typing import TypeVar, Generic

T1 = TypeVar('T1')
T2 = TypeVar('T2')


class Tuple(Generic[T1,T2]):
	'''
	tuple with two elements of different types. Immutable
	@param <T1> type of the first element of the tuple
	@param <T2> type of the second element of the tuple
	'''

	def __init__(self, element1:T1 , element2:T2 ):
		self._element1 = element1
		self._element2 = element2

	def get1(self) -> T1:
		return self._element1

	def get2(self)->T2  :
		return self._element2

	def __repr__(self)->str:
		return "<" + str(self._element1) + "," + str(self._element2) + ">"

	def __hash__(self):
		return hash((self._element1, self._element2))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._element1==other._element1\
			and self._element2==other._element2
