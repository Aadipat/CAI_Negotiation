from _decimal import Decimal
from abc import ABC

from pyson.JsonDeserialize import JsonDeserialize
from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonValue import JsonValue



@JsonDeserialize("geniusweb.issuevalue.ValueDeserializer.ValueDeserializer")
@JsonSubTypes(["geniusweb.issuevalue.NumberValue.NumberValue",\
			"geniusweb.issuevalue.DiscreteValue.DiscreteValue"])
class Value(ABC):
	'''
	A possible value for an Issue. Must be immutable and thread safe. Supported
	values are {@link NumberValue} and {@link DiscreteValue}. All values are just
	strings, a custom deserializer is used to determine which type it is.
	
	Value must be de-serializable all by itself, because it can occur plain in a
	Bid eg Bid["fte":0.8]
	'''
	def __init__(self, value):
		self._value = value;
	
	@JsonValue()
	def getValue(self) -> str:
		return self._value;
	
	def __repr__(self): 
		return str(self._value)
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) and  self._value == other._value

	def __hash__(self):
		return hash(self._value)