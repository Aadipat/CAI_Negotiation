from copy import copy
from decimal import Decimal
from typing import Dict, cast, Optional

from pyson.JsonGetter import JsonGetter

from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities
from geniusweb.utils import toStr


class DiscreteValueSetUtilities (ValueSetUtilities) :
	'''
	Links a set of values to utilities for that value. Does not link to some
	issue so may need further checking when used for an actual issue. Constructor
	guarantees that
	<ul>
	<li>All values in the provided map (the utilities) are in [0,1]
	<li>All keys are proper {@link DiscreteValue}s
	</ul>
	'''

	def __init__(self,	valueUtilities: Dict[DiscreteValue, Decimal]  ):
		'''
		create new object based on the given mapping from values to utilities.
		
		@param valueUtils map with key {@link DiscreteValue}s and value a Double
		                  in the range [0,1].
		@throws NullPointerException     if one of the args is null
		@throws IllegalArgumentException if values are not in range [0,1].

		'''
	
		if valueUtilities == None:
			raise ValueError("valueUtils==null")

		if None in valueUtilities.keys():
			raise ValueError("one of the keys in valueUtils is null")

		for v in valueUtilities.values():
			if v==None or v<Decimal("0") or v>Decimal("1"):
				raise ValueError("Weights in valueUtils must all be in [0,1]")

		self._valueUtilities = copy(valueUtilities);

	#Override
	def getUtility(self,  value:Optional[Value]) -> Decimal:
		if not value in self._valueUtilities:
			return Decimal("0")
		return self._valueUtilities[value] # type: ignore

	@JsonGetter("valueUtilities")
	def getUtilities(self) -> Dict[DiscreteValue, Decimal] :
		'''
		@return copy of the value-utility pair map.
		'''
		return copy(self._valueUtilities)
	

	#Override
	def isFitting(self, valueset:ValueSet ) ->str:
		if not isinstance(valueset, DiscreteValueSet):
			return "The utilities are for a discrete valueset but the given values are "\
					+ str(valueset);
		
		discvalueset = cast(DiscreteValueSet, valueset)
		if self._valueUtilities.keys() != set(discvalueset.getValues()):
			return "The values in the set " + str(valueset) \
					+ " do not match the values mapped to utilities " \
					+ str(self._valueUtilities.keys());
		return cast(str,None)

	def __repr__(self):
		return "DiscreteValueSetUtilities" + toStr(self._valueUtilities)
	

	def __hash__(self):
		return hash(tuple(self._valueUtilities.items()))

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			 self._valueUtilities == other._valueUtilities

