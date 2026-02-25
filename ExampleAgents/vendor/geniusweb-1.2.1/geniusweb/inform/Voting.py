from typing import Dict, List

from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.inform.Inform import Inform


class Voting (Inform):
    '''
    Informs a party that it's time to do voting.
    '''
    def __init__(self, offers:List[Offer] , powers:Dict[PartyId,int] ):
        self._offers = offers
        self._powers = powers

    def getOffers(self) -> List[Offer] :
        '''
        @return list of bids to be voted on
        '''
        return list(self._offers);

    def getPowers(self) -> Dict[PartyId, int]:
        '''
        @return map with the power of each party in the negotiation. This map may
                contain parties that are already finished, eg they reached an
                 agreement or walked away.
        '''
        return dict(self._powers)

    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            self._offers==other._offers and self._powers==other._powers

    def __hash__(self):
        return hash((tuple(self._offers), tuple(self._powers.items())))

    def __repr__(self)->str :
        return "Voting[" + str(self._offers) + "," + str(self._powers) + "]";

