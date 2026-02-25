from typing import List

from tudelft_utilities_logging.Reporter import Reporter

from geniusweb.protocol.NegoSettings import NegoSettings
from geniusweb.protocol.session.SessionProtocol import SessionProtocol
from geniusweb.protocol.session.TeamInfo import TeamInfo
from geniusweb.references.PartyWithProfile import PartyWithProfile


class SessionSettings(NegoSettings):
	'''
	interface for settings for session protocols. Immutable.
	'''
	def getTeams(self)->List[TeamInfo] :
		'''
		Get the {@link TeamInfo}s.
		
		@return list of {@link PartyWithProfile} items.
		'''

	def getTeamSize(self) -> int:
		'''
		@return the size of each {@link TeamInfo}. Usually 1 (SAOP etc) or
		        sometimes 2 (SHAOP). Used eg by tournament runner to determine
		        proper team construction.
		'''

	def With(self, partyprofteam:TeamInfo ) -> "SessionSettings" :
		'''
		Allows modification of SessionSettings to include a party. This is needed
		for tournament auto-configuration of sessions.
		
		@param partyprofteam the {@link TeamInfo} to be added
		@return new modified SessionSettings object
		'''
	
	def getAllParties(self) -> List[PartyWithProfile]:
		'''
		@return all parties from all teams, as a flattened ordered list. The
	        order : start with all parties from team 1, then all from team 2,
	        etc. The specific order of the parties from a team depends on the
	        protocol.
		'''

	def getProtocol(self,  logger:Reporter)->SessionProtocol :
		'''
		@param logger the logger where the protocol can log events to.
		@return the an initialized and ready to use {@link SessionProtocol} that
		    can handle this Negotiation.
		'''
