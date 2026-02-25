from collections import deque
from multiprocessing import Queue
from threading import Thread, Condition
import threading
import traceback
from typing import TypeVar, Generic, List, Optional

from tudelft.utilities.listener.Listener import Listener
from uri.uri import URI

from geniusweb.connection.ConnectionEnd import ConnectionEnd
from geniusweb.references.Reference import Reference
from geniusweb.simplerunner.BlockingQueue import BlockingQueue


S=TypeVar("S")

class Info (Generic[S]):
	'''
	Wrapper around data so that we can put Null end EOS in a
	{@link ArrayBlockingQueue}
	@param <S> the type of contained data.
	'''

class Data (Info[S]):

	def __init__(self, data:S):
		self._data = data

	def get(self)->S:
		return self._data;

	def __repr__(self):
		return str(self._data)

class EOS (Info[S]):
	'''
	End of stream.
	'''
	def __repr__(self):
		return "EOS"
	
# I use this single instance everywhere
THE_EOS:EOS = EOS()


IN = TypeVar('IN')
OUT = TypeVar('OUT')

class BasicConnection(ConnectionEnd[IN, OUT]):
	'''
	A basic connection that implements connection with direct calls
	
	@param <IN>  the type of the incoming data
	@param <OUT> the type of outgoing data
	'''

	def __init__(self, reference:Reference , uri:URI ):
		'''
		@param reference Reference that was used to create this connection.
		@param uri       the URI of the remote endpoint that makes up the
		                 connection. This is a URI that uniquely identifies the
		                 remote object
		'''
		self._reference = reference
		self._uri = uri
		self._listeners:List[Listener[IN]] = []
		self._synclock = threading.RLock()
		self._error:Optional[Exception]=None
	
		# to be initialized
		self._handler:Optional[Listener[OUT]] = None
		self._messages = BlockingQueue[Info](4)


	def init(self, newhandler:Listener[OUT] ) :
		'''
		To be called to hook up the other side that will handle a send action
		from us. Must be called first.
		
		@param newhandler a Listener&lt;OUT&gt; that can handle send actions.
		'''
		if self._handler: 
			raise ValueError("already initialized")
		self._handler = newhandler
		this=self

		class MyHandlerThread(Thread):
			'''
			thread that handles this._messages until EOS is hit.
			It runs in scope of init and uses 'this'
			'''
			def run(self):
				try:
					while (True):
						#print("INTO"+str(self))
						mess = this._messages.take()
						#print("OUT"+str(self))
						if mess==THE_EOS:
							break;
						this._handler.notifyChange(mess.get())
				except Exception as e:
					this.setError(e)
				this._handler = None
				#print("BasicConnection closed");
		
		handlerThread=MyHandlerThread()
		handlerThread.start();

	def setError(self,  e:Exception):
		'''
		Error condition occurs. Record error and close connection
		
		@param e
		'''
		with self._synclock:
			if not self._error:
				# maybe log instead?
				traceback.print_exc()
				self._error = e
				self.close()

	def send(self, data:OUT ) :
		with self._synclock:
			if not self._handler:
				raise ValueError(
					"BasicConnection has not been initialized or was closed")
			# it seems there is no InterruptedException possible in python.
			self._messages.put(Data(data))

	def getReference(self) -> Reference :
		return self._reference

	def getRemoteURI(self)->URI: 
		return self._uri

	def close(self):
		with self._synclock:
			print("flushing and terminating " + str(self))
			if not self._handler or self._messages.contains(THE_EOS):
				return
			# it seems there is no InterruptedException possible in python.
			self._messages.put(THE_EOS)

	def __repr__(self):
		return "BasicConnection[" + str(self._reference) + "]"

	def getError(self)->Optional[Exception]:
		return self._error;

	def isOpen(self)->bool: 
		'''
		 @return true iff this connection is open. Returns false also when then
 			handler is in the close-down process
		'''
		return self._handler != None and not self._messages.contains(THE_EOS)

	#****************** implements listenable ****************
	# override because notifyListeners should throw exceptions.
	def addListener(self, l:Listener[IN]):
		self._listeners.append(l)

	def removeListener(self, l:Listener[IN] ) :
		self._listeners.remove(l)

	def notifyListeners(self, data:IN ) :
		for l in self._listeners:
			l.notifyChange(data)

