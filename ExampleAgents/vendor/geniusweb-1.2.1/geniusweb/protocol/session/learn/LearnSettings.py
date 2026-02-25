from typing import List
from uuid import UUID

from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.deadline.Deadline import Deadline
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.SessionSettings import SessionSettings
from geniusweb.protocol.session.TeamInfo import TeamInfo
from geniusweb.references.PartyWithProfile import PartyWithProfile


class LearnSettings(SessionSettings):
	'''
	Settings for learn protocol.
	'''

	def __init__(self, participants:List[TeamInfo] , deadline:Deadline) :
		'''
		@param participants the list of {@link PartyWithProfile} in clockwise
		        order. There must be at least 2 to run the SAOP
		        protocol. But SAOP can be initialized with less, for
		        use in TournamentSettings.
		        <table>
		        <caption>Required parameters</caption>
		        <tr>
		        <td>persistentstate</td>
		        <td>a {@link FileLocation}, serialized as json eg
		        <code>"b29f3bf5-1dc4-499e-a676-7b2dbb864a03"</code> ,
		        where the party's persistant state is stored; this
		        must match the persistantstate used in earlier calls
		        for e.g. {@link SAOPSettings}.</td>
		        </tr>
		
		        <tr>
		        <td>negotiationdata</td>
		        <td>a List of {@link FileLocation}s, serialized as
		        json, matching the negotiationdata used in earlier
		        calls for eg {@link SAOPSettings}.</td>
		        </tr>
		        </table>
		@param deadline     the deadline of the negotiation.
		'''
		self._participants = participants
		self._deadline = deadline
		if participants == None:
			raise ValueError("participants must not be null")
		if deadline == None:
			raise ValueError("deadline must not be null")

		for pwithp in self.getAllParties():
			params = pwithp.getParty().getParameters()
			statestr = params.get("persistentstate")
			if not isinstance(statestr , str):
				raise ValueError(
						"persistentstate parameter containing UUID string is required, but found "\
								+ str(statestr))
			# check that it contains a UUID. Don't store it, we don't need
			# it.
			UUID(statestr)

			# and check the negotiationdata
			negotiationsstr = params.get("negotiationdata")
			if not isinstance(negotiationsstr, list):
				raise ValueError(
					"negotiationdata parameter containing a List is required")

			for negostr in  negotiationsstr:
				if not isinstance(negostr,str):
					raise ValueError(
						"The list in negotiationdata must contain UUID strings but found "\
							+ str(negostr))
				UUID(negostr)

	def getMaxRunTime(self)->float:
		return self._deadline.getDuration() / 1000.

	def getProtocol(self, logger:Reporter )->SessionProtocol :
		from geniusweb.protocol.session.learn.LearnState import LearnState
		from geniusweb.protocol.session.learn.Learn import Learn
		return Learn(LearnState([],[],None, self), logger)

	def getTeams(self)->List[TeamInfo] :
		return list(self._participants)

	def getParticipants(self) -> List[TeamInfo] :
		return list(self._participants)

	def getDeadline(self)->Deadline :
		'''
		@return the deadline for this negotiation
		'''
		return self._deadline

	def getAllParties(self)->List[PartyWithProfile] :
		return  [particip.getParties()[0]
			 for particip in self._participants ]

	def getTeamSize(self)->int:
		return 1

	def __repr__(self):
		return "LearnSettings" + str(self._participants) +\
			"," + str(self._deadline) + "]"

	def __hash__(self):
		return hash((self._deadline, tuple(self._participants)))

	
	def __eq__(self, other) -> bool:
		return isinstance(other, self.__class__) and \
			self._participants == other._participants and \
			self._deadline==other._deadline 

	def With(self, team:TeamInfo)->SessionSettings :
		if team.getSize() != 1:
			raise ValueError(
					"Team must be size 1 but found " + str(team))
		newparts = list(self._participants)
		newparts.append(team)
		return LearnSettings(newparts, self._deadline)
