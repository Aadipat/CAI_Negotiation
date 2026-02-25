# Generated from java by J2P
from __future__ import annotations
from collections.abc import Set as AbcSet
from decimal import Decimal
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.DefaultProfile import DefaultProfile
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profile.utilityspace.PartsUtilities import PartsUtilities
from geniusweb.profile.utilityspace.ProductOfValue import ProductOfValue
from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities
from tudelft.utilities.tools.dictkeys import Keys
from tudelft.utilities.tools.safehash import safehash
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import cast


class SumOfGroupsUtilitySpace(DefaultProfile, UtilitySpace):
 '''
 *************************** private funcs **************************
 This is a utility space that defines the utility of bids as a sum of the
 utilities of a number of subsets, or groups, of the issue values.
 <p>
 A group defines the utility of a non-empty subset of the issues in the
 domain. The parts are non-overlapping. Missing issue values have utility 0.
 <p>
 This space enables handling {@link UtilitySpace}s that are not simply linear
 additive, but with interacting issue values. For example, if you would like
 to have a car with good speakers but only if there is also a good hifi set,
 you can make a part that has {@link PartsUtilities} like
 <code> { { speakers:yes, hifi:yes }:1, {speakers, no: hifh:yes}:0.2, ...} </code>
 <p>
 NOTICE this space is completely discrete. There is no equivalent of the
 {@link NumberValueSet} here.

 '''
 
 def __init__(self, domain:Domain, name:str, partUtilities:Dict[str,PartsUtilities], reservationBid:Optional[Bid]):
  '''
  the key is the part name, the value is the valuesetutilities for this
  issue. Should be immutable so do not return direct access to this field.

  '''
  
  self.__partUtilities:Dict[str,PartsUtilities] = dict()
  super().__init__(name,domain,reservationBid)
  self.__partUtilities.update(partUtilities)
  err:Optional[str] = self.__checkParts()
  if err is not None:
   raise ValueError(err)
 
 @staticmethod 
 def create(las:LinearAdditive) -> SumOfGroupsUtilitySpace:
  '''
  Copy settings in las. This will have the exact same utilities as the las
  but this then gives you the power to change it into a non-linear space by
  grouping.
  
  @param las the {@link LinearAdditive} to be converted/copied.
  

  '''
  return SumOfGroupsUtilitySpace(las.getDomain(),las.getName(),SumOfGroupsUtilitySpace.__las2parts(las),las.getReservationBid())
 
 #Override
 def getUtility(self,bid:Bid) -> Decimal:
  summed:Decimal = Decimal(0)
  for partname in Keys(self.__partUtilities) :
   partname:Optional[str] = partname
   summed=summed + self.__util(partname,bid)
  return summed
 
 #Override
 def __repr__(self) -> str:
  return "SumOfGroupsUtilitySpace[" + str(self.getName()) + "," + str(self.__partUtilities) + "," + str(self.getReservationBid()) + "]"
 
 def group(self,partnames:List[str],newpartname:str) -> SumOfGroupsUtilitySpace:
  '''
  
  @param partnames   the partnames to remove from this. There must be at
                     least 2 parts
  @param newpartname the name of the new part that contains all partnames,
                     grouped into 1 "issue". This name must not be an issue
                     in this.
  @return new {@link SumOfGroupsUtilitySpace} that takes all partnames out
          of this, and makes a newaprtname that contains these.

  '''
  allpartnames:Set[str] = Keys(self.__partUtilities)
  if (len(partnames) < 2):
   raise ValueError("Group must contain at least 2 parts")
  if newpartname in allpartnames:
   raise ValueError("newpartname " + newpartname + " is already in use")
  for name in partnames :
   name:str = name
   if not(name in allpartnames):
    raise ValueError("Unknown part name " + name)
  newutils:Dict[str,PartsUtilities] = dict()
  newpartutils:Optional[PartsUtilities] = None
  for name in Keys(self.__partUtilities) :
   name:str = name
   if name in partnames:
    if (newpartutils is None):
     newpartutils=self.__partUtilities.get(name)
    else:
     newpartutils=newpartutils.add(self.__partUtilities.get(name))
   else:
    newutils[name]=self.__partUtilities.get(name)
  if (newpartutils is None):
   raise ValueError("Newpartutils remained null.")
  newutils[newpartname]=newpartutils
  return SumOfGroupsUtilitySpace(self.getDomain(),self.getName(),newutils,self.getReservationBid())
 
 #Override
 def __hash__(self) -> int:
  prime:int = 31
  result:int = safehash(super())
  result=((prime * result) + (0 if ((self.__partUtilities is None)) else safehash(self.__partUtilities)))
  return result
 
 #Override
 def __eq__(self,obj:Optional[Any]) -> bool:
  if (self is obj):
   return True
  if not(super().__eq__(obj)):
   return False
  if (type(self) is not type(obj)):
   return False
  other:Optional[SumOfGroupsUtilitySpace] = cast(SumOfGroupsUtilitySpace,obj)
  if (self.__partUtilities is None):
   if (other.__partUtilities is not None):
    return False
  else:
   if not(self.__partUtilities == other.__partUtilities):
    return False
  return True
 
 def getPartUtilities(self) -> Dict[str,PartsUtilities]:
  '''
  @return the raw map of utilities of all parts

  '''
  return dict(self.__partUtilities)
 
 def __util(self,partname:str,bid:Bid) -> Decimal:
  '''
  
  @param partname the name of the part to get the utility of
  @param bid      a possibly partial bid
  @return weighted util of just the part: utilities[part].getUtility(part
          of bid)

  '''
  partutils:PartsUtilities = self.__partUtilities.get(partname)
  value:ProductOfValue = self.__collectValues(bid,partutils)
  return partutils.getUtility(value)
 
 def __collectValues(self,bid:Bid,partutils:PartsUtilities) -> ProductOfValue:
  '''
  
  @param bid       a posibly partial bid
  @param partutils the part utils for which a list of values from the bid
                   is needed
  @return a list of values from the given bid, ordered as indicated in
          partutils

  '''
  values:List[Value] = list()
  for issue in partutils.getIssues() :
   issue:str = issue
   #  This is a bug. bid.getValue may return null.
   values.append(bid.getValue(issue))
  return ProductOfValue(values)
 
 @staticmethod 
 def __las2parts(las:LinearAdditive) -> Dict[str,PartsUtilities]:
  '''
  
  @param las a {@link LinearAdditive}
  @return a Map with partname-PartsUtilities. The partnames are identical
          to the issues in the given las.

  '''
  map:Dict[str,PartsUtilities] = dict()
  for issue in Keys(las.getIssueUtilities()) :
   issue:str = issue
   valset:ValueSetUtilities = las.getIssueUtilities().get(issue)
   utilslist:Dict[ProductOfValue,Decimal] = dict()
   weight:Decimal = las.getWeight(issue)
   for val in las.getDomain().getValues(issue) :
    val:Value = val
    util:Decimal = (valset.getUtility(val)) * (weight)
    if (int(Decimal(0).compare(util))!=0):
     utilslist[ProductOfValue((lambda _: _ if type(_)==list else [_])(val))]=util
   map[issue]=PartsUtilities((lambda _: _ if type(_)==list else [_])(issue),utilslist)
  return map
 
 def __checkParts(self) -> Optional[str]:
  '''
  
  @return error string, or null if no error (all parts seem fine)

  '''
  if None in Keys(self.__partUtilities):
   return "partUtilities contains null key(name)"
  if None in list(self.__partUtilities.values()):
   return "partUtilities contains null value"
  collectedIssues:Set[str] = set()
  for partname in Keys(self.__partUtilities) :
   partname:str = partname
   part:Optional[PartsUtilities] = self.__partUtilities.get(partname)
   #  convert to Set to help python.
   issues:Set[str] = set(part.getIssues())
   intersection:Set[str] = set(collectedIssues)
   (intersection:=intersection&(lambda _: frozenset(_) if isinstance(_, AbcSet) else _)(issues))==set()
   if not(not intersection):
    return "issues " + str(intersection) + " occur multiple times"
   collectedIssues.update((lambda _: frozenset(_) if isinstance(_, AbcSet) else _)(issues))
  if not(collectedIssues == Keys(self.getDomain().getIssuesValues())):
   return "parts must cover the domain issues " + str(self.getDomain().getIssuesValues()) + " but cover " + str(collectedIssues)
  if (int(self.__getMaxUtility().compare(Decimal(1))) > 0):
   return "Max utility of the space exceedds 1"
  return None
 
 def __getMaxUtility(self) -> Decimal:
  '''
  
  @return the max possible utility in this utility space.

  '''
  return sum( [ partutils.getMaxUtility() for partutils in self.__partUtilities.values() ] )
