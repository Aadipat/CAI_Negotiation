from abc import ABC, abstractmethod

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import Id, As
from pyson.JsonTypeInfo import JsonTypeInfo

from geniusweb.actions.PartyId import PartyId


@JsonSubTypes(
    [
        "geniusweb.actions.EndNegotiation.EndNegotiation",
        "geniusweb.actions.Offer.Offer",
        "geniusweb.actions.Accept.Accept",
        "geniusweb.actions.LearningDone.LearningDone",
        "geniusweb.actions.Vote.Vote",
        "geniusweb.actions.Votes.Votes",
        "geniusweb.actions.Comparison.Comparison",
        "geniusweb.actions.ElicitComparison.ElicitComparison",
        "geniusweb.actions.VoteWithValue.VoteWithValue",
        "geniusweb.actions.VotesWithValue.VotesWithValue",
    ]
)
@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
class Action(ABC):
    """
    An action represents a "promise" made by a participant in the negotiation. It
    can not be retracted and is immutable. But it can be followed by other
    actions that override it or make it outdated.
    HACK for now this just extends dict intead of defining proper subclasses
    """

    @abstractmethod
    def getActor(self) -> PartyId:
        pass
