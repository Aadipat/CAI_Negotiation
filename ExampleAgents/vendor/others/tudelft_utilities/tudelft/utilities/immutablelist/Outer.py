from typing import TypeVar, List

from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.FixedList import FixedList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList


T = TypeVar('T')

class Outer (AbstractImmutableList[ImmutableList[T]]) :
    '''
    outer product of lists: a list containing all possible combinations of one
    element from each of the provided lists.
    
    @param T the element type of all lists that we receive.
    '''

    def __init__(self, lists: List[ImmutableList[T]] ):
        '''
        outer product of lists: a list containing all possible combinations of
        one element from each of the provided lists
        
        @param lists
        '''
        self._sourceLists = list(lists)

        if len(lists) == 0:
            s = 0
        else:
            s = 1
            for l in lists:
                s = s * l.size()
        self._size = s;

    def get(self, index:int) ->ImmutableList[T]: 
        element:List[T]  = [];
        i = index;
        for item in range(len(self._sourceLists)):
            l:ImmutableList[T] = self._sourceLists[item]
            n = l.size()
            element.append(l.get(i % n))
            i = i // n
        return FixedList(element);


    def size(self) -> int:
        return self._size

    def __hash__(self):
        return hash(tuple(self._sourceLists))
    
    def __eq__(self, other):
        return isinstance(other, self.__class__) \
            and self._sourceLists==other._sourceLists

