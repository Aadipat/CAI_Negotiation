# Generated from java by J2P
from __future__ import annotations
from collections.abc import Set as AbcSet
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.profile.DefaultProfile import DefaultProfile
from geniusweb.profile.PartialOrdering import PartialOrdering
from tudelft.utilities.tools.dictkeys import Keys
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import cast


# Strange that we need to do this. Bid is completely standard. The complication
# that this solves is that the keys are places as STRING in the json code
# because json allows only strings as key.
# key deserializer not needed in python
# Key serializer not needed in python
class DefaultPartialOrdering(DefaultProfile, PartialOrdering):
 '''
 Default implementation of partial ordering that stores all is-better
 relations explicitly in a map.
 
 NOTICE this can handle profiles of max size Integer. This is because various
 functions used here rely on basic java functions that can handle only int.
 Besides, the size of partial maps grows very rapidly so this approach is
 limited anyway.

 '''
 
 def __init__(self, name:str, domain:Domain, reservationBid:Optional[Bid], better:Dict[Bid,Set[Bid]]):
  # not needed in pyson, has fallback for key (de)serialization
  # not needed in pyson, has fallback for key (de)serialization
  '''
  Set is sparsely filled. If a Bid is not a key, it is not better than any
  other bid.

  '''
  self.__better:Dict[Bid,Set[Bid]] = dict()
  super().__init__(name,domain,reservationBid)
  self.__better.update(better)
 
 #Override
 def isPreferredOrEqual(self,bid1:Bid,bid2:Bid) -> bool:
  if not(bid1 in self.__better.keys()):
   return False
  return bid2 in self.__better.get(bid1)
 
 def getBids(self) -> List[Bid]:
  '''
  
  @return a list with all the bids that are referred to, either as better
          or as worse than another bid

  '''
  #  FIXME the iteration order may not be guaranteed!
  bids:Set[Bid] = set()
  for bid in Keys(self.__better) :
   bid:Bid = bid
   bids.add((lambda _: frozenset(_) if isinstance(_, AbcSet) else _)(bid))
   bids.update((lambda _: frozenset(_) if isinstance(_, AbcSet) else _)(self.__better.get(bid)))
  return list(bids)
 
 def getBetter(self) -> Dict[Bid,Set[Bid]]:
  '''
  
  @return the better map.

  '''
  return dict(self.__better)
 
 def getBetterList(self) -> List[List[int]]:
  '''
  @return a list of tuples [bid1index, bid2index]. It indicates that
          bids[bid1index] isbetterthan bids[bid2index].

  '''
  betterlist:List[List[int]] = list()
  bidslist:List[Bid] = self.getBids()
  for bid in bidslist :
   bid:Bid = bid
   if bid in self.__better.keys():
    for worsebid in self.__better.get(bid) :
     worsebid:Bid = worsebid
     betterlist.append([bidslist.index(bid),bidslist.index(worsebid)])
  return betterlist
 
 #Override
 def __repr__(self) -> str:
  return type(self).__name__ + "[" + self.getValuesString() + "," + str(self.__better) + "]"
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = safehash(super())
  result=((prime * result) + (0 if ((self.__better is None)) else safehash(self.__better)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if not(super().__eq__(obj)):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[DefaultPartialOrdering] = cast(DefaultPartialOrdering,obj)
  if (self.__better is None):
   if (other.__better is not None):
    return False
  else:
   if not(self.__better == other.__better):
    return False
  return True
'''
Serializes a Bid to string. Unfortunately by default jackson uses
key.toString() for serializing (rather than
{@link ObjectMapper#writeValueAsString(Object)}).


'''

