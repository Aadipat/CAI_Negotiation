
from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import JsonTypeInfo, As, Id

from abc import ABC, abstractmethod

@JsonTypeInfo(use = Id.NAME, include = As.WRAPPER_OBJECT)
@JsonSubTypes( ["geniusweb.deadline.DeadlineRounds.DeadlineRounds","geniusweb.deadline.DeadlineTime.DeadlineTime" ])
class Deadline(ABC):
	'''
	Deadline indicates how long a session will be allowed to run. So it contains
	"relative" data (relative to the unknown start time of the session)
	'''
	@abstractmethod
	def getDuration(self):
		'''
		@return the duration of this deadline, measured in milliseconds
		'''
