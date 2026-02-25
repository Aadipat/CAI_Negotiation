from geniusweb.inform.Inform import Inform
from geniusweb.progress.Progress import Progress 
from geniusweb.references.Parameters import Parameters
from geniusweb.references.ProfileRef import ProfileRef
from geniusweb.references.ProtocolRef import ProtocolRef
from geniusweb.actions.PartyId import PartyId


class Settings (Inform):
	'''
	Informs a Party about all settings for the upcoming negotiation session. This
	should be sent to a party one time, so that the party knows the situation.
	'''
	
	def __init__(self, id:PartyId , profile:ProfileRef ,protocol:ProtocolRef ,
			progress:Progress ,parameters:Parameters ):
		'''
		@param id         the {@link PartyId} for this party
		@param profile    the profile used for this party in this session
		@param protocol   the protocol used in this session
		@param progress   the {@link Progress} object used for this session
		@param parameters a {@link Map} &lt;String, Object&gt; containing
		                  initialization parameters for this party. The Object
		                  can be a HashMap, ArrayList, String, or number
		                  (Integer, Double, etc). The Object should not be just
		                  any Object because deserialization will work only with
		                   the mentioned types.
		'''
		assert isinstance(id, PartyId)
		assert isinstance(profile, ProfileRef)
		assert isinstance(protocol, ProtocolRef)
		assert isinstance(progress, Progress)
		assert isinstance(parameters, Parameters)
		
		self._profile = profile;
		self._protocol = protocol;
		self._progress = progress;
		self._parameters = parameters;
		self._id = id;

	def getProfile(self) -> ProfileRef:
		'''
		@return the profile used for this party in this session
		'''
		return self._profile

	def getProtocol(self) -> ProtocolRef :
		return self._protocol
	
	def	getProgress(self) -> Progress :
		'''
		@return the {@link Progress} object used for this session
		'''
		return self._progress 
	

	def getID(self) -> PartyId :
		'''
		@return the party ID of this party
		'''
		return self._id

	def getParameters(self)->Parameters  :
		'''
		@return a {@link HashMap}&lt;String,Object&gt; containing initialization
		        parameters that can be used by the party.
		'''
		return self._parameters

	def __repr__(self)->str:
		return "Settings[" + str(self._id) + "," + str(self._profile) + "," + \
			str(self._protocol) + ","+ str(self._progress) + "," + str(self._parameters) + "]"
	
	def __eq__(self, other):
		return isinstance(other, self.__class__)\
			and self._profile == other._profile \
			and self._protocol == other._protocol \
			and self._progress == other._progress \
			and self._parameters == other._parameters\
			and	self._id == other._id

	def __hash__(self):
		return hash((self._id, self._parameters, self._progress, self._protocol, self._profile))

