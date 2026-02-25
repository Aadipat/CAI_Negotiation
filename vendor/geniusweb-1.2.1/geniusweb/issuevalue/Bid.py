from typing import Any, Dict, Union, Set, Optional
from geniusweb.issuevalue.Value import Value
from geniusweb.utils import toStr

NoneType=type(None)

class Bid:
    def __init__(self, issuevalues:Dict[str, Value]):
        '''
        @param  a map of issue, Value pairs. The String is the issue name.
        '''
        if not isinstance(issuevalues,dict):
            raise ValueError("issuevalues must be dict, got "+str(issuevalues))
        for (iss,val) in issuevalues.items():
            if not isinstance(iss, str):
                raise ValueError("Issue "+str(iss)+" must be a str")
            if not isinstance(val, Value):
                raise ValueError("value "+str(val)+" must be a Value, but is "+str(type(val)))
        self._issuevalues = dict(issuevalues) #shallow copy : Value is immutable

    def getIssueValues(self) -> Dict[str, Value]:
        '''
        @param issue name of the issue
        @return the value for the given issue, or null if there is no value for
                the given issue.
        '''
        return self._issuevalues
    
    def getIssues(self)->Set[str]:
        return set(self._issuevalues.keys())
    
    
    def getValue(self, issue:str) -> Optional[Value] :
        '''
        @param issue name of the issue
        @return the value for the given issue, or None if there is no value for
                the given issue.
        '''
        if not issue in self._issuevalues:
            return None
        return self._issuevalues[issue];
    
    def merge(self,  otherbid:"Bid")->"Bid" :
        '''
        this this partial bid with another partial bid.
        
        @param otherbid another partial bid.
        @return a bid with the combined values of both partial bids.
        @throws IllegalArgumentException if issues overlap.
        '''
        ourissues = set(self._issuevalues.keys())
        ourissues = ourissues.intersection(otherbid.getIssues())
        if len(ourissues)!=0:
            raise ValueError(\
                "Otherbid contains issues that are already set:"\
                            + str(ourissues))
            
        newvalues = dict(self._issuevalues)
        newvalues.update(otherbid._issuevalues)
        return Bid(newvalues)
    
    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            self._issuevalues == other._issuevalues

    def __repr__(self) -> str:
        return "Bid" + toStr(self._issuevalues);
    
    def __hash__(self):
        return hash((tuple(self._issuevalues.items())))
 