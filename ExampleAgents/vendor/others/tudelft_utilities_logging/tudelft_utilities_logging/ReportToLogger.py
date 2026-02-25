from logging import Logger
import logging
from typing import cast

from tudelft_utilities_logging.Reporter import Reporter


# initialize the logging, otherwise it seems not to work properly
logging.basicConfig()

class ReportToLogger ( Reporter ):
	'''
	dumps the reported messages into a log file with the
	given name.
	This really tries hard to avoid any writing to 
	stdout/stderr, because those are used
	for the communicatino to the party.
 	'''

	def __init__(self, logname:str):
		'''
		@param logname the name for the Logger
	 	'''
		self._logger:Logger = logging.getLogger(logname)
		# HACK to remove parent. Parent prints to stdout and 
		# preventing that is exactly why we have a logger here.
		self._logger.parent=cast(Logger, None)
		handler = logging.FileHandler(logname+".log")
		formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
		handler.setFormatter(formatter)
		self._logger.addHandler(handler)
		self._logger.setLevel(logging.INFO)

	def log(self, level:int , msg:str, thrown: BaseException=None) -> None:
		# We use the internal function, the only way to include our exception...
		self._logger._log(level=level, msg=msg, args=[], exc_info=thrown,\
			stack_info=True if thrown else False)
	

	