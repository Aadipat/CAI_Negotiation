import time

from geniusweb.events.CurrentState import CurrentState
from geniusweb.protocol.NegoState import NegoState


class CurrentNegoState (CurrentState):
	'''
	Implementation of CurrentState event. This contains NegoState and therefore
	can not be defined in the events module.
	'''

	def __init__(self,  state:NegoState, now:int=round(1000*time.time())) :
		super().__init__(now)
		self._state = state;


	def getState(self) -> NegoState:
		return self._state

		
	def __repr__(self):
		return "CurrentNegoState[" + str(self.getTime())\
			 + "," + str(self._state) + "]"

	def __hash__(self):
		return hash((self._state, self._time))

	def __eq__(self, other):
		return super().__eq__(other) and \
			self._state==other._state
