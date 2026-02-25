from typing import List

from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.Votes import Votes
from geniusweb.inform.Inform import Inform


class OptIn (Inform):
    '''
    Informs party that it's time to Opt-in.

    '''
    def __init__(self, votes:List[Votes] ) :
        '''
        @param votes a list of votes. There may be only one votes per party.
        '''
        self._votes = votes;

        parties:List[PartyId] = []
        for vots in votes:
            partyid = vots.getActor()
            if partyid in parties:
                raise ValueError("OptIn contains multiple Votes for party " + str(partyid))
            parties.append(partyid)

    def getVotes(self)->List[Votes] :
        '''
        @return list of Votes that can be opted in to
        '''
        return list(self._votes);

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self._votes==other._votes

    def __hash__(self):
        return hash(tuple(self._votes))
    
    def __repr__(self) -> str :
        return "OptIn[" + str(self._votes) + "]"

