# Generated from java by J2P
from __future__ import annotations
from geniusweb.actions.ActionWithBid import ActionWithBid
from geniusweb.actions.PartyId import PartyId
from geniusweb.issuevalue.Bid import Bid
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import Optional
from typing import cast


class VoteWithValue(ActionWithBid):
 '''
 A vote is an indication by a party that it conditionally accepts a bid. It's
 then up to the protocol to determine the outcome.

 '''
 
 def __init__(self, actor:PartyId, bid:Bid, minPower:int, maxPower:int, value:int):
  '''
  @param actor       the {@link PartyId} that does the action
  @param bid      the bid that is voted on
  @param minPower the minimum power this bid must get in order for the vote
                  to be valid. Power is the sum of the powers of the
                  parties that are in the deal. If power=1 for all
                  participants (usually the default) power can be
                  interpreted as number of votes
  @param maxPower the maximum power this bid must get in order for the vote
                  to be valid. See {@link #minPower}
  @param value    the value for this vote. An integer in [1,100]. Higher
                  means that the actor likes this bid better. Note: value 0
                  is reserved for "unacceptable" and therefore can not be
                  used as a valid value.

  '''
  self.__minPower:int = None
  self.__maxPower:int = None
  self.__value:int = None
  super().__init__(actor,bid)
  if ((value < 1) or (value > 100)):
   raise ValueError("value must be in [1,100] but got " + value)
  if (((((bid is None) or (minPower is None)) or (minPower < 1)) or (maxPower is None)) or (maxPower < minPower)):
   raise ValueError("Vote must have non-null bid and minVotes, and minPower must be >=1 and maxPower must be >=minPower")
  self.__minPower=minPower
  self.__maxPower=maxPower
  self.__value=value
 
 def getMinPower(self) -> int:
  '''
  
  @return the minimum power this bid must get in order for the vote to be
          valid.

  '''
  return self.__minPower
 
 def getMaxPower(self) -> int:
  '''
  
  @return the max power this bid must get in order for the vote to be
          valid.

  '''
  return self.__maxPower
 
 def getValue(self) -> int:
  '''
  
  @return the value for this vote. An integer in [1,100]. Higher means that
          the actor likes this bid better.
  

  '''
  return self.__value
 
 #Override
 def __repr__(self) -> str:
  return "VoteWithValue[" + str(self.getActor()) + "," + str(self.getBid()) + "," + str(self.__minPower) + "," + str(self.__maxPower) + "," + str(self.__value) + "]"
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = safehash(super())
  result=((prime * result) + (0 if ((self.__maxPower is None)) else safehash(self.__maxPower)))
  result=((prime * result) + (0 if ((self.__minPower is None)) else safehash(self.__minPower)))
  result=((prime * result) + (0 if ((self.__value is None)) else safehash(self.__value)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if not(super().__eq__(obj)):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[VoteWithValue] = cast(VoteWithValue,obj)
  if (self.__maxPower is None):
   if (other.__maxPower is not None):
    return False
  else:
   if not(self.__maxPower == other.__maxPower):
    return False
  if (self.__minPower is None):
   if (other.__minPower is not None):
    return False
  else:
   if not(self.__minPower == other.__minPower):
    return False
  if (self.__value is None):
   if (other.__value is not None):
    return False
  else:
   if not(self.__value == other.__value):
    return False
  return True
