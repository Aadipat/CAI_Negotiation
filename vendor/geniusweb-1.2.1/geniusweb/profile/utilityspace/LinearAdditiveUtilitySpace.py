from copy import copy
from decimal import Decimal
import re
from typing import Dict, Optional

from pyson.JsonGetter import JsonGetter

from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities

from geniusweb.utils import toStr


class LinearAdditiveUtilitySpace(LinearAdditive):
    """
    Defines a UtilitySpace in terms of a weighted sum of per-issue preferences.
    immutable. A {@link LinearAdditiveUtilitySpace} works with complete bids.

    Constructor guarantees that
    <ul>
    <li>weights are normalized to 1
    <li>the issues in the utility map and weights map match those in the domain
    <li>The utilities for each issue are proper {@link ValueSetUtilities} objects
    </ul>
    """

    def __init__(
        self,
        domain: Domain,
        name: str,
        issueUtilities: Dict[str, ValueSetUtilities],
        issueWeights: Dict[str, Decimal],
        reservationBid: Optional[Bid] = None,
    ):
        """
        @param domain  the {@link Domain} in which this profile is defined.
        @param name    the name of this profile. Must be simple name (a-Z, 0-9)
        @param issueUtilities   a map with key: issue names (String) and value: the values
                       for that issue. There MUST NOT be a null issue. All values
                       MUST NOT be null.
        @param issueWeights the weight of each issue in the computation of the
                       weighted sum. The issues must be the same as those in the
                       utils map. All weights MUST NOT be null. The weights MUST
                       sum to 1.
        @param reservationBid  the reservation bid. Only bids that are
                       {@link #isPreferredOrEqual(Bid, Bid)} should be accepted.
                       Can be None, meaning that there is no reservation bid and
                       any agreement is better than no agreement.
        @throws NullPointerException     if values are incorrectly null.
        @throws IllegalArgumentException if preconditions not met.
        """
        self._domain = domain
        self._name = name
        self._reservationBid = reservationBid
        self._issueUtilities = copy(issueUtilities)
        self._issueWeights = copy(issueWeights)

        if domain == None:
            raise ValueError("domain=null")

        if issueUtilities == None:
            raise ValueError("utils=null")

        if issueWeights == None:
            raise ValueError("weights=null")

        if None in issueUtilities.values():
            raise ValueError(
                "One of the ValueSetUtilities in issueUtilitiesis null:"
                + str(issueUtilities)
            )

        if None in issueWeights.values():
            raise ValueError("One of the weights is null")

        if None in issueUtilities.keys():
            raise ValueError("One of the issue names is null")

        if name == None or not re.match("[a-zA-Z0-9]+", name):
            raise ValueError("Name must be simple (a-Z, 0-9) but got " + name)

        if issueUtilities.keys() != domain.getIssues():
            raise ValueError(
                "The issues in  utilityspace and domain do not match: utilityspace has issues "
                + str(issueUtilities.keys())
                + " but domain contains "
                + str(domain.getIssues())
            )

        if issueWeights.keys() != domain.getIssues():
            raise ValueError(
                "The issues in weights and domain do not match: weights has "
                + str(issueWeights.keys())
                + " but domain contains "
                + str(domain.getIssues())
            )

        for issue in issueUtilities:
            message: str = issueUtilities.get(issue).isFitting(domain.getValues(issue))  # type:ignore
            if message != None:
                raise ValueError(message)
        total = sum(issueWeights.values())  # type:ignore
        if abs(float(total) - 1.0) > 1e-3:
            raise ValueError(
                "The sum of the weights (" + str(issueWeights.values()) + ") must be 1"
            )

        if reservationBid:
            message1: Optional[str] = domain.isFitting(reservationBid)
            if message1:
                raise ValueError("reservationbid is not fitting domain: " + message1)

    # Override
    def getUtility(self, bid: Bid) -> Decimal:
        return sum(
            [self._util(iss, bid.getValue(iss)) for iss in self._issueWeights.keys()]
        )  # type:ignore

    # Override
    def getWeight(self, issue: str) -> Decimal:
        return self._issueWeights[issue]

    # Override
    def __repr__(self):
        return (
            "LinearAdditive["
            + toStr(self._issueUtilities)
            + ","
            + toStr(self._issueWeights)
            + ","
            + str(self._reservationBid)
            + "]"
        )

    # Override
    def getReservationBid(self) -> Optional[Bid]:
        return self._reservationBid

    def __hash__(self):
        return hash(
            (
                self._domain,
                tuple(self._issueUtilities.items()),
                tuple(self._issueWeights.items()),
                self._name,
                self._reservationBid,
            )
        )

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and self._domain == other._domain
            and self._issueUtilities == other._issueUtilities
            and self._issueWeights == other._issueWeights
            and self._name == other._name
            and self._reservationBid == other._reservationBid
        )

    # Override
    def getDomain(self) -> Domain:
        return self._domain

    # Override
    def getName(self) -> str:
        return self._name

    # Override
    @JsonGetter("issueUtilities")
    def getUtilities(self) -> Dict[str, ValueSetUtilities]:
        return copy(self._issueUtilities)

    # Override
    @JsonGetter("issueWeights")
    def getWeights(self) -> Dict[str, Decimal]:
        return copy(self._issueWeights)

    def _util(self, issue: str, value: Optional[Value]) -> Decimal:
        """
        @param issue the issue to get weighted util for
        @param value the issue value to use (typically coming from a bid). Can be None
        @return weighted util of just the issue value:
                issueUtilities[issue].utility(value) * issueWeights[issue)
        """
        if not value:
            return Decimal(0)
        return self._issueWeights[issue] * self._issueUtilities[issue].getUtility(value)
