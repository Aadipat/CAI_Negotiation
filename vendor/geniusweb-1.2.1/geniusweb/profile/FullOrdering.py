# Generated from java by J2P
from __future__ import annotations
from abc import ABC
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.PartialOrdering import PartialOrdering


class FullOrdering(PartialOrdering,ABC):
 '''
 As {@link PartialOrdering}, but with more strict requirement on
 {@link #isPreferredOrEqual(geniusweb.issuevalue.Bid, geniusweb.issuevalue.Bid)}

 '''
 
 #Override
 def isPreferredOrEqual(self,bid1:Bid,bid2:Bid) -> bool:
  '''
  @param bid1 the first item's utility/preference
  @param bid2 the second item's utility/preference
  @return true iff bid1 is considered better or equal (&ge;) than bid 2. In
          all other cases false is returned.
  
          This predicate should be implemented such that
          <ul>
          <li>For all b1 and b2, either b1 &ge; b2 or b2 &ge; b1.
          <li>b &ge; b (every bid is better or equal to itself)
          <li>If b1&ge;b2 and b2&ge;b1 then the two bids are considered
          equally good. Note that this differes from a partial order in
          mathematics.
          <li>it behaves transitive: if b1&ge;b2 and b2&ge;b3 then
          b1&ge;b3.
          </ul>

  '''
  pass
 
 def __init__(self):
  super().__init__()
