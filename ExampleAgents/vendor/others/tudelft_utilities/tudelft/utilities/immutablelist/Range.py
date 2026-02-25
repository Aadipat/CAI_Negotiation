from decimal import Decimal, ROUND_FLOOR
from typing import List

from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList


class Range(AbstractImmutableList[Decimal]):
    '''
    Range is an immutable list of numbers from low to high with given step size.
    This class is compatible with pyson.
    '''
    def __init__(self, low:Decimal, high: Decimal, step:Decimal):
        '''
        @param low the first element in the range
        @param high the maximum value of the range. The last item
        in the range may be below or equal to this.
        @param step this value is added to low repeatedly to give all elements
        '''
        assert isinstance(low, Decimal) and isinstance(high, Decimal) \
            and isinstance(step, Decimal)
        self._low=low
        self._high=high
        self._step=step
        
    def getLow(self)->Decimal:
        return self._low
    
    def getHigh(self)->Decimal:
        return self._high
    
    def getStep(self)->Decimal:
        return self._step
    
    def get(self, index:int)-> Decimal:
        return self._low+ self._step  * index
    
    def size(self) -> int:
        if self._low > self._high:
            return 0
        return  1 + \
            int( (( self._high - self._low )/self._step) .quantize(Decimal('1'), rounding=ROUND_FLOOR) )
    
    def __eq__(self, other)->bool:
        return isinstance(other, self.__class__) and \
             self._low == other._low and \
             self._high == other._high and\
             self._step == other._step

    def __repr__(self):
        return "Range["+str(self._low)+","+str(self._high)+","+str(self._step)+"]"
    
    def __hash__(self):
        return hash((self._low, self._high, self._step))
    