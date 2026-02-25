from geniusweb.actions.Action import Action
from geniusweb.actions.PartyId import PartyId

class AbstractAction ( Action ):

	def __init__(self, actor:PartyId):
		'''
		@param id the {@link PartyId} of the party executing the action. Usually
		          the negotiation system will check that parties only use their
		          own Id when doing actions.
		'''
		self._actor = actor;
	

	def  getActor(self) -> PartyId:
		return self._actor;

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._actor==other._actor
		
	def __hash__(self):
		return hash(self._actor)