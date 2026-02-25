from datetime import datetime
class NoResourcesNowException( Exception): 
	'''
	Indicates that we are out of resources to handle the request. But this can be
	remedied by trying again later.
	'''
	def __init__(self, message:str, suggestedLater:datetime):
		'''
		@param message        the detail message
		@param suggestedLater the suggested time to retry
		'''
		super().__init__(message)
		self._later = suggestedLater;

	def getLater(self)->datetime:
		return self._later
	
	