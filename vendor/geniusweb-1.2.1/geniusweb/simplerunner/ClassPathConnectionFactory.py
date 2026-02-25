import importlib
import re
from typing import List

from tudelft.utilities.listener.Listener import Listener
from uri.uri import URI

from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Inform import Inform
from geniusweb.party.Party import Party
from geniusweb.protocol.partyconnection.ProtocolToPartyConn import ProtocolToPartyConn
from geniusweb.protocol.partyconnection.ProtocolToPartyConnFactory import ProtocolToPartyConnFactory
from geniusweb.references.Reference import Reference
from geniusweb.simplerunner.BasicConnection import BasicConnection 
from geniusweb.utils import val


class BasicConnectionWithParty (BasicConnection[Action, Inform],  ProtocolToPartyConn):

	_id: PartyId 

	def __init__(self, reference:Reference ,uri: URI):
		super().__init__(reference, uri)
		self._id = PartyId(re.sub("\.", "_", str(uri).replace("pythonpath:", "")))

	def getParty(self)->PartyId :
		return self._id

	def __repr__(self)->str:
		return "WP" + super().__repr__()


class ConnectionPair: 
	'''
	Contains the connection from protocol to party and from party to protocol.
	These two are dependent on each other, and must close together.
	'''
	serialcounter = 1 # class variable. Keeps track of used valies.
	_SCHEME = "pythonpath"
	_PROTOCOLURI = URI("protocol:protocol")

	_party2protocol: BasicConnection[Inform, Action]
	_protocol2party: BasicConnectionWithParty

	def __init__(self, reference:Reference ) :
		'''
		@param reference the party class path reference4
		'''
		# set up the whole other party including the connection to it.
		classpath = self._getClassPath(reference.getURI())
		party = self._instantiate(classpath)
		this=self

		# if call to protocol would fail, we should also close the
		# protocol2party connection. But we assume that will work fine.
		class myBC(BasicConnection[Inform, Action]):
			def __init__(self):
				super().__init__(reference, ConnectionPair._PROTOCOLURI)
				
			def close(self):
				if self.isOpen():
					super().close()
					this._protocol2party.close()
	
		self._party2protocol = myBC()
		
		# if callback from protocol to party fails, then also close the
		# other direction.
		class myBCP(BasicConnectionWithParty):
			def __init__(self):
				super().__init__(reference, \
					URI("pythonpath:" + reference.getURI().getPath()\
						+ "." + str(ConnectionPair.serialcounter)))
				ConnectionPair.serialcounter +=  1
				
			def close(self):
				if self.isOpen():
					super().close()
					this._party2protocol.close()
	
		
		self._protocol2party = myBCP()

		class party2protocolListener(Listener[Action]):
			def notifyChange(self, data: Action):
				this._protocol2party.notifyListeners(data)
		self._party2protocol.init(party2protocolListener())

		class protocol2partyListener(Listener[Inform]):
			def notifyChange(self, data: Inform):
				this._party2protocol.notifyListeners(data)
		self._protocol2party.init(protocol2partyListener())

		party.connect(self._party2protocol)


	def getOpenConnections(self)->List[BasicConnection] :
		'''
		@return the open connections
		'''
		open:List[BasicConnection]  = []
		if self._party2protocol.isOpen():
			open.append(self._party2protocol)
		if self._protocol2party.isOpen():
			open.append(self._protocol2party)
		return open

	def getProtocolToPartyConn(self)->BasicConnectionWithParty :
		return self._protocol2party
	
	
	def _getPartyToProtocolConn(self) ->BasicConnection :
		'''
		Internal use for testing
		'''
		return self._party2protocol
	
	def _instantiate(self, classpath:str)->Party :
		'''
		@param classpath to a full.pythonpath.classname as string. 
				The class must be on the python path.
				the 'full.pythonpath' must be the module "filename",
				the "classname" is the name of the class inside the module file.
		@return instance of the given {@link Party} on the classpath
		@throws ValueError if the Party can not be instantiated, eg
		         because of a ClassCastException,
		         ClassNotFoundException,
		         IllegalAccessException etc. Such an
		         exception is considered a bug by the
		         programmer, because this is a
		         stand-alone runner.
		'''
		print("Connecting with party '" + classpath + "'")
		try:
			
			[path, cla] = classpath.rsplit(".",1)
			mod=importlib.import_module(path)
			partyclass = getattr(mod, cla)
			return partyclass()
		except Exception as e:
			raise ValueError(
					"Failed to create connection to party " + classpath,e)
		importlib

	def _getClassPath(self,  uri:URI) -> str:
		assert isinstance(uri, URI)
		if self._SCHEME != uri.getScheme():
			raise ValueError("Required the " + self._SCHEME
					+ " protocol but found " + uri.getScheme())
		path = uri.getPath()
		if not path:
			raise ValueError(
					"Expected pythonpath not present in " + str(uri))
		return path
	


class ClassPathConnectionFactory (ProtocolToPartyConnFactory):
	'''
	A connectionfactory that only accepts URLs of the form
	<code>pythonpath:org/my/package/class</code>
	'''
	_allConnections: List[ConnectionPair]  = []

	def connect(self, reference:Reference ) ->ProtocolToPartyConn :
		'''
		@param reference the party class path reference4
			'''
		connpair = ConnectionPair(reference)
		self._allConnections.append(connpair)
		return connpair.getProtocolToPartyConn()

	def connectAll(self,  references:List[Reference] ) ->List[ProtocolToPartyConn] :
		connections:List[ProtocolToPartyConn] = []
		for partyref in references:
			connections.append(self.connect(partyref))
		return connections

	def getOpenConnections(self)->List[BasicConnection] :
		'''
		@return list of connections that are still open.
		'''
		openconns:List[BasicConnection] = []
		for connpair in self._allConnections:
			openconns.extend(connpair.getOpenConnections())
		return openconns
