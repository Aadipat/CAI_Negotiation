from collections import deque
import threading
from typing import Generic, TypeVar


T=TypeVar('T') # contained element type

class BlockingQueue(Generic[T]):
    '''
    Like threading.Queue but using collections.queue
    which allows us to extend the functioanlity
    '''
    def __init__(self, capacity: int):
        self._pushing = threading.Semaphore(capacity)
        self._pulling = threading.Semaphore(0)
        self._data:deque = deque()
 
    def put(self, element: T):
        self._pushing.acquire()
        self._data.append(element)
        self._pulling.release()
 
    def take(self) -> T:
        self._pulling.acquire()
        self._pushing.release()
        return self._data.popleft()
        
    def size(self) -> int:
        return len(self._data)
    
    def contains(self, elt:T) -> bool:
        return elt in self._data
    