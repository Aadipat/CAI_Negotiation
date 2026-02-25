from decimal import Decimal, ROUND_HALF_UP
from typing import cast, Optional

from geniusweb.issuevalue.NumberValue import NumberValue
from geniusweb.issuevalue.NumberValueSet import NumberValueSet
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities


class NumberValueSetUtilities (ValueSetUtilities ):
	'''
	The low and high values (from a {@link NumberValueSet} are given each a
	different utility. This linearly interpolates in-between utility values.
	'''


	def __init__(self,  lowValue:Decimal,\
			lowUtility:Decimal,  highValue: Decimal, highUtility:Decimal) :
		'''
		@param lowValue    the low value of the {@link Range}
		@param lowUtility  the utility of the {@link #lowValue}
		@param highValue   the high value of the {@link Range}. Must be
		                   &gt;lowValue.
		@param highUtility the utility of the {@link #highValue}
		'''
		if lowValue == None or highValue == None or lowUtility == None \
				or highUtility == None :
			raise ValueError(\
					"arguments lowValue, lowUtility, highValue and highUtility must be non-null");
		
		if not self._isInZeroOne(lowUtility):
			raise ValueError("lowUtility must be in [0,1]")
		
		if not self._isInZeroOne(highUtility):
			raise ValueError("highUtility must be in [0,1]")
		
		if highValue<=lowValue:
			raise ValueError("highValue must be > lowValue")
		
		self._lowValue = lowValue
		self._highValue = highValue
		self._lowUtility = lowUtility
		self._highUtility = highUtility

	#Override
	def getUtility(self, value:Optional[Value] ) -> Decimal :
		if not isinstance(value, NumberValue):
			return Decimal("0");

		x:Decimal  = value.getValue()
		if x<self._lowValue or x>self._highValue:
			return Decimal("0")
		# we need to be careful to avoid round errors from divides.
		# so we return lowU + deltaU * (x-lowV) /deltaV
		deltaU:Decimal  = self._highUtility- self._lowUtility
		deltaV:Decimal = self._highValue-self._lowValue

		return (self._lowUtility + deltaU *(x-self._lowValue)/deltaV )\
			.quantize(Decimal('1.00000000'), rounding=ROUND_HALF_UP)
	

	#Override
	def isFitting(self, valueset: ValueSet ) -> Optional[str]:
		if not isinstance(valueset, NumberValueSet):
			return "The utilities are for a number valueset but the given values are "\
					+ str(valueset);
		
		numvalset= cast(NumberValueSet, valueset)
		if numvalset.getRange().getLow() != self._lowValue:
			return "the utilities are specified down to " + str(self._lowValue) \
					+ " but the valueset starts at " \
					+ str(numvalset.getRange().getLow())
		
		if numvalset.getRange().getHigh() != self._highValue:
			return "the utilities are specified up to " + str(self._highValue) \
					+ " but the valueset ends at " \
					+ str(numvalset.getRange().getHigh())
		return None

	def getLowValue(self) -> Decimal  :
		'''
		@return the lowest value
		'''
		return self._lowValue;


	def getHighValue(self) ->Decimal :
		'''
		@return the highest value
		'''
		return self._highValue

	def  getLowUtility(self) ->Decimal :
		'''
		@return the utility of the lowest value
		'''
		return self._lowUtility;

	def  getHighUtility(self) ->Decimal:
		'''
		@return the utility of the highest value
		'''
		return self._highUtility

	def __repr__(self):
		return "NumberValueSetUtilities[" + str(self._lowValue) + "->" + str(self._lowUtility) + "," \
				+ str(self._highValue) + "->" + str(self._highUtility) + "]"

	def __hash__(self):
		return hash((self._lowUtility, self._lowValue,self._highUtility, self._highValue))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			 and self._highUtility == other._highUtility \
			 and self._highValue == other._highValue \
			 and self._lowUtility == other._lowUtility \
			 and self._lowValue == other._lowValue 

	def _isInZeroOne(self  ,  value:Decimal) -> bool:
		'''
		Check if value is in range [0,1]
		
		@param value
		@return true if in range.
		'''
		return value >= Decimal("0") and value <= Decimal("1")

