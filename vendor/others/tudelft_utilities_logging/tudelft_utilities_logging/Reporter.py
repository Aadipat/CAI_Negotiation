from abc import ABC, abstractmethod

class Reporter(ABC):
	'''
	logs events. We don't use {@link Logger} because that's not an interface and
	is hard to stub properly because the class is protected and builds on static
	code.
	'''

	@abstractmethod
	def log(self, level:int, msg:str, thrown:BaseException=None):
		'''
		Log a message, with associated Throwable information.
		
		@param level  One of the message level identifiers. Eg
		logging.WARNING 
		@param msg    The string message (or a key in the message catalog)
		@param thrown Exception associated with log message.
		'''

