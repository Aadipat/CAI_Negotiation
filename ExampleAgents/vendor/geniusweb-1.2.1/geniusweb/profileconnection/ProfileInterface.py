from abc import ABC

from tudelft.utilities.listener.Listenable import Listenable

from geniusweb.profile.Profile import Profile


class ProfileInterface (Listenable[Profile] ):
	'''
	A container holding a modifyable profile. This interface allows testing.
	'''

	def getProfile(self) -> Profile :
		'''
		@return the latest version of the profile. May change at any time, after
		        someone updates the version on the server. Call to this may block
		        for limited time if the profile is not yet available.
		@throws IOException if profile can not be fetched
		'''
	

	def close(self):
		'''
		This must be called when the user is finished using the interface. The
		interface can not be used after calling this. This function allows
		implementors to release the streams and listeners. Not calling this after
		use may cause resource leaks.
		'''
