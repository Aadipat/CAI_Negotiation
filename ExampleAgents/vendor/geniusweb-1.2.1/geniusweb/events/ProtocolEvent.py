from geniusweb.events.AbstractEvent import AbstractEvent

class ProtocolEvent (AbstractEvent):
	'''
	an event triggered by the protocol.
	'''
	
	def ProtocolEvent(self, now:int):
		super().__init__(now)
