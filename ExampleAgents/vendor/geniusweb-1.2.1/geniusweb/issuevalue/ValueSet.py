
from pyson.JsonDeserialize import JsonDeserialize
from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList

from geniusweb.issuevalue.Value import Value


@JsonDeserialize(using = "geniusweb.issuevalue.ValueSetDeserializer.ValueSetDeserializer")
class ValueSet (AbstractImmutableList[Value]):
	'''
	A set of possible {@link Value}s (usually, of an Issue (which is represented
	by a String)).
	
	Value is the type of objects in this value set. We do not implement ValueSet
	right away because types are lost at runtime. Implementing separate classes
	for implementing the ValueSet ensures we can get back the type at runtime.
	immutable. Thread safe.
	'''

	def contains(self, value:Value) -> bool:
		'''
		@param value the value to check
		@return true iff this set contains given value
		'''
