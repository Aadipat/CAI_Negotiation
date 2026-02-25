# Generated from java by J2P
from __future__ import annotations
from collections import Counter
from collections.abc import Set as AbcSet
from geniusweb.actions.AbstractAction import AbstractAction
from geniusweb.actions.PartyId import PartyId
from geniusweb.actions.VoteWithValue import VoteWithValue
from geniusweb.issuevalue.Bid import Bid
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import Optional
from typing import Set
from typing import cast


class VotesWithValue(AbstractAction):
 '''
 Indicates that a party conditionally agrees with any of the
 {@link VoteWithValue}s provided.

 '''
 
 def __init__(self, actor:PartyId, votes:Set[VoteWithValue]):
  '''
  
  @param actor party id
  @param votes the {@link Vote}s that the party can agree on, if the
               condition of the Vote holds. Every {@link Vote#getActor()}
               should equal the id. The sum of the values must =100.

  '''
  self.__votes:Set[VoteWithValue] = set()
  super().__init__(actor)
  if (votes is None):
   raise ValueError("votes must be not null")
  for vote in votes :
   vote:VoteWithValue = vote
   if not(vote.getActor() == actor):
    raise ValueError("All votes must come from " + str(actor) + " but found " + str(vote))
  if sum( [ v.getValue() for v in votes] ) != 100:
    raise ValueError("Sum of the placed votes must be 100")
  
  counts = Counter( [ vote.getBid() for vote in votes ] )
  
  nonunique:Optional[Bid] = next( iter([(bid,cnt) for (bid,cnt) in counts.items() if cnt>1]), None)
  if nonunique!=None:
   raise ValueError("Votes contains multiple Vote's for " + str(nonunique[0]))
  self.__votes.update((lambda _: frozenset(_) if isinstance(_, AbcSet) else _)(votes))
 
 def isExtending(self,otherVotes:VotesWithValue) -> bool:
  '''
  Test if Votes extends other votes. Extending means that for each vote on
  bid B with power P in othervotes, this contains also a vote for bid B
  with power at most P.
  
  @param otherVotes the {@link VotesWithValue}, usually from a previous
                    round, that this should extend.
  @return true iff this extends the otherVotes.

  '''
  if not(otherVotes.getActor() == self.getActor()):
   return False
  for vote in otherVotes.getVotes() :
   vote:VoteWithValue = vote
   myvote:VoteWithValue = self.getVote(vote.getBid())
   if (((myvote is None) or (myvote.getMinPower() > vote.getMinPower())) or (myvote.getMaxPower() < vote.getMaxPower())):
    return False
  return True
 
 def getVote(self,bid:Bid) -> Optional[VoteWithValue]:
  '''
  
  @param bid the bid that we may have a vote for
  @return myvote for bid, or null if no vote for that bid;

  '''
  for vote in self.__votes :
   vote:VoteWithValue = vote
   if vote.getBid() == bid:
    return vote
  return None
 
 def getVotes(self) -> Set[VoteWithValue]:
  return frozenset(self.__votes)
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = safehash(super())
  result=((prime * result) + (0 if ((self.__votes is None)) else safehash(self.__votes)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if not(super().__eq__(obj)):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[VotesWithValue] = cast(VotesWithValue,obj)
  if (self.__votes is None):
   if (other.__votes is not None):
    return False
  else:
   if not(self.__votes == other.__votes):
    return False
  return True
 
 #Override
 def __repr__(self) -> str:
  return "VotesWithValue[" + str(self.getActor()) + "," + str(self.__votes) + "]"
