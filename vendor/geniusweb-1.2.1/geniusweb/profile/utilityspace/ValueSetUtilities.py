from abc import ABC
from decimal import Decimal
from typing import Optional

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import JsonTypeInfo, Id, As

from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet


@JsonTypeInfo(use = Id.NAME, include = As.WRAPPER_OBJECT)
@JsonSubTypes(["geniusweb.profile.utilityspace.DiscreteValueSetUtilities.DiscreteValueSetUtilities",
			"geniusweb.profile.utilityspace.NumberValueSetUtilities.NumberValueSetUtilities"])
class ValueSetUtilities(ABC) :
	'''
	Provides a mechanism to map {@link Value}s into a utility (value in range
	[0,1]).
	'''

	def getUtility(self, value:Optional[Value] )->Decimal:
		'''
		@param value the {@link Value} to get the utility for
		@return the utility of the given value. MUST be in [0,1]. Should return 0
		        if the value is unknown.
		'''

	def isFitting(self,  valueset: ValueSet) -> Optional[str]:
		'''
		@param valueset the valueset that is supposed match with this
		@return null if the ValueSetUtilities fits the given set of values , that
		        means it can give utilities for all possible values in valueset.
		        Or a string containing an explanation why not.
		'''

