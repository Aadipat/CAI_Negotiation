from geniusweb.actions.Action import Action
from geniusweb.inform.Inform import Inform


class ActionDone (Inform):
	'''
	Informs that someone did an action
	'''

	def __init__(self, action:Action ):
		self._action = action;
	
	
	def getAction(self) -> Action:
		return self._action;
	
	def __repr__(self):
		return "ActionDone[" + str(self._action) + "]"
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and super().__eq__(other) \
			and self._action == other._action
			
	def __hash__(self):
		return hash(self._action)