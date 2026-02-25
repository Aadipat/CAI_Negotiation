import json

from pyson.ObjectMapper import ObjectMapper

from geniusweb.party.Party import Party
from geniusweb.partystdio.StdInOutConnectionEnd import StdInOutConnectionEnd


class PartyStdIo:
    '''
    A class that makes a connection between a Party and the system stdio and stderr channels.
    This allows communication with a party through the stdio channels,
    which in fact is a system pipe.
    '''
    def __init__(self, partyclas):
        '''
        partyclas the class of the party.
        Parties should implement a getter for this in the function
        party.party()
        '''
        if not issubclass(partyclas, Party):
            raise ValueError("party must be subclass of Party but got "+str(partyclas))
        self._partyclas= partyclas
        self._jackson = ObjectMapper()

    
    def capabilities(self)->None: 
        '''
        This assumes a party object 
        at the global scope, containing the party() call that returns
        a class extending Party
        '''
        self.out(self._partyclas.getCapabilities(None)) 
        
    def description(self)->None:
        '''
        This assumes a party object 
        at the global scope, containing the party() call that returns
        a class extending Party
        '''
        self.out(self._partyclas.getDescription(None))
        
    def out(self, obj)->None:
        '''
        prints object serialized with ObjectMapper to stdout, without newline
        '''
        print(json.dumps(self._jackson.toJson(obj)),end="")

    def run(self, connend=StdInOutConnectionEnd()):  
        '''
        "runs" the party. Create instance, connect, 
        pipe actions and inform through stdin/stdout, terminate.
        '''
        party=self._partyclas()

        party.connect(connend)
        connend.run(party)
        
        
        