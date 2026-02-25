from geniusweb.events.ProtocolEvent import ProtocolEvent
class CurrentState( ProtocolEvent ):
	'''
	Reports a NegoState as the latest state of the protocol. The negoState is
	abstract because the state is not something that can be handled at this place
	in the dependency hierarchy. The "real" implementations are inside the
	protocol.
	<p>
	When a protocol reports this event, it indicates that this state can be
	logged to the loggers for output to the users (publication on the webpages
	and reporting to parent protocols eg a tournamentrunner). Usually protocols
	are updating this only after a session completes. There may be quite some
	overhead triggered by emission of these events, such as rewriting files and
	notifying end users behind websockets. Protocols MUST report this at least
	once to report the final isFinished() state.
	<p>
	The logged state may be used to re-start a protocol if it crashes later in an
	unfinished state.
	'''
	# all should implement NegoState getState();

