from abc import ABCMeta
from datetime import datetime
from decimal import Decimal
import json
import time
from typing import cast , Dict, Any, List, Optional
from uuid import UUID


from pyson.JsonDeserialize import getDeserializer
from pyson.JsonGetter import getGetter
from pyson.JsonTools import isPrimitive, getActualClass, getInitArgs, getDefaults, addTypeInfo, getListClass
from pyson.JsonTypeInfo import Id, As, getTypeWrappingInfo
from pyson.JsonValue import getJsonValue
from uri.uri import URI


# from pyson.JsonSubTypes import getSubTypes
class ObjectMapper:  
    '''
    A very simple pyson-style objectmapper.
    '''
    def parse(self, data:object, clas:object )->object:
        '''
        @param data either a dict or a built-in object like an int
        @param clas the expected class contained in the data.
        If a dict, this class must have a __init__ function specifying the params
        needed and the data in this case should be a dict.
        Any is considered indicating that the expected argument is primitive.
        @return a clas instance matching the data
        '''
        # now distinguish 
        if isPrimitive(clas,True) or clas==Any:
            return self.parseBase(data, clas)
        if (clas==list):
            #FIXME this is unreachable?
            raise ValueError("Illegal type, use List[X] instead of list")
        if (clas==dict):
            #FIXME this is unreachable?
            raise ValueError("Illegal type, use Dict[X] instead of dict")
        
        deserializer=getDeserializer(clas)
        if deserializer:
            return deserializer().deserialize(data, clas) 
            
        if getJsonValue(clas):
            argclasses:dict=getInitArgs(clas)
            if len(argclasses)!=1:
                raise ValueError("Class "+str(clas)+" has @JsonValue getter but has multiple init arguments")
            valueclas = list(argclasses.values())[0]
            return clas(self.parse(data, valueclas))

        if getTypeWrappingInfo(clas):
            if not isinstance(data, dict):
                raise ValueError("Expected class, therefore data must be a dict but got "+str(data))
            (data, clas) = getActualClass(cast(dict, data),clas)

        if repr(clas).startswith('typing.'):
            return self.parseGeneric(data,clas)
        # after this, clas is NOT a generic like List[X] 
        if issubclass(clas, BaseException): #type:ignore
            return self.parseException(data,clas)
        
        if type(data)==dict: # if it contains class, data must be dict
            return self.parseClass(cast(dict,data), clas)
        raise ValueError("Expected "+str(clas)+" but got '"+str(data)+"' which is a "+str(type(data)))
        
    def parseBase(self,obj, clas)->object:
        '''
        @param obj a built-in object like an int
        @param clas the class of the expected object.
        If Any, then the obj is accepted as primitive (eg, int, dict, str)
        Else, if clas does not contain __init__, it must be a primitive
        @return the obj, after checking it's indeed a clas
        '''
        #datetime is special, the json primitive will be a int with millis since 1970
        if clas== datetime:
            if not type(obj)==int:
                raise ValueError("expected int (millis since 1970) but got "+str(obj))
            return datetime.fromtimestamp(cast(int, obj)/1000.0)
        if clas==URI:
            if not type(obj)==str:
                raise ValueError("expected uri string but got "+str(obj))
            return URI(obj)
        if clas==Decimal:
            # obj must be a float or int. We use str
            # to get the number truncated at correct #digits.
            # It is possible json already rounded the number
            return Decimal(str(obj))
        if clas==UUID:
            if not type(obj)==str:
                raise ValueError("expected UUID string but got "+str(obj))
            return UUID(obj)
        if  not (clas==Any or type(obj)==clas):
            raise ValueError("Expected "+str(clas)+" but got "+str(obj)+" which is a "+str(type(obj)))
        return obj
             
 
    def parseClass(self, data:dict, clas)->object:
        '''
        @param data a dict with the values for class.__init__ function
        @return a clas instance matching the data
        '''
        if not isinstance(data,dict ):
            raise ValueError("data "+str(data)+" must be dict")
        # then this class needs initialization
        initargs={}
        argclasses=getInitArgs(clas)
        defaults = getDefaults(clas)
        if not set(data.keys()).issubset(set(argclasses.keys())):
            raise ValueError("Constructor of "+str(clas)+" requires arguments "+str(list(argclasses.keys()))+" but got "+str(list(data.keys())))
        for arg in argclasses:
            if arg in data:
                try:
                    initargs[arg] = self.parse(data[arg], argclasses[arg])
                except ValueError as e:
                    raise ValueError("Error parsing "+str(data),e ) from e
            else: # does constructor have a devault for the missing avlue?
                if not arg in defaults:
                    raise ValueError(str(clas)+" constructor takes "+str(arg)+" which has no default value, but value missing in dict "+str(data))
        return clas(**initargs)
    
    def parseGeneric(self, data, clas:object)->object:
        '''
        A generic is soemthing like typing Dict[str,str]. 
        @param data may be list or dict,  depending on the exact clas
        @return instance of the clas. Don't know how to write this for typing
        '''
        gname =repr(clas) # _name fails for eg typing.Union
        
        if gname.startswith('typing.List') or gname.startswith('typing.Set'):
            elementclas = clas.__args__[0]
            if type(data)!=list:
                raise ValueError("expected list[{elementclas}] but got "+str(data))
            res=[self.parse(listitem, elementclas) for listitem in data]
            if gname.startswith('typing.List'):
                return res
            else:
                return set(res)
        
        if gname.startswith('typing.Dict'):
            keyclas = clas.__args__[0]
            if not keyclas.__hash__:
                raise ValueError("Dict cannot be serialized, key class "+str(keyclas)+" does not  have __hash__")
            elementclas = clas.__args__[1]
            if type(data)!=dict:
                raise ValueError("expected dict[{keyclass, elementclas}] but got "+str(data))
            return { self.parse(key, keyclas) : self.parse(val, elementclas)\
                     for key,val in data.items() }
            
        if gname.startswith('typing.Union'):
            # Special to support optional: Union[class, NoneType]
            actualclasses = [actual for actual in clas.__args__ if actual!=type(None)]
            if len(actualclasses)!=1:
                raise ValueError("Union type only supported with NoneType, but found: "+str(clas))
            if data==None:
                return None
            return self.parse(data, actualclasses[0])
        
        if gname.startswith('typing.Optional'):
            if data==None:
                return None
            return self.parse(data, clas.__args__[0])


        raise ValueError("Unsupported generic type "+ str(clas))
    
    def parseException(self, data, excclass=Exception):
        '''
        Assumes argument for excclass constructor is the message.
        '''
        if not isinstance(data, dict):
            raise ValueError("Expected dict  but got "+repr(data))
        if not "message" in data:
            raise ValueError("Expected 'message' in "+str(data))
        res=excclass(data['message'])
        if 'cause' in data:
            res.__cause__=self.parse(data['cause'], Optional[Exception])
        return res
    
    def toJson(self, data)->dict:
        '''
        @param data either a dict or a built-in object like an int
        @return a dict containing this object 
        '''
        if isinstance(data, BaseException):
            return self.toJsonException(data)
        res:dict
        clas = type(data)
        # dict and list are handled separately because
        # we must serizliae keys and values separately
        if isPrimitive(clas):
            return self.toJsonBase(data) 
        if clas==list or clas==tuple or clas==set:
            res=self.toJsonList(data)
        elif clas==dict:
            res=self.toJsonDict(data)
        elif type(clas)==type or type(clas)==ABCMeta:
            # is it general class? FIXME can this be done better?
            res = self.toJsonClass(data)
        else:
            raise ValueError("Unsupported object of type "+str(clas))
        # check if wrapper setting is requested for this class
        if getTypeWrappingInfo(clas):
            res=addTypeInfo(clas,res);
        return res
        
    def toJsonClass(self,data:object)->dict:
        ''' 
        @param data a class instance
        @return data a dict with the values 
        The values are based on the  class.__init__ function
        '''
        jsonvalue = getJsonValue(data)
        if jsonvalue:
            return self.toJson(jsonvalue())
        
        clas=type(data)
        res={}
        arg:str
        for arg in getInitArgs(clas):
            argvalue = getGetter(data, arg)()
