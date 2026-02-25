from pyson.JsonSubTypes import JsonSubTypes
from geniusweb.protocol.NegoProtocol import NegoProtocol

@JsonSubTypes([ "SAOP" ])
class SessionProtocol (NegoProtocol):
    '''
    Interface for all session protocols.
    '''

