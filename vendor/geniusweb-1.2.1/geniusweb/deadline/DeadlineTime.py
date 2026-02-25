from pyson.JsonGetter import JsonGetter

from geniusweb.deadline.Deadline import Deadline


class DeadlineTime ( Deadline):
	'''
	How long a session will be allowed to run
	'''

	def __init__(self, durationms:int ):
		'''
		@param durationms number of milliseconds the session will be allowed to run
		'''
		if durationms <= 0:
			raise ValueError("deadline must be positive time");
		self._durationms = durationms

	@JsonGetter("durationms")
	def getDuration(self) -> int:
		'''
		@return the duration of this deadline, measured in milliseconds
		'''
		return self._durationms;

	def __repr__(self) -> str:
		return "DeadlineTime[" + str(self._durationms) + "]";


	def __hash__(self):
		return hash(self._durationms)

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._durationms == other._durationms

