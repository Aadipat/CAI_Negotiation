from abc import ABC
from typing import TypeVar, Generic, List, Optional

from tudelft.utilities.listener.Listenable import Listenable
from uri.uri import URI

from geniusweb.references.Reference import Reference


INTYPE = TypeVar('INTYPE')
OUTTYPE = TypeVar('OUTTYPE')

class ConnectionEnd(Listenable[INTYPE], Generic[INTYPE,OUTTYPE]):
	'''
	One end of a general two-way connection. incoming data is reported through
	the {@link Listenable} channel, sending events of the INTYPE.
	<p>
	
	The connection mechanism assumed here is fundamentally asymmetric. One side
	is "Connectable", the other side is a ConnectionEnd created (usually from a
	{@link Reference}. This matches the typical client-server system (web
	architecture).
	
	<p>
	If an internal error occurs, eg a socket failure, timeout, or parser error, a
	null event is sent into the Listenable. {@link #getError()} can be called to
	find out about the error.
	@param <INTYPE>  the type of incoming messages (incoming for the user of this
	                 connection end). Incoming messages are received through
	                 Listener#not. Incoming messages are usually asynchronous.
	@param <OUTTYPE> the type of outgoing messages (outgoing for the user of this
	                 connection end). Outgoing messages can be sent directly with
	                 #send.
	'''

	def send(self,data:OUTTYPE ):
		'''
		Send data out (and flush the output so that there are no excessive delays
		in sending the data). This call is assumed to return immediately (never
		block, eg on synchronized, Thread.sleep, IO, etc). When this is called
		multiple times in sequence, the data should arrive at the receiver end in
		the same order.
		
		@param data the data to be sent.
		@throws ConnectionError if the data failed to be sent.
		'''
	
	def getReference(self) -> Reference:
		'''
		@return Reference that was used to create this connection
		'''

	def getRemoteURI(self)->URI: 
		'''
		@return the URI of the remote endpoint that makes up the connection. This
		         is a URI that uniquely identifies the remote object.
		'''

	def close(self):
		'''
		Close the connection. Should return immediately (not block). Before
		really closing, this should attempt to send out possibly cached messages
		before closing the connection.
		'''
	def getError(self) -> Optional[Exception]:
		'''
		@return the latest internal error, or null if no error occured. If the
		        channel is closed, this is set to {@link SocketException} "Socket
		        closed", even if the close was a "normal" termination eg when
		        {@link #close()} was called.
		'''

