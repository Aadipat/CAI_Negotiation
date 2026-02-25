from abc import ABC, abstractmethod
from datetime import datetime
from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import JsonTypeInfo, Id, As

@JsonTypeInfo(use = Id.NAME, include = As.WRAPPER_OBJECT)
@JsonSubTypes([ "geniusweb.progress.ProgressTime.ProgressTime", "geniusweb.progress.ProgressRounds.ProgressRounds"] )
class Progress(ABC):
	'''
	Progress is similar to {@link Deadline} but contains absolute values. It
	always contains a hard termination moment at which the party should be
	killed. This is used to free up the run server. The protocol should always
	check its own clock, as parties may be ignoring or cheating with the
	deadline.
	<p>
	immutable.

	'''
	@abstractmethod
	def get(self,currentTimeMs:int)->float:
		'''
		@param currentTimeMs the current time in ms since 1970 as from
		                     {@link System#currentTimeMillis()}.
		@return the current time as a fraction of the total amount of time/rounds
		        available. So at start this returns 0, and when (and after) the
		        deadline is reached this returns 1. Notice that when the progress
		        is about the number of rounds, the party may also want to keep an
		        eye on {@link #getTerminationTime()}.
		'''
	 
	@abstractmethod
	def getTerminationTime(self)->datetime :
		'''
		@return the unix time (UTC, ms since 1970) at which the party will be
		        terminated. At this time the server can remove the party and free
		        up its resources. Notice that server and party implementations
		        are free to ignore this, the protocol should always check on
		         whether a party is out of time.
		'''

	@abstractmethod
	def isPastDeadline(self, currentTimeMs:int) -> bool:
		'''
		@param currentTimeMs the current time in ms since 1970 as from
		                     {@link System#currentTimeMillis()}.
		@return true iff the progress has passed the deadline.
		'''
