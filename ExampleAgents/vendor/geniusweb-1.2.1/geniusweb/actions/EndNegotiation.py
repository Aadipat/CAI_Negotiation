from geniusweb.actions.AbstractAction import AbstractAction
from geniusweb.actions.PartyId import PartyId


#@JsonTypeName("endnegotiation")
class EndNegotiation ( AbstractAction ):
    '''
    Indicates that a party turns away from the negotiation and.
    '''
    def __init__(self,  actor:PartyId) :
        super().__init__(actor);
    

    def __repr__(self)->str:
        return "EndNegotiation[" + repr(self.getActor()) + "]";
    