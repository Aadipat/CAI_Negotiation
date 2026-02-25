import sys


def JsonSubTypes(subclassnames:list):
    '''
    A bit complex mechanism that just sets
    attribute __jsonsubtypes__ of the annotated class to the tuple
    (annotatedclass, subclassnames).
    We store annotatedclass itself also here because derived
    classes inherit this annotation, while they are NOT having
    these derived classes. We can check the annotated class to 
    check if this attribute holds.
    
    NOTE this annotation must be used only if the referred
    classes actually extend the annotated class.
    Failure to do this will lead to runtime errors.
    We follow the behaviour of jackson here:
    such classes may still serialize but will fail to deserialize.
    
    NOTE2 in jackson the parent-child relations are stored
    in a separate object. Here we store these in the 
    class object itself. The major advantage is that 
    we can leave inheritance to python inheritance mechanisms.
    Disadvantage is that this modifies the class,
    and that this can not handle multiple inheritance situations.
    Now I have no idea how these should be handled anyway,
    neither do I think jackson would support that as multiple
    inheritance is not part of java,
    so probably not much is currently lost here. 
    
    @param subclassnames a list of full class names of subclasses.
    '''
    if not isinstance(subclassnames, list):
        raise ValueError("JSonSubTypes requires list of classes")
    # we can't check class existence here, as subclasses 
    # will not yet exist as they extend superclass.
    
    
    def doAnnotate(annotatedclass):
        '''
        This function is applied to the annotated class.
        It just adds an attribute __jsonsubtypes__ to the class
        with the annotation data
        '''
        setattr(annotatedclass,'__jsonsubtypes__', (annotatedclass, subclassnames))
        return annotatedclass
    
    # we return doAnnotate as result of the function.
    # that way we can apply that function to the next argument
    # which is the annotatedclass
    return doAnnotate


def getSubTypes(clas) -> tuple:
    '''
    @return (annotatedclass, [subclassId])
    tuple with the full annotated class object, and the list of ClassIds
    of the registered subclasses of the annotated class.
    returns None if the class has no subtypes registered.
    Note that this annotation is inherited - all derived classes
    inherit the same annotation.
    '''
    return getattr(clas, '__jsonsubtypes__',None)
