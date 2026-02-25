from inspect import signature
import sys
from types import MethodType
from typing import Optional


def JsonValue(value:bool=True):
    '''
    annotation that indicates that the value of annotated accessor 
    (either field or "getter" method [a method with non-void return type, 
    no args]) is to be used as the single value to serialize for the 
    instance, instead of the usual method of collecting properties 
    of value. Usually value will be of a simple scalar type (String or Number), 
    but it can be any serializable type (Collection, Map or Bean).

    At most one accessor of a Class can be annotated with this annotation; 
    if more than one is found, an exception may be thrown. 
    Also, if method signature of annotated method is not compatible with 
    Getters, an exception may be thrown (whether exception is thrown or 
    not is an implementation detail (due to filtering during introspection, 
    some annotations may be skipped) and applications should not rely on 
    specific behavior).

    A typical usage is that of annotating toString() method so that returned 
    String value is used as the JSON serialization; and if deserialization is 
    needed, there is matching constructor or factory method annotated with 
    JsonCreator annotation. 
    
    Boolean argument is only used so that sub-classes can "disable" annotation if necessary. 
     '''
    def doAnnotate(annotatedfunction):
        '''
        This function is applied to the annotated class.
        It just adds an attribute __jsonsubtypes__ to the class
        with the annotation data
        @param annotatedfunction the function that gets this annotation
        '''
        if not isinstance(value, bool):
            raise ValueError("JsonValue requires boolean argument but got  "+str(value))
        args = list(signature(annotatedfunction).parameters)
        args.remove('self')
        if len(args)!=0:
            raise ValueError("@JsonValue annotated function "+str(annotatedfunction)+" can not have arguments but found "+str(args))

        setattr(annotatedfunction, '__jsonvalue__', value)
        return annotatedfunction
    
    # we return doAnnotate as result of the function.
    # that way we can apply that function to the next argument
    # which is the annotatedclass
    return doAnnotate


def getJsonValue(ob:object)->Optional[str]:
    '''
    @param ob the class or instance containing a possible @jsonValue..
    @returns the name of the function in this class that has 
    a @JsonValue annotation, or None.
    '''
    for fname in dir(ob):
        func = getattr(ob, fname)
        if hasattr(func, '__jsonvalue__') and getattr(func, '__jsonvalue__'):
            return func
    return None
