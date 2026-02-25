from __future__ import annotations
from typing import Set, Optional, List

from geniusweb.actions.AbstractAction import AbstractAction
from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.Vote import Vote
from geniusweb.issuevalue.Bid import Bid


class Votes (AbstractAction):
    '''
    Indicates that a party conditionally agrees with any of the {@link Vote}s
    provided.
    '''
    def __init__(self, actor: PartyId, votes:Set[Vote]):
        '''
        @param id    party id
        @param votes the {@link Vote}s that the party can agree on, if the
                     condition of the Vote holds. Every {@link Vote#getActor()}
                     should equal the id. There may be at most 1 vote per
                     {@link Bid}.
        '''
        super().__init__(actor)
        if votes == None:
            raise ValueError("votes must be not null");
        self._votes = votes.copy()
        for vote in self._votes:
            if not vote.getActor()== actor:
                raise ValueError("All votes must come from "\
                        + str(actor) + " but found " + str(vote))

        # check for duplicate Vote's, possibly with different powers
        votedfor:List[Bid] = []
        for vote in votes:
            bid = vote.getBid()
            if bid in votedfor:
                raise ValueError("Votes contains multiple Vote's for "+ str(bid))
            votedfor.append(bid)


    def isExtending(self, otherVotes:Votes ) -> bool:
        '''
        Test if Votes extends other votes. Extending means that for each vote on
        bid B with power P in othervotes, this contains also a vote for bid B
        with power at most P.
        
        @param otherVotes the {@link Votes}, usually from a previous round, that
                          this should extend.
        @return true iff this extends the otherVotes.
        '''
        if not otherVotes.getActor()==self.getActor():
            return False
        for vote in otherVotes.getVotes():
            myvote:Optional[Vote] = self.getVote(vote.getBid())
            if myvote == None or myvote.getMinPower() > vote.getMinPower()   or myvote.getMaxPower() < vote.getMaxPower(): # type:ignore
                return False

        return True


    def getVote(self, bid:Bid ) -> Optional[Vote] :
        '''
        @param bid the bid that we may have a vote for
        @return myvote for bid, or null if no vote for that bid;
        '''
        for vote in self._votes:
            if vote.getBid() == bid:
                return vote;
        return None;

    def getVotes(self) -> Set[Vote]:
        return self._votes.copy()

    
    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            self._actor==other._actor and self._votes==other._votes

    def __hash__(self):
        return hash((self._actor, tuple(self._votes)))
    
    def __repr__(self) -> str :
        return "Votes[" + str(self._actor) + "," +\
             str(self._votes) + "]"

