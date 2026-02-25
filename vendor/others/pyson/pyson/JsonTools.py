"""
Tools that are working just with a class
"""

from _decimal import Decimal
from datetime import datetime
import importlib
from inspect import Parameter
from inspect import _empty
import inspect
from typing import Dict, _GenericAlias, cast, Tuple, get_type_hints
from uuid import UUID

from uri.uri import URI

from pyson.JsonSubTypes import getSubTypes
from pyson.JsonTypeInfo import Id, As, getTypeWrappingInfo, getClassId

NoneType = type(None)


def isPrimitive(clas, includeListDict: bool = False):
    """
    @return true if clas is primitive: int, float, etc.
    These are also the class types that can be used for dictionary keys.
    list can't be primitive because we must check the type of the list elements and
    use the appropriate parser for them.
    """
    return clas in (
        NoneType,
        int,
        float,
        bool,
        str,
        complex,
        range,
        bytes,
        bytearray,
        datetime,
        URI,
        Decimal,
        UUID,
    ) or (includeListDict and clas in (list, dict))


def getInitArgs(clas) -> Dict[str, object]:
    """
    @param clas a class object that can be instantiated
    @return dict with key: argument of clas __init__ and
    value: the type/class of that argument.
    @throws ValueError if not all args are annotated with a type.
    """
    if not hasattr(clas, "__init__"):
        return {}
    f = getattr(clas, "__init__")
    # Does not work, dee #1, uses __annotations__ which is broken.
    # argclasses = {name:param._annotation for name,param in inspect.signature(f).parameters.items()}
    argclasses = get_type_hints(f)
    if "self" in argclasses:
        argclasses.pop("self")
    # _empty is indicates an undefined type in the typing system.
    untyped = [name for name, param in argclasses.items() if param == _empty]
    # untyped = set(argclasses.keys()) - set(['self'])
    if len(untyped) > 0:
        raise ValueError(
            "init function of Class "
            + str(clas)
            + " must have all arguments typed, but found untyped "
            + str(untyped)
        )
    return argclasses


def getDefaults(clas) -> Dict[str, object]:
    """
    @param clas a class object that can be instantiated
    @return dict with key: argument of clas __init__ and
    value: the default value for that argument.
    """
    if not hasattr(clas, "__init__"):
        return {}
    sig = inspect.signature(getattr(clas, "__init__"))
    return {
        name: param.default
        for name, param in sig.parameters.items()
        if param.default is not inspect.Parameter.empty and name != "self"
    }


def str_to_class(fullclasspath: str) -> object:
    """
    @param fullclasspath : full path specification to a class,
    so that we can locate and load it.
    @return a new class, loaded from the given string.
    """
    x = fullclasspath.rfind(".")
    module_name = ""
    if x > 0:
        module_name = fullclasspath[0:x]
    # load the module, will raise ImportError if module cannot be loaded
    try:
        m = importlib.import_module(module_name)
    except Exception as e:
        raise ValueError("Failed to load class " + fullclasspath, e)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, fullclasspath[x + 1 :])
    return c


def id2class(classid: str, realclasses: list):
    """
    @param classid the class id , coming from the json
    @param use the Id
    @param realclasses the list of real classes that are allowed
    @return the real class  that has the requested id
    """
    for clas in realclasses:
        if classid == getClassId(clas):
            return clas
    raise ValueError(
        "There is no subclass of '" + str(realclasses) + " with the name " + classid
    )


def addTypeInfo(clas, jdict: dict) -> dict:
    """
    @param clas the class of the object to be serialized
    @jdict an already json-ized object dict, but without type wrapper
    @return res, but with type info added
    """
    (use, include) = getTypeWrappingInfo(clas)
    if use == Id.NONE:
        return jdict
    classid = getClassId(clas)

    if include == As.WRAPPER_OBJECT:
        return {classid: jdict}
    else:
        raise ValueError("Not implemented include type " + str(include))


def getActualClass(data: dict, clas) -> tuple:
    """
    @param data the json dict to be deserialized. It should contain the
    class type info.
    @param clas the expected class. This class IS annotated with jsonsubtypes but
    clas may differ from the originally annotated class (it may just have inherited the annotation)
    @return tuple (actualdata,actualclass). with the actualclass contained in the data. It must be one
    of the classes in the __jsonsubtypes__ of class. actualdata is stripped of the type data contained
    in the original data dict. ASSUMES typewrappinginfo is set
    @throws if typewrapping info is not set.
    """
    (use, include) = getTypeWrappingInfo(clas)

    if getSubTypes(clas):
        (_annotatedclass, subclasslist) = getSubTypes(clas)
        # we could not load the real classes earlier
        # because they did not yet exist at parse time.
        realclasses = [str_to_class(classname) for classname in subclasslist]
        realclasses.append(clas)
    else:
        # class has no subtypes annotation, it can be only the indicated class.
        realclasses = [clas]
    """
    Algorithm: this ignores annotatedclass.
    We first try to find which of the subclasslist is actually in the data.
    Then we just check if that is subclass of clas.
    """
    if include == As.WRAPPER_OBJECT:
        if len(data.keys()) != 1:
            raise ValueError(
                "WRAPPER_OBJECT requies 1 key (class id) but found " + str(data.keys())
            )
        classid = next(iter(data.keys()))
        actualdata = data[classid]
    else:
        raise ValueError(
            "Not implemented: deserialization with include " + str(include)
        )

    # find back the matching full classname
    actualclas = id2class(classid, realclasses)

    # We found a class that matches the header.
    # but the clas requested might be more restrictive as we may be in a subclass
    # FIXME can we do this test once, somewhere, for all of the realclasses?
    if not issubclass(actualclas, clas):
        raise ValueError(
            "The class ID ("
            + str(actualclas)
            + " is not implementing the requested class "
            + str(clas)
        )
    return (actualdata, actualclas)


def getListClass(listofobj: set) -> object:
    """
    @param listofobj a list/set/tuple with at least 1 object
    @return class of the list elements. All elements must extend same superclass.
    returns None if elements are primitive.
    @throws ValueError if elements are not primitive, yet do not all extend same superclass
    """
    if len(listofobj) == 0:
        raise ValueError("bug, getListClass called with empty list")
    clas = type(next(iter(listofobj)))  # object may be a list, dict, set

    if isPrimitive(clas):
        return None

    # if clas is subclass, use the superclass
    if getSubTypes(clas):
        (clas, _subclasses) = getSubTypes(clas)

    for obj in listofobj:
        if not issubclass(type(obj), clas):
            raise ValueError(
                "Expected all elements of type " + str(clas) + " but found " + str(obj)
            )
    return clas
