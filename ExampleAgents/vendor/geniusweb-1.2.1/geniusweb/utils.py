'''
A few simple but often needed tools.
'''
from _collections_abc import dict_items #type:ignore
from typing import TypeVar, Optional


def toStr(d)->str:
    '''
    prettyprint a "primitive" like dict or list, 
    similar to how java prints it.
    In java, strings are NOT quoted.
    '''
    if isinstance(d, dict):
        return "{"+ (", ".join([toStr(k)+"="+toStr(v) for (k,v) in d.items()]))+"}"
    if isinstance(d, list):
        return "["+(", ".join([toStr(v) for v in d])) + "]"
    if isinstance(d, tuple):
        return "("+(", ".join([toStr(v) for v in d]))+")"
    if isinstance(d, set):
        return "{"+(", ".join([toStr(v) for v in d]))+"}"
    return str(d)

def toTuple(d:dict) -> tuple:
    '''
    Converts dict into tuples of tuples. Used mainly to compute hash
    '''
    return tuple([(k,v) for (k,v) in d.items()])

T = TypeVar('T')
def val(v:Optional[T])->T:
    '''
    @return the value contained in the optional.
    Raises exception if the value is None. 
    '''
    if not v:
        raise ValueError("Value is not set")
    return v 

def HASH(obj) -> int:
    '''
    hashes built-in objects, even dict and list of built-in objects.
    '''
    if isinstance(obj, list) or isinstance(obj, set) or\
        isinstance(obj, tuple) or isinstance(obj, dict_items):
        return 31+sum([HASH(e) for e in obj])
    if isinstance(obj, dict):
        return HASH(obj.items())
    return hash(obj)