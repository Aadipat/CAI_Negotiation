from abc import ABC

from pyson.JsonSubTypes import JsonSubTypes
from pyson.JsonTypeInfo import Id, As
from pyson.JsonTypeInfo import JsonTypeInfo


@JsonSubTypes(
    [
        "geniusweb.inform.Settings.Settings",
        "geniusweb.inform.YourTurn.YourTurn",
        "geniusweb.inform.ActionDone.ActionDone",
        "geniusweb.inform.Finished.Finished",
        "geniusweb.inform.OptIn.OptIn",
        "geniusweb.inform.OptInWithValue.OptInWithValue",
        "geniusweb.inform.Voting.Voting",
    ]
)
@JsonTypeInfo(use=Id.NAME, include=As.WRAPPER_OBJECT)
class Inform(ABC):
    """
    base class of all information sent to a Party
    HACK for now this just extends dict, instead
    of properly defining all subclasses.
    """

    def __eq__(self, other):
        return isinstance(other, self.__class__)
