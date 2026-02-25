import json 
from pathlib import Path

from pyson.ObjectMapper import ObjectMapper 
from tudelft.utilities.listener.DefaultListenable import DefaultListenable

from geniusweb.profile.Profile import Profile
from geniusweb.profileconnection.ProfileInterface import ProfileInterface


class FileProfileConnector (DefaultListenable[Profile], ProfileInterface):
	'''
	ProfileInterface based on a plain filesystem UTF8 file.
	'''
	_pyson = ObjectMapper()

	def __init__(self,  filename:str) :
		'''
		@param filename the filename of the file containing the profile
		@throws IOException if the profile is not proper json
		'''
		serialized = Path(filename).read_text("utf-8")
		self._profile:Profile = self._pyson.parse(json.loads(serialized), Profile) #type:ignore
	
	#Override
	def getProfile(self) ->Profile :
		return self._profile

	#Override
	def close(self) :
		pass
