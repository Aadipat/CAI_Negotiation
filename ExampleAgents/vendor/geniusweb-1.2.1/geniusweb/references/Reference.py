
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List
from pyson.JsonValue import JsonValue
from uri.uri import URI          # type: ignore

class Reference (ABC):
	'''
	A reference is a URI to a Connectable object.
	'''
	@abstractmethod
	def getURI(self) -> URI:
		'''
		@return URI address to which a connection can be made with the real
		        object. HACK for now we return just the str 
		'''
		
	# WE CAN NOT DEFINE __hash__ here, it is not inherited...