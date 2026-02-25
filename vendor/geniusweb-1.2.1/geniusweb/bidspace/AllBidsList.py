from typing import Dict, List

from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from tudelft.utilities.immutablelist.Outer import Outer

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value


class AllBidsList (AbstractImmutableList[Bid]):
    '''
    A list containing all complete bids in the space. This is an
    {@link ImmutableList} so it can contain all bids without pre-computing them.
    '''

    def __init__(self, domain:Domain):
        '''
        This object contains s list containing all bids in the space. This is an
        ImmutableList so it can contain all bids without pre-computing them.
        
        @param domain the {@link Domain}
        '''
        if domain == None:
            raise ValueError("domain=null");
        self._issues = list(domain.getIssues())

        values:List[ImmutableList[Value]] = [domain.getValues(issue) for issue in self._issues]
        self._allValuePermutations = Outer[Value](values)
 
    def  get(self, index:int) -> Bid:
        nextValues = self._allValuePermutations.get(index);

        issueValues:Dict[str, Value]  = {}
        for n in range(len(self._issues)):
            issueValues[self._issues[n]] = nextValues.get(n)

        return Bid(issueValues);

    def size(self) ->int:
        return self._allValuePermutations.size();

