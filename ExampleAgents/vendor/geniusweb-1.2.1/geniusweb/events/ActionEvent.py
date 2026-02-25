from geniusweb.actions.Action import Action
from geniusweb.events.AbstractEvent import AbstractEvent
class ActionEvent ( AbstractEvent):
	'''
	Event where a party did an {@link Action}
	'''

	def __init__(self, action:Action ,	time:int) :
		'''
		@param action the {@link Action} that was done
		@param time   the current time to use. in millisec since 1970.
		'''
		super().__init__(time)
		if not action:
			raise ValueError("Action must not be null")
		self._action = action

	def getAction(self)->Action :
		'''
		@return action done by some party in the system.
		'''
		return self._action

	
	def __repr__(self):
		return type(self).__name__ + "[" + str(self.getTime())\
			 + "," + str(self._action) + "]"

	def __hash__(self):
		return hash((self._action, self._time))

	def __eq__(self, other):
		return super().__eq__(other) and \
			self._action==other._action
