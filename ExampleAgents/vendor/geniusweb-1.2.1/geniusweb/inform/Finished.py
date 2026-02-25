from geniusweb.inform.Agreements import Agreements
from geniusweb.inform.Inform import Inform


class Finished (Inform):
	'''
	Informs that the session is finished, and also contains the bid that was
	agreed on.

	'''

	def __init__(self, agreements:Agreements ):
		'''
		The session finished (can be for any reason).
		
		 @param agreements the {@link Agreements} that were finally agreed on.

		'''
		if not agreements:
			raise ValueError("Agreements must be not None")
		self._agreements = agreements;

	def getAgreements(self) -> Agreements :
		return self._agreements;


	def __repr__(self):
		return "Finished["+str(self._agreements)+"]"


	def __eq__(self, other):
		return isinstance(other, self.__class__) and super().__eq__(other) \
			and self._agreements == other._agreements

	def __hash__(self):
		return hash(self._agreements)