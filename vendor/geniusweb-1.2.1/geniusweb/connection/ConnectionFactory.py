from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from geniusweb.connection.ConnectionEnd import ConnectionEnd
from geniusweb.references.Reference import Reference


INTYPE = TypeVar('INTYPE')
OUTTYPE = TypeVar('OUTTYPE')

class ConnectionFactory(ABC,  Generic[INTYPE,OUTTYPE]):
	'''
	factory that can turn a {@link Reference} into a connection to that
	reference.
	
	
	@param <INTYPE>  the type of incoming messages. Incoming messages are
	                 received through Listener#not. Incoming messages are usually
	                 asynchronous.
	@param <OUTTYPE> the type of outgoing messages. Outgoing messages can be sent
	                 directly with #send.
	'''
	@abstractmethod
	def connect(self, reference:Reference) -> ConnectionEnd[INTYPE, OUTTYPE]:
		'''
		@param reference the {@link Reference} to a {@link Connectable}
		@return connection to provided reference
		@throws ConnectionError         if the connection can not be made because
		                                of a network or address related problem.
		                                This points to something non-trivially
		                                that may require user intervention to fix
		                                something.
		@throws NoResourcesNowException if the connection can not be made at this
		                                moment because of lack of resources on
		                                the server. This suggest to retry later.
		'''
