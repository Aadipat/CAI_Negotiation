from pyson.JsonValue import JsonValue

from geniusweb.issuevalue.Value import Value


class DiscreteValue (Value) :
	'''
	A value for a discrete issue. Constructor guarantees this is non-null and
	non-empty. immutable.
	'''

	def __init__(self, value:str):
		if value == None or value=="":
			raise ValueError("value must be non-null and non-empty")
		super().__init__(value)

	def __hash__(self):
		return hash(self._value)

	def __repr__(self): 
		return '"'+str(self._value)+'"'
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) and  self._value == other._value
