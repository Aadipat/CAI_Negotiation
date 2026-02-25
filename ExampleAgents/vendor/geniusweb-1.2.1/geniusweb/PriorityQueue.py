from heapq import heappush, heappop
from queue import Queue
from typing import TypeVar, Generic, Callable, List, Set


T=TypeVar("T")
class Wrap(Generic[T]):
    '''
    Wrapper that has __lt__. 
    We wrap objects that possibly don't implement __lt__ 
    in the queue in this to avoid 
    heapq crashing on a call to __lt__
    '''
    def __init__(self, obj:T, lessthanfunction):
        '''
        @param obj the object to be wrapped.
        @param lessthanfunction a function that 
        when called with another object, 
        returns true iff other object is < this.
        '''
        self._obj=obj
        self._lessthanfunction = lessthanfunction
    def get(self) -> T:
        return self._obj
    def __repr__(self):
        return str(self._obj)
    def __lt__(self, other):
        return self._lessthanfunction(self.get(), other.get())

class PriorityQueue(Queue, Generic[T]):
    '''Variant of Queue that retrieves open entries in priority order (lowest first).
    This differs from queue.PriorityQueue as it allows custom comparator function.
    Another difference is that entries are 
    '''

    def __init__(self, lessthanfunction:Callable[[T,T], bool]):
        '''
        @param lessthanfunction a function with arguments (this, other)
            that is used to sort the queue.
            If queue should have the "smallest" item at head, 
            this function should return true iff other object is < this.
        '''
        super().__init__()
        self._queue:List[Wrap[T]] = []
        self._lessthanfunction=lessthanfunction
        
    def _qsize(self)->int:
        return len(self._queue)

    def _put(self, item:T):
        heappush(self._queue, Wrap(item, self._lessthanfunction))

    def _get(self)->T:
        return heappop(self._queue).get()

    def __repr__(self)->str:
        return str(self._queue)
    
    def __iter__(self):
        return iter([w.get() for w in  self._queue])
    
    