#             gettername = 'get'+arg
#             if not hasattr(data, gettername) :# in clas.__dict__:
#                 raise ValueError("The object "+str(data)+ "of type "+ str(clas)+" has no function "+gettername)
#             argvalue = getattr(data, gettername)() #.__dict__[gettername]()
            res[arg]=self.toJson(argvalue)
        return res
        
    
    def toJsonBase(self,obj):
        '''
        @param obj a built-in object like an int or a datetime.
        obj does not contain __init__, it must be a built-in type
        @return the json style representation of teh built-in object.
        For datetime objects we use the linux timestamp (millis since 1970)
        '''
        if isinstance(obj, datetime):
            return round(datetime.timestamp(obj)*1000)
        if isinstance(obj, URI) or isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            if obj == obj.to_integral_value():
                return int(obj) # python has no maxint 
            return float(obj)
        return obj
    
    def toJsonList(self, listofobj):
        '''
        @param listofobj list or tuple of objects each to be serialized separately.
        @return list object to be put in the json representation,  
        '''
        if len(listofobj)==0:
            return [] # empty list has no type. 
        clas = getListClass(listofobj)
        #         if isPrimitive(clas):
        #             return listofobj
        # CHECK can we check if classes involved are properly annotated?
        #if not(clas==None or getTypeWrappingInfo(clas)):
        #    raise ValueError("@JsonTypeInfo is required for list objects, but found "+str(clas))
        return [self.toJson(elt) for elt in listofobj]
    
    def toJsonDict(self, dictofobj:Dict[Any,Any]):
        '''
        @param dictofobj dict with objects each to be serialized separately.
        The keys must be primitive, values must be all the same class.
        @return list object to be put in the json representation,  
        '''
        if len(dictofobj)==0:
            return {} # empty list has no type. 
        keyclas = getListClass(list(dictofobj.keys()))
        valclas = getListClass(list(dictofobj.values()))
        #         if isPrimitive(clas):
        #             return listofobj
        if keyclas!=None and not getJsonValue(keyclas):
            raise ValueError("key of dict must be primitive, but found "+\
                             str(keyclas)+" in "+str(dictofobj))
        #if valclas and not getTypeWrappingInfo(valclas):
        #    raise ValueError("@JsonTypeInfo is required for dict objects, but found "+str(valclas))
        return { self.toJson(key):self.toJson(val) for key,val in dictofobj.items()}

    def toJsonException(self, e:BaseException):
        res:Dict[str ,Any] ={}
        if len(e.args)==1:
            res["message"]=str(e.args[0])
        else:
            res["message"]=str(e.args)
        res["stackTrace"]=[]
        res["cause"]=self.toJsonException(e.__cause__) if e.__cause__ else None
        return res
    