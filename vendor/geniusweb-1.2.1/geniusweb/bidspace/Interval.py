from decimal import Decimal
from math import floor, ceil
from typing import Optional

class Interval:
	'''
	An interval [min, max].
	'''
	#ZERO = Interval(0,0) can't be done in Python...


	def __init__(self, min:Decimal, max:Decimal):
		'''
		AN interval [min,max]. If min &gt; max, then there are no values in this
		interval.
		
		@param min the minimum value of the interval
		@param max the maximum value of the interval
		'''
		if min == None or max == None:
			raise ValueError("min and max must contain not None")
		self._min = min
		self._max = max

	def getMin(self)->Decimal :
		'''
		@return the minimum value of the interval
		'''
		return self._min

	def getMax(self) ->Decimal :
		'''
		@return the maximum value of the interval
		'''
		return self._max

	def isEmpty(self)->bool :
		'''
	 	@return true iff this range does not contain any element.
		'''
		return self._min > self._max

	def contains(self, value:Decimal ) ->bool :
		'''
		@param value the value to test
		@return true iff min &le; value &le; max
		'''
		return self._min<=value  and self._max>= value

	def add(self, other:"Interval" ) ->"Interval" :
		'''
		@param other {@link Interval} to be added to this
		@return new interval [ this.min + other.min , this.max + other.max ]
		'''
		return Interval(self._min + other._min, self._max+other._max)

	def intersect(self, other:"Interval" ) ->"Interval" :
		'''
		@param other another {@link Interval} intersect with
		@return intersection of this with other. returns null if intersection is
		        empty.
		'''
		return Interval(max(self._min,other._min),min(self._max,other._max))

	def invert(self,  other:"Interval") -> Optional["Interval"] :
		'''
		@param other the other minmax to deal with
		@return the range of values that, when added to a value from other, will
		        possibly get in our range. effectively, [min-other.max,
		        max-other.min]. Returns None if the resulting range is empty.
		'''
		newmin = self._min-other._max
		newmax = self._max-other._min
		if newmin>newmax:
			return None;
		return Interval(newmin, newmax);

	def subtract(self,  value:Decimal) ->"Interval" :
		'''
		@param value the value to subtract
		@return Interval with both min and max reduced by value.
		'''
		return Interval(self._min-value, self._max-value)

	def multiply(self, weight:Decimal ) -> "Interval" :
		return Interval(self._min*weight, self._max*weight)
	
	#Override
	def __repr__(self) ->str:
		return "Interval[" + str(self._min) + "," + str(self._max) + "]"

	def round(self, precision:int)->"Interval" :
		'''
		@param precision number of digits required
		@return this but with modified precision. The interval is rounded so that
		        the new interval is inside the old one.
		'''
		factor=Decimal(10)**precision
		return Interval( ceil(self._min * factor)/factor,
						floor(self._max * factor)/factor)	

	#Override
	def __hash__(self)->int:
		return hash((self._min, self._max))

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._min == other._min and \
			self._max == other._max

