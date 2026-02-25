from abc import ABC, abstractmethod

class Deserializer(ABC):
    @abstractmethod
    def deserialize(self, data:object, clas: object)-> object:
        '''
        @param data either a dict or a built-in object like an int
        @param clas the expected class contained in the data.
        If a dict, this class must have a __init__ function specifying the params
        needed and the data in this case should be a dict.
        Any is considered indicating that the expected argument is primitive.
        @return a clas instance matching the data
        '''