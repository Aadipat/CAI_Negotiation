from decimal import Decimal
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities
from geniusweb.bidspace.Interval import Interval
from geniusweb.issuevalue.Value import Value
from typing import List, Dict, Optional

class IssueInfo:
	'''
	 Tool class to collect all relevant info about one issue (from LinearAdditive)
	 in one class. Used for internally grouping data for more efficient
	 processing. This class may change in the future, not recommended for direct
	 use.
	 <p>
	 immutable
	'''

	def __init__(self, name:str, values:ValueSet ,  utils:ValueSetUtilities,
			weight:Decimal , precision:int ) :
		'''
		@param name      the issue name
		@param values    the {@link ValueSet} of the issue
		@param utils     the {@link ValueSetUtilities} of the issue profile
		@param weight    the weight of the {@link ValueSetUtilities}
		@param precision the precision to compute with. Basically the number of
		         decimal places used for the computations.
		'''
		self._name = name;
		self._values = values;
		self._weightedUtils = self._computeWeightedUtils(utils, weight, precision);
		self._interval = self._getRange();

	def getValues(self) ->ValueSet :
		return self._values

	def getName(self)->str:
		return self._name;

	def getInterval(self)->Interval:
		'''
		@return weighted minimum and maximum utility achievable with this issue,
		    rounded to the requested precision.
		'''
		return self._interval;

	def getExtreme(self, isMax:bool)->Value :
		'''
		@param isMax if true the max {@link Value} is returned, else the min is
		             returned.
		@return the extreme value, either the minimum if isMax=false or maximum
		        if isMax=true
		'''
		extremeutil:Decimal = None #type:ignore
		extremeval:Decimal = None #type:ignore
		for val in self._values:
			util = self._weightedUtils.get(val)
			if extremeval == None:
				extremeutil = self._weightedUtils.get(val) #type:ignore
				extremeval = val
			else:
				if isMax:
					if util > extremeutil: #type:ignore
						extremeutil = util #type:ignore
						extremeval = val
				else:
					if util<extremeutil: #type:ignore
						extremeutil = util #type:ignore
						extremeval = val
		return extremeval #type:ignore

	def getWeightedUtil(self, val:Value ) -> Decimal :
		'''
		@param val the issue value to be evaluated
		@return weighted utility of given value, rounded to nearest value with
		        the requested precision number of digits.
		'''
		return self._weightedUtils.get(val) #type:ignore

	def _subset(self,  interval:Interval) -> List[Value]:
		'''
		@param interval an {@link Interval} of utility values.
		@return all values that are inside the interval.
		'''

		selection:List[Value]  = []
		for value in self._values:
			if interval.contains(self.getWeightedUtil(value)):
				selection.append(value);
		return selection

	def _subsetSize( self, interval:Interval) ->int:
		'''
		Faster way to determine subset size, it does not create a list
		
		@param interval an {@link Interval} of utility values.
		@return size of the subset that you will get from calling subset
		'''
		n = 0
		for value in self._values:
			if interval.contains(self.getWeightedUtil(value)):
				n=n+1
		return n

	def _getRange(self)->Interval :
		'''
		@return the {@link Interval} (minimum and maximum) of the utility of the
		        weighted utility of this issue, properly rounded to the
		        {@link #precision}/

		'''
		min = Decimal(1)
		max = Decimal(0)
		for value in  self._values:
			util = self.getWeightedUtil(value)
			if util < min:
				min = util
			if util > max:
				max = util
		return Interval(min, max)

	def _computeWeightedUtils(self, utilities:ValueSetUtilities, w:Decimal, prec:int) \
				-> Dict[Value, Decimal] :
		map:Dict[Value, Decimal]  = {}

		for val in self._values:
			map[val] = round(utilities.getUtility(val)* w, prec)
		return map
