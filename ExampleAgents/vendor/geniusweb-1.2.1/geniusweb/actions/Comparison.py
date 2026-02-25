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


class Comparison(ActionWithBid):
 '''
 @return All bids that are worse than the bid. Maybe empty
 
 A statement from a Party that some bids are better and worse than
 {@link #getBid()} bid. Typically this is a response to a CompareWithBid
 inform
 

 '''
 
 def __init__(self, actor:PartyId, bid:Bid, better:List[Bid], worse:List[Bid]):
  '''
  @param actor  the party id that made this comparison
  @param bid    the bid that is compared wiht
  @param better list of bids that are better than bid
  @param worse  list of bids that are worse than bid

  '''
  self.__better:List[Bid] = list()
  self.__worse:List[Bid] = list()
  super().__init__(actor,bid)
  if (((bid is None) or (better is None)) or (worse is None)):
   raise ValueError("bid, better and worse must not be null")
  self.__better.extend(better)
  self.__worse.extend(worse)
 
 def getBetter(self) -> List[Bid]:
  '''
  @return All bids that are better than the bid. Maybe empty
  

  '''
  return self.__better
 
 def getWorse(self) -> List[Bid]:
  return self.__worse
 
 #Override
 def __repr__(self) -> str:
  return "Comparison[" + str(self.getActor()) + "," + str(self.getBid()) + ",better=" + str(self.__better) + ",worse=" + str(self.__worse) + "]"
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = safehash(super())
  result=((prime * result) + (0 if ((self.__better is None)) else safehash(self.__better)))
  result=((prime * result) + (0 if ((self.__worse is None)) else safehash(self.__worse)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if not(super().__eq__(obj)):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[Comparison] = cast(Comparison,obj)
  if (self.__better is None):
   if (other.__better is not None):
    return False
  else:
   if not(self.__better == other.__better):
    return False
  if (self.__worse is None):
   if (other.__worse is not None):
    return False
  else:
   if not(self.__worse == other.__worse):
    return False
  return True
