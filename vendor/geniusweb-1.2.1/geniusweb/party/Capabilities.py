from typing import Set


class Capabilities:
	'''
	The capabilities of a party
	'''
	

	knownprofileclasses = [
		"geniusweb.profile.utilityspace.UtilitySpace",
		"geniusweb.profile.utilityspace.LinearAdditive",
		"geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace",
		"geniusweb.profile.utilityspace.SumOfGroupsUtilitySpace",
		"geniusweb.profile.DefaultPartialOrdering",
		"geniusweb.profile.FullOrdering",
		"geniusweb.profile.DefaultProfile",
		"geniusweb.profile.Profile",
		"geniusweb.profile.PartialOrdering",
		]

	def __init__(self, behaviours:Set[str], profiles:Set[str]):
		'''
	 	@param behaviours the {@link ProtocolRef} that a Party can handle, as
	                    returned by NegoProtocol.getRef()
	 	@param profiles   the {@link Profile} classes that Party acan handle
		'''
		if (behaviours == None):
			raise ValueError("behaviours==null")
		
		prof:str
		for  prof in profiles:
			if prof not in self.knownprofileclasses:
				raise ValueError("profile " + prof + " must be a subclass of Profile")
		self.__behaviours = behaviours
		self.__profiles = profiles
	
	def getBehaviours(self)-> Set[str]:
		'''
		@return the behaviours (protocols) that are supported
		'''
		return self.__behaviours

	def getProfiles(self)-> Set[str]:
		'''
		@return the profile classes that are supported
		'''
		return self.__profiles

	def __repr__(self)-> str:
		return "Capabilities[" + str(self.__profiles)+"," + str(self.__behaviours) + "]"

	def __hash__(self):
		return hash((tuple(self.__profiles), tuple(self.__behaviours)))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			 and  self.__profiles == other.__profiles \
			 and self.__behaviours==other.__behaviours
