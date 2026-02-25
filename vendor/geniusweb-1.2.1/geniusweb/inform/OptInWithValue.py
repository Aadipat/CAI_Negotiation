# Generated from java by J2P
from __future__ import annotations
from collections import Counter
from geniusweb.actions.VotesWithValue import VotesWithValue
from geniusweb.inform.Inform import Inform
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import List
from typing import Optional
from typing import Optional, Tuple
from typing import cast


class OptInWithValue(Inform):
 '''
 Informs party that it's time to Opt-in.

 '''
 
 def __init__(self, votes:List[VotesWithValue]):
  '''
  @param votes a list of votes. There may be only one votes per party.

  '''
  self.__votes:List[VotesWithValue] = None
  super().__init__()
  
  counts = Counter( [ vote.getActor() for vote in votes ] )
  
  nonunique:Optional[Tuple] = next( iter([(pid,cnt) for (pid,cnt) in counts.items() if cnt>1]), None)
  if nonunique!=None:
   raise ValueError("OptIn contains multiple Votes for party " + nonunique[0])
  self.__votes=votes
 
 def getVotes(self) -> List[VotesWithValue]:
  '''
  @return list of votes that can be opted in to

  '''
  return list(self.__votes)
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = 1
  result=((prime * result) + (0 if ((self.__votes is None)) else safehash(self.__votes)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if (obj is None):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[OptInWithValue] = cast(OptInWithValue,obj)
  if (self.__votes is None):
   if (other.__votes is not None):
    return False
  else:
   if not(self.__votes == other.__votes):
    return False
  return True
 
 #Override
 def __repr__(self) -> str:
  return "OptInWithValue[" + str(self.__votes) + "]"
