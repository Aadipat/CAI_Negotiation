# Generated from java by J2P
from __future__ import annotations
from geniusweb.actions.ActionWithBid import ActionWithBid
from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import List
from typing import Optional
from typing import cast


class ElicitComparison(ActionWithBid):
 '''
 Request a comparison from the cob party. The party can do a
 {@link Comparison} action as a response.

 '''
 
 def __init__(self, actor:PartyId, bid:Bid, options:List[Bid]):
  '''
  @param actor   the eliciting party.
  @param bid  the bid to compare the options with
  @param options the available options that may be chosen from. Must not be
              null and must have at least 2 options.

  '''
  self.__options:List[Bid] = list()
  super().__init__(actor,bid)
  if (bid is None):
   raise ValueError("Bid to compare with must not be null")
  if ((options is None) or (len(options) < 1)):
   raise ValueError("opts must not be null and have at least 1 option")
  self.__options.extend(options)
 
 def getOptions(self) -> List[Bid]:
  '''
  
  @return the list of {@link Bid}s to compare {@link #getBid()} with

  '''
  return list(self.__options)
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = safehash(super())
  result=((prime * result) + (0 if ((self.__options is None)) else safehash(self.__options)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if not(super().__eq__(obj)):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[ElicitComparison] = cast(ElicitComparison,obj)
  if (self.__options is None):
   if (other.__options is not None):
    return False
  else:
   if not(self.__options == other.__options):
    return False
  return True
 
 #Override
 def __repr__(self) -> Optional[str]:
  return "ElicitComparison[" + str(self.getActor()) + "," + str(self.getBid()) + "," + str(self.__options) + "]"
