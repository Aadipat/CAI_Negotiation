from geniusweb.deadline.DeadlineTime import DeadlineTime

class DeadlineRounds (DeadlineTime):
	'''
	The number of rounds that a session will be allowed to run. This extends
	DeadlineTime because a rounds deadline is an ADDITIONAL deadline on top of a
	normal time deadline. It is not hard defined what a round is, this is up to
	the protocol.
	'''

	def __init__(self, rounds:int, durationms:int):
		'''
		@param rounds     the max number of rounds for the session
		@param durationms the maximum time in milliseconds the session is allowed
		                  to run.
		'''
		super().__init__(durationms)
		if rounds <= 0:
			raise ValueError("deadline must have at least 1 round")
		self._rounds = rounds;

	def getRounds(self) ->int:
		return self._rounds;

	def __hash__(self):
		prime = 31
		result = super().__hash__()
		result = prime * result + hash(self._rounds)
		return result

	def __eq__(self, other):
		return isinstance(other, self.__class__) and \
				super().__eq__(other) and self._rounds == other._rounds


	def __repr__(self)->str:
		return "DeadlineRounds[" + str(self._rounds) + "," + str(self._durationms) + "]";

