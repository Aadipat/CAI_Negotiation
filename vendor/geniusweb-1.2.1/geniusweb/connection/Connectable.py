from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List

from geniusweb.connection.ConnectionEnd import ConnectionEnd

INTYPE = TypeVar('INTYPE')
OUTTYPE = TypeVar('OUTTYPE')

class Connectable(ABC, Generic[INTYPE,OUTTYPE]):
	'''
	A Connectable is an object that can connect on request with a provided
	{@link ConnectionEnd} and then respond to incoming and outgong signals.
	@param <INTYPE>  the type of incoming messages
	@param <OUTTYPE> the type of outgoing messages
	'''

	@abstractmethod
	def connect(self,connection:ConnectionEnd[INTYPE, OUTTYPE] ):
		'''
		creates the connection. Only called if not yet connected.
		@param connection the new connection
		'''
		
	@abstractmethod
	def disconnect(self):
		'''
		Removes the connection from a connectable; the previously given
		connection can not be used anymore after this call. Only called if
		previously connected.

		'''