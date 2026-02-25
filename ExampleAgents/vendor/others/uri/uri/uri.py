from __future__ import annotations
from rfc3986.api import uri_reference

class URI:
    '''
    Immutable object containing an Uniform Resource Identifier (URI).
    An URI is a string of characters identifying a resource on the web.
    It generally looks like scheme://user@host:port/bla/bla?query#fragment.
    Many of these parts are optional, check the specs of rfc3986
    '''
    def __init__(self, uri:str):
        '''
        Constructor checks that the provided URI meets the specs.
        '''
        self._uri=uri
        self._parse= uri_reference(uri)
        # 41 do not check URI presence, similar to java
        # assert self._parse.scheme , "missing scheme"
        self._normal=self._parse.normalize()

    def getUri(self):
        '''
        @return the original URI provided in the constructor
        '''
        return self._uri
    
    def getScheme(self):
        '''
        The scheme of the URI.  Scheme specifies the format of the data
        and the communication protocols needed. Eg "https" or "ws"
        '''
        return self._parse.scheme

    
    def getHost(self):
        '''
        @return the Name or IP address of the machine containing the resource
        '''
        return self._parse.host
    
    def getPath(self):
        '''
        @return the Path part of the URI.  The pat to the data on the machine. 
        '''
        return self._parse.path

    def getQuery(self):
        '''
        @return the query part of the URI
        '''
        return self._parse.query

    def getFragment(self):
        '''
        @return the fragment contained in the URI.
        '''
        return self._parse.fragment

    def __repr__(self)->str:
        return self._uri
    
    def __eq__(self, other):
        return isinstance(other, self.__class__) and \
            self._normal==other._normal
            
    def __hash__(self):
        return hash(self._normal)
    
