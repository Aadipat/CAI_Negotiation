from datetime import datetime

from geniusweb.progress.Progress import Progress


class ProgressTime (Progress):
	'''
	keeps track of progress towards the Deadline and the time/rounds left.
	immutable. However, the time progresses nevertheless since this refers to the
	system clocks. immutable.
	'''

	def __init__(self, duration: int, start:datetime):
		'''
		@param d     the duration, eg {@link DeadlineTime#getDuration()}. Must be
		             &gt; 0.
		@param start the start Date (unix time in millisecs since 1970). See
		             {@link System#currentTimeMillis()}. WARNING
		             due to a bug in python for windows, this value must be 
		             at least 100000 seconds above jan. 1, 1970.
		'''
		self._start = start;
		self._duration = 1 if duration == None or duration <= 0 else duration

	def get(self, currentTimeMs:int) -> float:
		delta = currentTimeMs - 1000 * datetime.timestamp(self._start);
		# double should have ~53 digits of precision, and we're computing
		# deltas here.
		# 2^53 millis seems plenty for our purposes so no need to use
		# BigDecimal here.
		ratio:float = delta / self._duration;
		if ratio > 1:
			ratio = 1
		elif ratio < 0:
			ratio = 0
		return ratio

	def isPastDeadline(self, currentTimeMs:int) -> bool:
		return currentTimeMs > int(datetime.timestamp(self._start) * 1000) + self._duration;

	def getStart(self) -> datetime:
		'''
		@return time measured in milliseconds, between the start time and
		        midnight, January 1, 1970 UTCas returned from
		        {@link System#currentTimeMillis()}
		'''
		return self._start;

	def getDuration(self) -> int:
		'''
		@return duration in milliseconds.
		'''
		return self._duration;

	def getTerminationTime(self) -> datetime:
		return datetime.fromtimestamp((int(datetime.timestamp(self._start) * 1000) + self._duration) / 1000.);

	def __repr__(self):
		return "ProgressTime[" + str(int(1000 * datetime.timestamp(self._start))) + " , " + str(self._duration) + "ms]"

	def __hash__(self):
		return hash((self._duration, self._start))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			and self._duration == other._duration \
			and self._start == other._start

