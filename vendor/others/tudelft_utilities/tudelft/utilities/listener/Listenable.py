from abc import  abstractmethod
from abc import ABC
from typing import TypeVar, Generic, List

from tudelft.utilities.listener.Listener import Listener


TYPE= TypeVar('TYPE')

class Listenable (ABC, Generic[TYPE]):
	'''
	Simple reusable listenable
	@param <TYPE> the type of the data being passed around.
	'''
	@abstractmethod
	def addListener(self, l:Listener[TYPE]):
		'''
		Add listener for this observable
		
		@param l the listener to add
		'''

	@abstractmethod
	def removeListener(self, l:Listener[TYPE] ):
		'''
		Remove listener for this observable
		 
		@param l the listener to remove
		'''
