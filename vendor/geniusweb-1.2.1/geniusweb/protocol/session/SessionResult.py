from typing import Dict, Optional

from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Agreements import Agreements
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.utils import toStr, toTuple


class SessionResult:
	'''
	All results collected from running a session. Normally this does not contain
	all the details, only the final outcome and other global notes.
	'''

	def __init__(self, participants: Dict[PartyId, PartyWithProfile],
			agreements:Agreements , penalties:Dict[PartyId, float] ,
			error:Optional[Exception]):
		'''
		@param participants the list oof {@link PartyWithProfile}. Should never
		                    be null. Some of them may have entered later of left
		                    early. This list should contain them all.
		@param agreements   the final Agreements. The key is the party ID, value
		                    is the bid that the party agreed on. Only parties
		                    that reached an agreement are in this list.
		@param penalties    Key is the party ID, the value is the penalties in
		                    [0,1] for that participant. A penalty only applies to
		                    an agreement, not to a reservation bid.
		@param error        a fatal error that terminated the session. Non-fatal
		                    errors (warnings) are not to be reported. Null if no
		                    fatal error occured (session ended following the
		                    protocol). Normally, a fatal error results in no
		                    agreement but there might be protocols that allow a
		                    session to end with an error but stick with a already
		                    reached agreement as well.
		'''
		self._participants = dict(participants)
		self._agreements = agreements
		self._penalties = dict(penalties)
		self._error = error

	def getParticipants(self) -> Dict[PartyId, PartyWithProfile]:
		'''
		@return the map with for each {@link PartyId} the
		        {@link PartyWithProfile}. Should never be null. Some of them may
		        have entered later of left early. This list should contain them
		        all.
		'''
		return dict(self._participants)

	def getAgreements(self) -> Agreements:
		'''
		@return the final {@link Agreements} of the session. May be empty, not
		        null
		'''
		return self._agreements;

	def getPenalties(self) -> Dict[PartyId, float]:
		'''
	 	@return Map of penalties,
		'''
		return dict(self._penalties)

	def getError(self) -> Optional[Exception]:
		'''
		@return a fatal error that terminated the session. Non-fatal errors
		        (warnings) are not to be reported. Null if no fatal error occured
		        (session ended following the protocol). Normally, a fatal error
		        results in no agreement but there might be protocols that allow a
		        session to end with an error but stick with a already reached
		        agreement as well.
		'''
		return self._error

	def __repr__(self) -> str:
		return "SessionResult[" + toStr(self._participants) + "," + str(self._agreements) + ","\
				+toStr(self._penalties) + "," + str(self._error) + "]"
	
	def __hash__(self):
		return hash((toTuple(self._participants), toTuple(self._penalties), self._agreements))

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._participants == other._participants and \
			self._agreements == other._agreements and\
			self._penalties == other._penalties and \
			self._error == other._error 
