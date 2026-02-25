from typing import Optional

from geniusweb.actions.PartyId import PartyId


class ProtocolException (Exception) :
	'''
	thrown if a Party violates the protocols (that includes disconnecting).
	'''

	def __init__(self, message:str, party:Optional[PartyId] ,  e:Optional[Exception]=None):
		'''
		ProtocolException is special, in that it does not auto-fill the
		stacktrace. This is needed because usually a ProtocolException is caused
		by a party doing a bad action. Creating a stacktrace pointing to the
		class reporting the protocol exception (usually, the protocol handler)
		makes no sense as the protocol handler is doing the correct job there.
		
		
		@param message the error message
		@param party   offending/failing {@link PartyId}. In exceptional cases this can
			be null, eg if it can not be determined which party
			failed. Null should be avoided if possible at all.
		@param e       the cause of the error, none if no cause
		'''
		super().__init__(str(party) + ":" + message)
		self.__cause__=e
		self._party = party


	def getParty(self) -> Optional[PartyId] :
		'''
		@return offending party, either the {@link PartyId} or a {@link PartyRef}
		'''
		return self._party;
