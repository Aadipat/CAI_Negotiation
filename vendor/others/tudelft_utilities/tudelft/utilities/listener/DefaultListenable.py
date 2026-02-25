from abc import ABC
import threading
import traceback
from typing import TypeVar, Generic, List

from tudelft.utilities.listener.Listenable import Listenable
from tudelft.utilities.listener.Listener import Listener


TYPE= TypeVar('TYPE')


class DefaultListenable (Listenable[TYPE], Generic[TYPE]) :
	'''
	a default implementation for Listenable. Thread safe. Intercepts any
	exceptions from children and prints them as stacktrace.
	@param <TYPE> the type of the data being passed around.
	'''
	
	def __init__(self):
		self.__listeners:List[Listener[TYPE]]  = []
		self.__lock = threading.RLock()


	#Override
	def addListener(self, l:Listener[TYPE]):
		with self.__lock:
			self.__listeners.append(l);
		
	#Override
	def removeListener(self,l:Listener[TYPE]):
		with self.__lock:
			self.__listeners.remove(l);
		
	def notifyListeners(self,data:TYPE ):
		'''
		This should only be called by the owner of the listenable, not by
		listeners or others. Avoid calling this from synchronized blocks as a
		notified listener might immediately make more calls to you.
		<p>
		Any listeners that throw an exception will be intercepted and their
		stacktrace is printed.
		
		@param data information about the change.
		'''
		with self.__lock:
			listens = list(self.__listeners)
			
		l:Listener[TYPE] 
		for l in listens:
			try:
				l.notifyChange(data);
			except BaseException as e:
				traceback.print_exc()
	