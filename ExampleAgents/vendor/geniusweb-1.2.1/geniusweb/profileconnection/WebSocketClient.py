from abc import ABC, abstractmethod

from geniusweb.profileconnection.Session import Session


class WebSocketClient(ABC):
    '''
    Interface for client listening to websocket events.
    This basically hides the python websocket app,
    so that we can ensure the functions are implemented
    and allows us to pass mock clients.
    '''
    @abstractmethod
    def onOpen(self, session:Session):
        '''
        called when the socket opens. Clients should store the session
        '''
    @abstractmethod
    def onClose(self):
        '''
        called when session closes.
        '''
        
    @abstractmethod
    def onMessage(self, text:str):
        '''
        called when message comes for the client
        '''
    @abstractmethod
    def onError(self, error:BaseException):
        '''
        @param error the error that occured
        '''
        
    @abstractmethod
    def close(self):
        '''
        When this is called, the client should close and free its resources.
        '''