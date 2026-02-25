import sys


def JsonGetter(value:str):
    '''
    Marker annotation that can be used to define a non-static,
    no-argument value-returning (non-void) method to be used as a "getter"
    for a logical property.
    p>
    Getter means that when serializing Object instance of class that has
    this method (possibly inherited from a super class), a call is made
    through the method, and return value will be serialized as value of
    the property.    
    @param value the name to be used for the property in json.
    '''
    if not isinstance(value, str):
        raise ValueError("JsonGetter requires name of the property (str) but got "+str(value))
    
    def doAnnotate(annotatedfunction):
        '''
        This function is applied to the annotated class.
        It just adds an attribute __jsonsubtypes__ to the class
        with the annotation data
        @param annotatedfunction the function that gets this annotation
        '''
        setattr(annotatedfunction, '__jsongetter__', value)
        return annotatedfunction
    
    # we return doAnnotate as result of the function.
    # that way we can apply that function to the next argument
    # which is the annotatedclass
    return doAnnotate


def getGetter(ob:object, gettername: str):
    '''
    @param ob the class or instance containing getter functions.
    getter functions are functions (1) starting with "get"
    (2) that have JsonGetter annotation and is not private
    @returns the name of the function in this class that has the given gettername
    (case insensitive.
    So this may be the gettername itself, prefixed by "get", 
    or a function in ob that has @JsonGetter annotation matching the gettername.
    '''
    for fname in dir(ob):
        func = getattr(ob, fname)
        if hasattr(func, '__jsongetter__'):
            if gettername == getattr(func, '__jsongetter__'):
                return func
        else:
            # actual name is case insentive version
            if fname.lower() == "get"+gettername.lower():
                return func
    raise ValueError("The object "+str(ob) +" has no getter for "+gettername)

