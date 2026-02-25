from typing import List

from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.deadline.Deadline import Deadline
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.SessionSettings import SessionSettings
from geniusweb.protocol.session.TeamInfo import TeamInfo
from geniusweb.protocol.tournament.Team import Team
from geniusweb.references.PartyWithProfile import PartyWithProfile
from geniusweb.voting.VotingEvaluator import VotingEvaluator


class MOPACSettings (SessionSettings):
	'''
	Settings for MOPAC negotiation. in MOPAC, each party may get a "power"
	parameter containing an natural number &le;1.
	'''
	
	def __init__(self, participants:List[TeamInfo] ,
			deadline:Deadline ,
			 votingevaluator:VotingEvaluator):
		'''
		@param participants the list of {@link PartyWithProfile} in clockwise
		            order. There must be at least 2 to run the MOPAC
		            protocol. This is not tested in the constructor
		            because this can be initialized with less, for use in
		            TournamentSettings.
		@param deadline     the {@link Deadline} for the negotiation
		@param votingeval   the {@link VotingEvaluator} to use.
		'''
		self._participants = participants;
		self._deadline = deadline;
		if participants == None or deadline == None or votingevaluator == None:
			raise ValueError(
					"participants, deadline and votingeval must be not none")
		self._votingevaluator = votingevaluator
		self._checkTeams();

	def getMaxRunTime(self)->float:
		return self._deadline.getDuration() / 1000.

	def getProtocol(self, logger:Reporter) -> SessionProtocol :
		from geniusweb.protocol.session.mopac.MOPACState import MOPACState
		from geniusweb.protocol.session.mopac.MOPAC import MOPAC

		return  MOPAC(MOPACState(None, [], None, self, {}), logger) 

	def getTeams(self ) -> List[TeamInfo] :
		return list(self._participants)
	
	def getParticipants(self ) -> List[TeamInfo] :
		'''
		bit hacky, same as getTeams, for deserialization...
		'''
		return list(self._participants)

	def getDeadline(self)-> Deadline :
		'''
		@return the deadline for this negotiation
		'''
		return self._deadline

	def getAllParties(self)->List[PartyWithProfile] :
		return [ particip.getParties()[0] for particip in self._participants]
	

	def getVotingEvaluator(self)->VotingEvaluator :
		'''
		@return a class that allows us to evaluate the voting results in
		        different ways, selectable by the user.
		'''
		return self._votingevaluator

	def With(self, team:TeamInfo ) -> "MOPACSettings" :
		if team.getSize() != 1:
			raise ValueError(
					"Added party must have one party but got " + str(team))
		newparts:List[TeamInfo]  = list(self._participants)
		newparts.append(team)
		return MOPACSettings(newparts, self._deadline, self._votingevaluator)

	def __repr__(self)->str:
		return "MOPACSettings[" + str(self._participants) + "," +\
				str(self._deadline) + "," + \
				type(self._votingevaluator).__name__ + "]";

	def getTeamSize(self)->int:
		return 1;

	def __hash__(self):
		return hash((tuple(self._participants), self._deadline, self._votingevaluator))
	
	def __eq__(self, other):
		return isinstance(other, self.__class__)\
			and self._participants == other._participants \
			and self._deadline == other._deadline \
			and self._votingevaluator == other._votingevaluator

	def _checkTeams(self):
		'''
		@throws IllegalArgumentException if teams have improper power settings.
		'''
		for team in self._participants:
			if team.getSize() != 1:
				raise ValueError("All teams must be size 1 but found " + str(team))
			party = team.getParties()[0]
			if 'power' in party.getParty().getParameters().getParameters():
				power = party.getParty().getParameters().get("power")
				if not isinstance(power, int):
					raise ValueError(
							"parameter 'power' for party" + str(party)
									+ " must be integer but found " + str(power))
				if power < 1:
					raise ValueError(
							"parameter 'power'  for party" + str(party)
									+ " must be >=1 but found " + str(power))

