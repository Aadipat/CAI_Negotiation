from __future__ import annotations

from copy import deepcopy
from email._header_value_parser import Parameter
from typing import Dict, Any, List, Optional
from numbers import Number

from pyson.JsonGetter import JsonGetter
from pyson.JsonValue import JsonValue
from geniusweb.utils import toStr, HASH


class Parameters:
	'''
	init parameters for a party. Object must be either a HashMap, List, String or
	Number. Other objects may not deserialize properly. We never use blanket
	Object deserializers (enableDefaultTyping) because of security reasons.
	'''

	def __init__(self, parameters:Dict[str, Any]={}) :
		'''
		@param parameters dict of key-value pairs. values can be primitive
		object, but also a list or dict. The value will be used 'as is',
		so this will not be parsed as a geniusweb object but kept as list/dict.
		'''
		self._params = deepcopy(parameters);
		# deepcopy to ensure our copy is immutable

	def get(self,  key:str) -> object:
		'''
		@param key the key to get the value for.
		@return the raw value, or none if key not in parameters.
		'''
		if not key in self._params:
			return None
		return self._params[key]
	
	@JsonValue()
	def getParameters(self) -> Dict[str, Any]:
		return deepcopy(self._params)


	def isEmpty(self) -> bool:
		'''
		@return true iff params is empty
		'''
		return len(self._params)==0
	

	def containsKey(self, key:str) -> bool:
		'''
		@param key the key to be checked
		@return true iff params contains the given key
		'''
		return key in self._params


	def With(self, key:str, val:object) -> "Parameters" :
		'''
		@param key the key. Key may already in params.
		@param val the new value for the key
		@return new Parameters , which is copy of this but with key-value pair
		        added/overridden
		'''
		newparams = dict(self._params) # our params are immutable 
		newparams[key]= val
		return Parameters(newparams)

	def WithParameters(self, parameters:"Parameters"):
		'''
		@param parameters the parameters to be added/overridden
		@return new Parameters, with new parameters ADDED to existing. The new
			 parameters override existing ones.
		'''
		newparams = dict(self._params)
		newparams.update(parameters._params)
		return Parameters(newparams)

	def getType(self, paramname:str, classType):
		'''
		Getter with type-check
		
		@param <T>       the expected type
		@param paramname the parameter name that must be in the map
		@param classType the expected value type for this parameter
		@return object of requested type.
		@throws IllegalArgumentException if the object is not available.
	'''
		if not paramname in self._params \
				or not type(self._params[paramname])==classType: 
			raise ValueError(" Missing a parameter "+ paramname + " with a " + str(classType) + " value");
		return self._params[paramname]
	
	def getDouble(self, name:str, defaultval:Optional[float], minv:Optional[float],
			 maxv:Optional[float]) -> Optional[float]: 
		'''
		@param name       the parameter name
		@param defaultval the default value to return if parameter is not
		                  available or not inside the given range. Can be null
		@param minv        the minimum value, or null if not applicable
		@param maxv        the maximum value, or null if not applicable
		@return the double value contained inside the parameter with the given
		        name, or defaultval if the parameter does not exist, does not
		        contain a double, or is outside [min, max].
		'''
		if  not name in self._params or not isinstance(self._params[name], Number):
			return defaultval;
		val:float = self._params[name]
		if minv  and val < minv:
			return defaultval;
		if maxv  and val > maxv:
			return defaultval;
		return val;
	
	def __hash__(self):
		return HASH(self._params)
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._params == other._params

	def __repr__(self):
		return toStr(self._params)

