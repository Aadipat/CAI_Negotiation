from builtins import issubclass
import sys
from types import MethodType

from pyson.Deserializer import Deserializer
from pyson.JsonTools import str_to_class


def JsonDeserialize(using:str):
    '''
    Annotation use for configuring deserialization aspects, by attaching
    to "setter" methods or fields, or to value classes.
    When annotating value classes, configuration is used for instances
    of the value class but can be overridden by more specific annotations
    (ones that attach to methods or fields).    @param value the name to be used for the property in json.
    '''
    if not isinstance(using, str):
        raise ValueError("@JsonDeserializer takes class.path of deserializer but got "+str( using))
    
    def doAnnotate(annotatedfunction):
        '''
        This function is applied to the annotated class.
        It just adds an attribute __jsondeserialize__ to the class
        with using as value
        @param annotatedfunction the function that gets this annotation
        '''
        setattr(annotatedfunction, '__jsondeserialize__', using)
        return annotatedfunction
    
    # we return doAnnotate as result of the function.
    # that way we can apply that function to the next argument
    # which is the annotatedclass
    return doAnnotate


def getDeserializer(ob:object)->object : # Class
    '''
    @param ob the class or instance presumably containing deserializer annotation.
    @returns the 'using'  clas  to the deserializing class, 
    or None if ob has no deserialize annotation.
    @raise  ValueError if the 'using' class is not a Deserializer
    '''
    if not hasattr(ob, '__jsondeserialize__'):
        return None
    deserializername=getattr(ob, '__jsondeserialize__')
    clas:object = str_to_class(deserializername)
    if not issubclass(clas, Deserializer):
        raise ValueError("Custom deserializer "+deserializername+" must implement Deserializer")
    return clas