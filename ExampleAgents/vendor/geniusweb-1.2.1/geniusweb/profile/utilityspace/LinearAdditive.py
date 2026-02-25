from decimal import Decimal
from typing import Dict

from geniusweb.profile.utilityspace.UtilitySpace import UtilitySpace
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities


class LinearAdditive ( UtilitySpace):
	'''
	interface to a Utilityspace that is linear-additive.

	'''
	def getUtilities(self) -> Dict[str, ValueSetUtilities] :
		'''
		@return the map from issue names to valuesetutilities (un-weighted)
		'''

	def getWeights(self) -> Dict[str, Decimal] :
		'''
		@return the map from issue names to weights. weights sum to 1.
		'''

	def  getWeight(self, issue:str) -> Decimal:		'''
		@param issue the issue name
		@return the weight of the given issue
		'''

