from decimal import Decimal

from tudelft.utilities.immutablelist.Range import Range

from geniusweb.issuevalue.NumberValue import NumberValue
from geniusweb.issuevalue.ValueSet import ValueSet


class NumberValueSet ( ValueSet ):
	'''
	number range from low to high with given step size
	'''
	def __init__(self,  range:Range ):
		if not isinstance(range, Range):
			raise ValueError("range must be type Range but got "+repr(range))
		self._range = range;

	def getRange(self)->Range :
		'''	 
		@return the range defining this NumberValueSet.
		'''
		return self._range

	def get(self, index:int) -> NumberValue :
		return NumberValue(self._range.get(index))
	
	def size(self) -> int:
		return self._range.size()

	def __repr__(self) -> str :
		return "NumberValueSet[" + str(self._range.getLow()) + "," +\
			 str(self._range.getHigh()) + "," + str(self._range.getStep()) + "]"

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			 self._range == other._range

	def __hash__(self):
		return hash(self._range)
	