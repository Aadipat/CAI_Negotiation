from copy import copy
from decimal import Decimal
from typing import List, Collection

from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet


class DiscreteValueSet (ValueSet):

	def __init__(self, values: Collection[DiscreteValue]) :
		self._values:List[DiscreteValue]=[]
		for val in values:
			if val not in self._values:
				self._values.append(val)

	def getValues(self) -> List[DiscreteValue]:
		return list(self._values)

	def contains(self, value:Value ) ->bool:
		return value in self._values

	def get(self,index:int) -> DiscreteValue :
		return self._values[int(index)]

	def size(self) -> int :
		return len(self._values)

	def __repr__(self):
		# workaround, str(list) seems to call __repro__ isntead of _-str__....
		return "DiscreteValueSet" + repr(self._values)

	def __eq__(self, other):
		return isinstance(other, self.__class__) and set(self._values)==set(other._values)

	def __hash__(self):
		# don't use tuple because order is irrelevant.
		return sum([hash(val) for val in self._values]) 