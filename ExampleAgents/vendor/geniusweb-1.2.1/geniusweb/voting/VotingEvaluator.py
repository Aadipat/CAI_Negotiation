from abc import ABC, abstractmethod
from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import Id, As
from pyson.JsonTypeInfo import JsonTypeInfo
from geniusweb.inform.Agreements import Agreements
from geniusweb.voting.CollectedVotes import CollectedVotes


@JsonSubTypes(["geniusweb.voting.votingevaluators.LargestAgreement.LargestAgreement",
			"geniusweb.voting.votingevaluators.LargestAgreementsLoop.LargestAgreementsLoop"])
@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
class VotingEvaluator(ABC) :
	'''
	Evaluates the {@link CollectedVotes}, determining the agreements and if the
	negotiation should continue.
	
	Implementations should be immutable and not serialize internal variables (eg
	&#64;JsonIgnore them).
	'''
	@abstractmethod
	def create(self, votes:CollectedVotes)->"VotingEvaluator" :
		'''
		This function is the effective constructor. This mechanism serves several
		purposes:
		<ul>
		<li>It defines the constructor at interface level, so that we can ensure
		it's available and can call it given an instance,
		<li>We can use a (typically blank) instance of this to make more
		instances
		<li>You can cache intermediate results in the object for caching
		</ul>
		
		@param votes the Votes made by parties in the round to be evaluated.. All
		             active parties in the negotiation must be available, even if
		             they did not vote, to ensure that {@link #isFinished()} can
		             work properly.
		
		@return new VotingEvaluation object containing the given votes.
		'''

	@abstractmethod
	def getAgreements(self)-> Agreements:
		'''
		@return the agreements that is contained in the current available votes.
		        The exact procedure varies with the implementation.
		'''

	def isFinished(self )->bool:
		'''
		@return true iff the negotiation is finished after taking the agreement
	        returned by {@link #getAgreements()}
		'''

