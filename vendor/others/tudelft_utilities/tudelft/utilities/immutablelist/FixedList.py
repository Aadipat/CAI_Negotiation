from typing import TypeVar, Collection
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList


E = TypeVar('E')

class FixedList (ImmutableList[E]):
    '''
    a list with a fixed (finite, typically small) number of elements.
    
    @param <T> type of the elements
    '''

    def __init__(self, lst:Collection[E]): 
        '''
        Copies elements of given list into an immutable list. SO the resulting list
        is really immutable, although the components may still be mutable.
        
        @param lst the source list.
        '''
        self._list = list(lst)

    def FixedList(self) :
        self._list = []


    def __iter__(self): 
        return iter(self._list)

    def get(self, index:int) -> E:
        return self._list[index]

    def size(self) ->int:
        return len(self._list)

    def __repr__(self):
        return repr(self._list)

    def __hash__(self):
        return hash(tuple(self._list))

    def __eq__(self, other):
        return isinstance(other, self.__class__) \
            and self._list==other._list
        
    def contains(self, value) -> bool: 
        '''
        @param value value to look for
        @return Returns true iff this list contains the specified value. More
                formally, returns true if and only if this list contains at least one
                element e such that (o==null ? e==null : o.equals(e)).
        '''
        return value in self._list

