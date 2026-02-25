from _decimal import Decimal
from pyson.JsonValue import JsonValue
from geniusweb.issuevalue.Value import Value


class NumberValue (Value):
	'''
	A value containing a number, that should be in some {@link NumberValueSet}.
	immutable
	'''

	def __init__(self, value:Decimal):
		if not isinstance(value, Decimal):
			raise ValueError("NumberValue must be Decimal, but got "+str(value)+ " of type "+str(type(value)))
		super().__init__( value )
	
