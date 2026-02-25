from __future__ import annotations
from datetime import datetime

from geniusweb.progress.Progress import Progress


class ProgressRounds (Progress):
	'''
	progress in terms of number of rounds. The round has to be updated by the
	user of this class, calling {@link #advance()}. immutable.
	'''

	def __init__(self, duration:int, currentRound:int, endtime:datetime):
		'''
		@param duration     length max number of rounds, must be positive (not 0)
		@param currentRound the current round number (can be from 0 to deadlne).
		                    When = deadline, it means the progress has gone past
		                    the deadline.
		@param end          the termination time of this session. 
							WARNING due to a bug in python for windows, this value must be 
		             		at least 100000 seconds above jan. 1, 1970.
		'''
		if duration <= 0:
			raise ValueError("deadline must be positive but is " + str(duration))
		if currentRound < 0 or currentRound > duration:
			raise ValueError("current round must be inside [0," + str(duration) + "]")
		self._duration = duration
		self._currentRound = currentRound
		self._endtime = endtime

	def getTerminationTime(self) -> datetime:
		return self._endtime

	def getDuration(self):
		'''
		@return max number of rounds, positive  integer (not 0)
		'''
		return self._duration
	
	def getEndtime(self):
		return self._endtime

	def getCurrentRound(self) -> int:
		'''
		@return the current round. First round is 0. It is recommended that you
		        use the functions in {@link Progress} instead of this, to ensure
		        your code works with all implementations of Progress including
		        future developments.
		'''
		return self._currentRound

	def getTotalRounds(self) -> int:
		'''
		@return total number of rounds. It is recommended that you use the
		        functions in {@link Progress} instead of this, to ensure your
		        code works with all implementations of Progress including future
		        developments.
		'''
		return self._duration

	def get(self, currentTimeMs:int) -> float:
		# deadline and current both are limited to MAXINT is 32 bits; double
		# fits 52
		# bits so this should not result in accuracy issues
		ratio:float = self._currentRound / self._duration;
		if ratio > 1:
			ratio = 1;
		elif ratio < 0:
			ratio = 0;
		return ratio;

	def isPastDeadline(self, currentTimeMs:int) -> bool:
		return self._currentRound >= self._duration or \
			currentTimeMs > int(1000 * datetime.timestamp(self._endtime))

	def advance(self) -> "ProgressRounds":
		'''
		@return new ProgressRounds with round 1 advanced (or this, if
		        currentRound= duration). This is up to the user, as it is up to
		        the used protocol what exactly is a round.
		'''
		if self._duration == self._currentRound:
			return self
		return ProgressRounds(self._duration, self._currentRound + 1, self._endtime)

	def __hash__(self):
		return hash((self._currentRound, self._duration))
	
	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._currentRound == other._currentRound \
			and self._duration == other._duration \
			and self._endtime == other._endtime

	def __repr__(self):
		return "ProgressRounds[" + str(self._currentRound) \
			+" of " + str(self._duration) + "]"
