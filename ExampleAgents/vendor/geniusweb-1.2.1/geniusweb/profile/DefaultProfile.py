# Generated from java by J2P
from __future__ import annotations
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.profile.Profile import Profile
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import Optional
from typing import cast


class DefaultProfile(Profile):
 '''
 Set up such that jackson can look at the getters.
 

 '''
 
 def __init__(self, name:str, domain:Domain, reservationBid:Optional[Bid]):
  self.__name:str = None
  self.__domain:Domain = None
  self.__reservationBid:Optional[Bid] = None
  super().__init__()
  if name is None:
   raise ValueError("name must be not null")
  if (domain is None):
   raise ValueError("domain must be not null")
  self.__name=name
  self.__domain=domain
  self.__reservationBid=reservationBid
  if (reservationBid is not None):
   message:Optional[str] = domain.isFitting(reservationBid)
   if message is not None:
    raise ValueError("reservationBid is not fitting domain: " + message)
 
 #Override
 def getName(self) -> str:
  return self.__name
 
 #Override
 def getDomain(self) -> Domain:
  return self.__domain
 
 #Override
 def getReservationBid(self) -> Optional[Bid]:
  return self.__reservationBid
 
 def getValuesString(self) -> str:
  '''
  
  @return string of values contained in here. Useful to make derived
          toString functions

  '''
  return self.__name + "," + str(self.__domain) + "," + str(self.__reservationBid)
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = 1
  result=((prime * result) + (0 if ((self.__domain is None)) else safehash(self.__domain)))
  result=((prime * result) + (0 if (self.__name is None) else safehash(self.__name)))
  result=((prime * result) + (0 if ((self.__reservationBid is None)) else safehash(self.__reservationBid)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if (obj is None):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[DefaultProfile] = cast(DefaultProfile,obj)
  if (self.__domain is None):
   if (other.__domain is not None):
    return False
  else:
   if not(self.__domain == other.__domain):
    return False
  if self.__name is None:
   if other.__name is not None:
    return False
  else:
   if not(self.__name == other.__name):
    return False
  if (self.__reservationBid is None):
   if (other.__reservationBid is not None):
    return False
  else:
   if not(self.__reservationBid == other.__reservationBid):
    return False
  return True
