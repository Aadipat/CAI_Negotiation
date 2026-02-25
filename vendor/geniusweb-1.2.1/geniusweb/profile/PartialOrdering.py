# Generated from java by J2P
from __future__ import annotations
from abc import ABC
from geniusweb.issuevalue.Bid import Bid
from geniusweb.profile.Profile import Profile


class PartialOrdering(Profile,ABC):
 '''
 Defines a is-better relation between bids. This basically is a partially
 ordered space however some bids or groups of bids may not be relatable to
 others.

 '''
 
 def isPreferredOrEqual(self,bid1:Bid,bid2:Bid) -> bool:
  '''
  @param bid1 the first item's utility/preference
  @param bid2 the second item's utility/preference
  @return true iff bid1 is considered better or equal (&ge;) than bid 2. In
          all other cases false is returned. A bid may not have a &ge;
          relation at all.
  
          This predicate should be implemented such that
          <ul>
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
