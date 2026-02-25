from typing import TYPE_CHECKING
from pyson.JsonSubTypes import JsonSubTypes
from tudelft.utilities.listener.Listenable import Listenable

from geniusweb.events.ProtocolEvent import ProtocolEvent
if TYPE_CHECKING:
	from geniusweb.protocol.NegoState import NegoState
from geniusweb.protocol.partyconnection.ProtocolToPartyConnFactory import ProtocolToPartyConnFactory
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.references.ProtocolRef import ProtocolRef


@JsonSubTypes(["SessionProtocol"])
class NegoProtocol (Listenable[ProtocolEvent]):
	'''
	Abstract interface to all negotiation protocols, both single session and
	tournaments. Generally a protocol handles events on the provided connections
	according to the rules set by the protocol. The rules are explained by
	{@link #getDescription()}. A protocol reports the progress through its
	{@link Listenable} interface. <br>
	<h2>General information</h2>
	
	A protocol is mutable because the incoming connections cause state changes.
	But it is recommended to push changing properties into the state so that the
	complete state can be recovered and analysed.
	<p>
	Because a protocol contains an internal state, it can be used only once.
	<p>
	The protocol can emit a {@link CurrentState} event at any time. It should do
	so at least once, to log the final outcome of the nego.
	<p>
	
	Normally the constructor will receive a {@link ConnectionFactory} through
	which it can resolve received {@link Reference}s. <br>
	First call to instances <b>must be</b>
	{@link #start(ProtocolToPartyConnFactory)}.
	
	<h2>Ensure time deadline</h2>
	
	The protocol also needs to keep an eye on the deadline and take appropriate
	actions when the deadline is reached. <br>
	<p>
	All protocol implementations must ensure that the deadline is kept and that
	the session ends at the agreed time {@link Deadline#getDuration()}. This is
	to ensure that the negotiation ends and resources are freed up at or before
	some known time.
	'''
	def start(self, connectionfactory:ProtocolToPartyConnFactory):
		'''
		Start the protocol: make connection with parties and follow the protocol.
		This must be called once and should be the first call after construction.
		<p>
		
		The protocol implementation should not start any real work (eg making
		connections) before this point. That also allows us to construct protocol
		instances just to fetch the description.
		<p>
		
		All errors are to be handled through {@link SessionState#getResult()}
		except for bugs that use {@link RuntimeException} like
		{@link IllegalArgumentException}s. <br>
		The protocol usually uses the incoming connections to keep running. It
		does not need to run in a separate thread or so.
		
		
		@param connectionfactory the {@link ProtocolToPartyConnFactory} that
		                         allows the protocol to connect with the
		                        {@link Reference}s in the settings
		'''

	def getDescription(self)-> str:
		'''
		@return a complete description of how this protocol behaves. Presented to
		        the end users who should know negotiation basics but not all
		        technical terms.
		'''
	def getState(self)->"NegoState" :
		'''
		@return current state: the results of all sessions run so far and how to
		        continue from that point. Changes over time as the session
		        proceeds. Errors are also stored in the state.
		'''

	 
	def getRef(self) -> ProtocolRef :
		'''
		@return the {@link ProtocolRef} for this protocol
		'''

	def addParticipant(self, party:PartyWithProfile ):
		'''
		Add a party after the protocol has started. Only some protocols can
		handle this call. Usual protocols take the settings with their
		constructor.
		@param party the {@link PartyWithProfile} to be added.
		'''

