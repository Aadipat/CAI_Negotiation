from typing import List

from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.deadline.Deadline import Deadline
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.SessionSettings import SessionSettings
from geniusweb.protocol.session.TeamInfo import TeamInfo

from geniusweb.references.PartyWithProfile import PartyWithProfile


class SAOPSettings(SessionSettings):

	def __init__(self,  participants:List[TeamInfo], deadline:Deadline ): 
		'''
		@param participants the list of {@link PartyWithProfile} in clockwise
		                    order. There must be at least 2 to run the SAOP
		                    protocol. But SAOP can be initialized with less, for
		                    use in TournamentSettings.
		@param deadline     the deadline of the negotiation
		'''
		self._participants = participants;
		self._deadline = deadline;
		if participants == None:
			raise ValueError("participants must not be null")
		if deadline == None:
			raise ValueError("deadline must not be null")

	def getMaxRunTime(self) -> float:
		return self._deadline.getDuration() / 1000.

	def getProtocol(self, logger:Reporter ) -> SessionProtocol :
		# avoid circular imports
		from geniusweb.protocol.session.saop.SAOP import SAOP
		from geniusweb.protocol.session.saop.SAOPState import SAOPState
		return SAOP(SAOPState([],[],None, self), logger)
	
	def getParticipants(self) -> List[TeamInfo] :
		return list(self._participants)

	def getTeams(self) -> List[TeamInfo] :
		return list(self._participants)

	def getDeadline(self)->Deadline :
		'''
		@return the deadline for this negotiation
		'''
		return self._deadline

	def  getAllParties(self) -> List[PartyWithProfile] : 
		return [particip.getParties()[0] for particip in self._participants ]

	def getTeamSize(self) -> int:
		return 1

	def __repr__(self)->str:
		return "SAOPSettings" + str(self._participants) + "," + str(self._deadline) + "]"

	def __hash__(self):
		return hash((self._deadline, tuple(self._participants)))
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			 and  self._deadline == other._deadline and self._participants==other._participants

	def With(self, team:TeamInfo) -> SessionSettings :
		if team.getSize() != 1:
			raise ValueError("Team must be size 1 but found " + str(team));
		newparts = list(self._participants)
		newparts.append(team)
		return SAOPSettings(newparts, self._deadline)

