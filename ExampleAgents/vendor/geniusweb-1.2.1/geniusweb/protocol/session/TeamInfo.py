from typing import List
from pyson.JsonTypeInfo import Id, As
from pyson.JsonTypeInfo import JsonTypeInfo

from geniusweb.protocol.tournament.Team import Team
from geniusweb.references.Parameters import Parameters
from geniusweb.references.PartyWithProfile import PartyWithProfile


@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
class TeamInfo :
	'''
	Contains a functional team, eg in SHAOP a team would be a SHAOP together with
	his COB partner. In SAOP this is just a SAOP party.
	'''

	def __init__(self,  parties: List[PartyWithProfile]):
		self._parties = parties

	 
	def getParties(self) ->List[PartyWithProfile] :
		'''
		@return the list of all parties involved, which is the parties in all
		teams combined.
		'''
		return list(self._parties)


	def getSize(self)-> int:
		'''
		@return the number of parties in the team.
		'''
		return len(self._parties)

	def __repr__(self)->str:
		return "TeamInfo[" +str( self._parties) + "]"

	def __hash__(self):
		return hash(tuple(self._parties))

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
            self._parties == other._parties

	def With(self, parameters:Parameters ) ->"TeamInfo" :
		'''
		@param parameters a set of {@link Parameters} to be merged with the
		                  existing parameters of the first team member.
		@return updated TeamInfo
		'''
		updatedparties = list(self._parties)
		party1 = updatedparties[0]
		newparams1 = party1.getParty().getParameters().WithParameters(parameters)
		party1update = PartyWithProfile(
				party1.getParty().With(newparams1), party1.getProfile())
		updatedparties[0]= party1update
		return TeamInfo(updatedparties)


	def getTeam(self)->Team:
		'''
		@return the Team, without the profiles
		'''
		return Team ([party.getParty() for party in self._parties])

