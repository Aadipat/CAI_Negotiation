from geniusweb.actions.AbstractAction import AbstractAction
from geniusweb.actions.PartyId import PartyId

class LearningDone ( AbstractAction):
	'''
	 * Indicates that a party turns away from the negotiation and.

	'''
	def __init__(self, actor:PartyId ):
		super().__init__(actor)

	def __repr__(self):
		return "LearningDone[" + str(self.getActor()) + "]";

