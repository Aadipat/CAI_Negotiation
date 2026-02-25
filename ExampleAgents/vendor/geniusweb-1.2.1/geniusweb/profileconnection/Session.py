from abc import ABC, abstractmethod

class Session(ABC):
    '''
    An active websocket session.
    '''
    @abstractmethod
    def send(self, text: str):
        '''
        @param text the text to be sent into the websocket.
        '''
        
    @abstractmethod
    def close(self):
        '''
        close this session.
        '''
        
        
        
        