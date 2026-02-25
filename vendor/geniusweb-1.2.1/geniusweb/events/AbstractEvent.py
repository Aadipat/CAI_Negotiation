from abc import ABC
import time
from geniusweb.events.NegotiationEvent import NegotiationEvent



class AbstractEvent (NegotiationEvent, ABC):

	def __init__(self, now:int=round(1000*time.time())):
		'''
		@param now the current time to use. see {@link System#currentTimeMillis()}.
		Defaults to current time.
		'''
		if now == None or now < 0:
			raise ValueError("time must be non-null and positive")

		self._time = now;


	def getTime(self) ->int:
		return self._time


	def __repr__(self) ->str:
		return str(self.__class__.__name__) + "[" + str(self._time) + "]";

	def __hash__(self):
		return hash(self._time)


	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
			self._time==other._time


