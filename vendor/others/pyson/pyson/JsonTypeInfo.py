from enum import Enum
from typing import Tuple, Optional


class Id(Enum):
    '''
    Id is the way a ClassId is created from a class object.
    It is recommended to use the default NAME.
    CLASS may be system dependent and therefore is no good
    choice for generally usable json.
    NONE will not cause deserialization issues.
    '''
    NONE=0 # don't include ClassId at all.
    NAME=1 # ClassId=the last part of the full.class.path
    CLASS=2 # ClassId= full.class.path


class As(Enum):
    '''
    Identifies how ClassId (see Id) is to be wrapped into json.
    '''
    PROPERTY=0 # add 'type':ClassId attribute to the object dict
    WRAPPER_OBJECT=1 # wrap object in dict, with ClassId as key
    WRAPPER_ARRAY=2 # ...
        
        
        
def JsonTypeInfo(use:Id, include:As):
    '''
    rudimentary component,
    following packson structure but limited actual support in ObjecMapper.
    puts a tuple (use, include) in the field __jsontypeinfo__ of the annotated class.
    '''    

    
    def doAnnotate(annotatedclass):
        setattr(annotatedclass,'__jsontypeinfo__', (use, include))
        return annotatedclass

    
    '''
    A bit complex mechanism that just sets
    attribute __jsonsubtypes__ of the annotated class to the tuple
    (id, as).
    . 
    @param subclassnames a list of full class names of subclasses.
    '''
    if not isinstance(use, Id):
        raise ValueError("use must be JsonTypeInfo.Id")
    if not isinstance(include, As):
        raise ValueError("include must be JsonTypeInfo.As")
    return doAnnotate


##### support functions.
# these are static functions because they handle class objects directly


def getClassId(clas) -> str:
    '''
    @param clas the clas to get ID for
    @return the classId for the given class and use method.
    The classId is a string tag referring to a class.
    '''
    useinclude=getTypeWrappingInfo(clas)
    if not useinclude:
        raise ValueError("The object "+str(clas)+" does not have TypeWrapping info. Is it a class and is it extending the proper superclass?")
    (use, _include)=useinclude
    if use==Id.NAME:
        return getattr(clas,'__name__')
    if use==Id.CLASS:
        return getattr(clas,'__module__')+"."+getattr(clas,'__name__')
    raise ValueError("Not implemented type info "+str(use))

def getTypeWrappingInfo( clas )-> Optional[Tuple[Id, As]]:
        '''
        @param clas: a dict that should include way class information is wrapped into the dict
        @param defaultval: a Tuple[Id, As] containing defaul tif clas does not contain setting.
        @return (use,include) tuple that indicates how type
        information is to be wrapped into the json object.
        Or defaultval if the class is not annotated.
        '''
        if hasattr(clas, '__jsontypeinfo__'):
            return getattr(clas, '__jsontypeinfo__')
        return None


