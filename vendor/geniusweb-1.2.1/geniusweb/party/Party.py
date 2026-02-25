from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List
from geniusweb.connection.Connectable import Connectable
from geniusweb.party.Capabilities import Capabilities
from geniusweb.inform.Inform import Inform
from geniusweb.actions.Action import Action


class Party (Connectable[Inform, Action] ):
	'''
	 This is a interface definition for java-based party implementations that are
	 to be run on the PartiesServer.
	 
	 To implement a party to run on the PartiesServer, you must implement this and
	 also have a 0-arg constructor. Also we strongly recommend not to use any
	 static code blocks or do anything serious in the constructor. Instances of
	 your class may also be created only to call the getCapabilities function.
	 
	 <h2>Short outline</h2> After the party is created (empty constructor) it is
	 first connected through a call to connect (from the {@link Connectable}
	 interface). The party can subscribe to receive {@link Inform} objects using
	 {@link ConnectionEnd#addListener(tudelft.utilities.listener.Listener)}. The
	 party can also send its actions using {@link ConnectionEnd#send(Object)}.
	 
	 The {@link ConnectionEnd} allows the party to receive Inform objects and send
	 action objects.
	 
	 Incoming Inform objects (eg "Settings" containing the profile, and
	 "yourturn") are notified to the party throught he notifyChange() call to the
	 party.
	 <p>
	 Outgoing Action objects (eg "Offer") are sent using the send() command.
	 
	 Most parties extend {@link DefaultParty} to handle these connection details.
	 <p>
	 Technical details: normally a Party will be spawned inside a PartiesFactory,
	 and incoming/outgoing calls are routed through a websocket there. But in
	 testing the Connectable is often mocked.
	'''
	
	@abstractmethod
	def getCapabilities(self) -> Capabilities: 
		'''
		 @return the capabilities of this party.
		'''
	
	@abstractmethod
	def getDescription(self) -> str:
		'''
		 @return some useful short description, eg "tit-for-tat with bayesian
		         opponent modeling".
		'''

	@abstractmethod
	def terminate(self):
		'''
		When this is called, the party should free up its resources and terminate
		its threads. This call may come in at any time, eg when a negotiation is
		aborted.
		'''

