from copy import copy
import re
from typing import Dict, Set, Optional

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.ValueSet import ValueSet


class Domain:
	'''
	A domain description. 
	'''

	def __init__(self,  name:str,  issuesValues :Dict[str, ValueSet]) :
		'''
		@param name a short name for display/toString. This name must
		                 contain simple characters only (a-z, A-Z, 0-9).
	 	@param issuesValues    the issues and values, Map with key: the issue name and value:
	 	                 {@link ValueSet} with the allowed values for the issue.		'''
		if issuesValues == None:
			raise ValueError("issues=null")
		if name == None:
			raise ValueError("shortName=null")
		if not re.match("[a-zA-Z0-9]+", name):
			raise ValueError("domain name can have only simple characters but found "+ name)
		if len(issuesValues)==0:
			raise ValueError("issuesValues is empty set");

		self._name = name;
		self._issuesValues = dict(issuesValues) #'freeze'...
	


	def getName(self) ->str:
		'''
		@return short name for this domain.

		'''
		return self._name

	def getIssues(self) -> Set[str] :
		'''
		@return set of the issues in this domain.
		'''
		#workaround bug, issueValue
		return set(self._issuesValues.keys())
	
	def getIssuesValues(self):
		return copy(self._issuesValues)

	def isFitting(self,  bid:Bid) -> Optional[str]:
		'''
		@param bid the {@link Bid} to be checked
		@return None if bid is fitting, or a string containing a message
		        explaining why not. A bid is fitting if all issues are in the
		        domain and all issue values are known values.
		'''
		for issue in bid.getIssues(): 
			if not issue in self._issuesValues:
				return "bid " + str(bid) + " refers to non-domain issue '" + issue  + "'"
			if not bid.getValue(issue) in self._issuesValues[issue]:
				return "issue '" + issue + "' in bid has illegal value " + str(bid.getValue(issue))
		return None

	def isComplete(self,  bid:Bid) -> Optional[str] :
		'''
		@param bid a Bid
		@return null if this bid is complete, or an error message explaining why
		        the bid is not complete. Complete means that the bid contains a
		        valid value for each issue in the domain and no values for
		        unknown issues.
		'''
		if self._issuesValues.keys() != bid.getIssues(): 
			return "Issues in bid (" + str(bid.getIssues())  \
					+ ") do not match issues in domain ("  \
					+str(self._issuesValues.keys()) + ")"
		return self.isFitting(bid);

	def getValues( self, issue:str) ->ValueSet :
		'''
		@param issue the issue for which allowed values are needed
		@return set of allowed values for given issue, or null if there is no
		        such an issue.

		'''
		return self._issuesValues[issue]

	def __hash__(self):
		return hash((self._name, tuple(self._issuesValues.items())))

	def __eq__(self, other):
		return isinstance(other, self.__class__) \
			 and  self._issuesValues == other._issuesValues and self._name==other._name

	def __repr__(self):
		return "Domain["+self._name+","+repr(self._issuesValues)+"]"