

from decimal import Decimal
from typing import List, Dict

from tudelft.utilities.immutablelist.AbstractImmutableList import AbstractImmutableList
from tudelft.utilities.immutablelist.FixedList import FixedList
from tudelft.utilities.immutablelist.ImmutableList import ImmutableList
from tudelft.utilities.immutablelist.JoinedList import JoinedList
from tudelft.utilities.immutablelist.MapList import MapList
from tudelft.utilities.immutablelist.Tuple import Tuple

from geniusweb.bidspace.Interval import Interval
from geniusweb.bidspace.IssueInfo import IssueInfo
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.utils import val


class BidsWithUtility:
	'''
	Tool class containing functions dealing with utilities of all bids in a given
	{@link LinearAdditive}. This class caches previously computed values to
	accelerate the calls and subsequent calls. Re-use the object to keep/reuse
	the cache.
	<h2>Rounding</h2> Internally, utilities of bids are rounded to the given
	precision. This may cause inclusion/exclusion of some bids in the results.
	See {@link #BidsWithUtility(LinearAdditive, int)} for more details
	Immutable.
	'''

	def __init__(self, issuesInfo:List[IssueInfo] , precision:int):
		'''
		@param issuesInfo List of the relevant issues (in order of relevance) and
		                  all info of each issue.
		@param precision the number of digits to use for computations. In
		                 practice, 6 seems a good default value.
		                 <p>
		                 All utilities * weight are rounded to this number of
		                 digits. This value should match the max number of
		                 (digits used in the weight of an issue + number of
		                 digits used in the issue utility). To determine the
		                 optimal value, one may consider the step size of the
		                 issues, and the range of interest. For instance if the
		                 utility function has values 1/3 and 2/3, then these have
		                 an 'infinite' number of relevant digits. But if the goal
		                 is to search bids between utility 0.1 and 0.2, then
		                 computing in 2 digits might already be sufficient.
		                 <p>
		                 This algorithm has memory and space complexity O(
		                 |nissues| 10^precision ). For spaces up to 7 issues, 7
		                 digits should be feasible; for 9 issues, 6 digits may be
		                 the maximum.
		'''
		if issuesInfo == None or len(issuesInfo) == 0:
			raise ValueError("sortedissues list must contain at least 1 element")
		self._issueInfo = issuesInfo;
		self._precision = precision;
		# cache. Key = call arguments for {@link #get(int, Interval)}. Value=return
	 	# value of that call.

		self._cache:Dict[Tuple[int, Interval], ImmutableList[Bid]] = {}

	@staticmethod
	def create(space:LinearAdditive, precision:int=6) -> "BidsWithUtility":
		'''
		Support constructor, uses default precision 6. This value seems practical
		for the common range of issues, utilities and weights. See
		{@link #BidsWithUtility(LinearAdditive, int)} for more details on the
		precision.
		
		@param space the {@link LinearAdditive} to analyze
		@param space     the {@link LinearAdditive} to analyze. Optional, defaults to 6
		'''
		return BidsWithUtility(BidsWithUtility._getInfo(space, precision), precision);

	def getRange(self) -> Interval:
		'''
		@return the (rounded) utility {@link Interval} of this space: minimum and
		        maximum achievable utility.
		'''
		return self._getRange(len(self._issueInfo) - 1)

	def getBids(self, range: Interval) -> ImmutableList[Bid]:
		'''
		@param range the minimum and maximum utility required of the bids. to be
		             included (both ends inclusive).
		@return a list with bids that have a (rounded) utility inside range.
		        possibly empty.
		'''
		return self._get(len(self._issueInfo) - 1, range.round(self._precision));

	def getInfo(self) -> List[IssueInfo]:
		return self._issueInfo.copy()

	def getExtremeBid(self, isMax:bool) -> Bid:
		'''
		@param isMax the extreme bid required
		@return the extreme bid, either the minimum if isMax=false or maximum if
		        isMax=true
		'''
		map:Dict[str, Value] = {}
		for info in self._issueInfo:
			map[info.getName()] = info.getExtreme(isMax)
		return Bid(map)

	def _get(self, n:int , goal:Interval) -> ImmutableList[Bid]:
		'''
		Create partial BidsWithUtil list considering only issues 0..n, with
		utilities in given range.
		
		@param n    the number of issueRanges to consider, we consider 0..n here.
		            The recursion decreases n until n=0
		@param goal the minimum and maximum utility required of the bids. to be
		            included (both ends inclusive)
		@return BidsWithUtil list, possibly empty.
		'''
		if goal == None:
			raise ValueError("Interval=null")

		# clamp goal into what is reachable. Avoid caching empty
		goal = goal.intersect(self._getRange(n))
		if (goal.isEmpty()):
			return FixedList([])

		cachetuple = Tuple(n, goal)
		if (cachetuple in self._cache):
			return self._cache[cachetuple]

		result = self._checkedGet(n, goal)
		self._cache[cachetuple] = result
		return result

	@staticmethod
	def _getInfo(space2:LinearAdditive , precision:int) -> List[IssueInfo]:
		dom = space2.getDomain()
		return [IssueInfo(issue, dom.getValues(issue), \
				val(space2.getUtilities().get(issue)), \
				space2.getWeight(issue), precision) \
				for issue in dom.getIssues()]

	def _checkedGet(self, n:int, goal:Interval) -> ImmutableList[Bid]:
		info = self._issueInfo[n]
		# issue is the first issuesWithRange.
		issue = info.getName()

		if n == 0:
			return OneIssueSubset(info, goal)

		# make new list, joining all sub-lists
		fulllist:ImmutableList[Bid] = FixedList([])
		for val in info.getValues():
			weightedutil = info.getWeightedUtil(val)
			subgoal = goal.subtract(weightedutil)
			# recurse: get list of bids for the subspace
			partialbids = self._get(n - 1, subgoal)

			bid = Bid({issue: val})
			fullbids = BidsWithUtility.maplist(bid, partialbids)
			if fullbids.size() != 0:
				fulllist = JoinedList[Bid]([fullbids, fulllist])
		return fulllist
	
	@staticmethod
	def maplist(bid: Bid, partialbids: ImmutableList[Bid]) -> ImmutableList[Bid]:
		'''
		this is just to force a scope onto bid
		'''
		return MapList[Bid, Bid](lambda pbid: pbid.merge(bid), partialbids)

	def _getRange(self, n:int) -> Interval:
		'''
		@param n the maximum issuevalue utility to include. Use n=index of last
		         issue s= (#issues in the domain - 1) for the full range of this
		         domain.
		@return Interval (min, max) of the total weighted utility Interval of
		        issues 0..n. All weighted utilities have been rounded to the set
		        {@link #precision}
		'''
		value = Interval(Decimal(0), Decimal(0))
		for i in range(0, n + 1):  # include end point
			value = value.add(self._issueInfo[i].getInterval())
		return value


class OneIssueSubset (AbstractImmutableList[Bid]):
	'''
	List of all one-issue bids that have utility inside given interval.
	'''

	def __init__(self, info:IssueInfo , interval:Interval):
		'''
		@param info     the {@link IssueInfo}
		@param interval a utility interval (weighted)
		'''
		self._info = info;
		self._interval = interval;
		self._size = info._subsetSize(interval)

	# Override
	def get(self, index:int) -> Bid:
		return Bid({self._info.getName():
				self._info._subset(self._interval)[index]})

	# Override
	def size(self) -> int:
		return self._size
