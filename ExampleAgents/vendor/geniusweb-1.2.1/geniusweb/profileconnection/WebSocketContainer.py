from abc import ABC, abstractmethod
import threading

from uri.uri import URI  # type:ignore
from websocket._app import WebSocketApp  # type:ignore

from geniusweb.profileconnection.Session import Session
from geniusweb.profileconnection.WebSocketClient import WebSocketClient


class WebSocketContainer(ABC):
    '''
    mockable interface to websocket system. 
    This allows us to test the WebSocketProfileConnector
    without having a profilesserver running.
    This uses websocket_client module (to be pip-installed)
    '''
    @abstractmethod
    def setDefaultMaxTextMessageBufferSize(self, bufsize:int):
        '''
        @param bufsize the new buffer size for websocket
        '''
        
    @abstractmethod
    def connectToServer(self, uri:URI, client:WebSocketClient) -> Session: 
        '''
        @param uri the websocket uri to contact
        @param client the WebSocketClient to be attached 
        '''


class WsSession(Session):
    '''
    Websocket based implementation.
    '''
    def __init__(self, uri:URI , client:WebSocketClient):
        self._ws = WebSocketApp(str(uri), 
            on_message = lambda ws,text: client.onMessage(text),
            on_error = lambda ws,error: client.onError(error),
            on_close = lambda ws,a,b: client.onClose(),  # is really called with 3 args??
            on_open = lambda ws: client.onOpen(self))
        threading.Thread(target=lambda:self._ws.run_forever()).start()

    
    def send(self, text: str):
        self._ws.send(text)
        
    def close(self):
        self._ws.close()
        
    def __repr__(self):
        return 'Session to '+str(self._ws.url)
        

class DefaultWebSocketContainer(WebSocketContainer):
    '''
    "Real" websocket implementation using WebSocketApp
    '''
    def setDefaultMaxTextMessageBufferSize(self, bufsize:int):
        print("WARNING setDefaultMaxTextMessageBufferSize not implemented")
        
    def connectToServer(self, uri:URI, client:WebSocketClient) -> Session:
        return WsSession(uri, client)
    