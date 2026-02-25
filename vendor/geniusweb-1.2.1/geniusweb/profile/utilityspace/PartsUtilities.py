# Generated from java by J2P - Modified to remove plum dependency
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional, Union

from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.profile.utilityspace.ProductOfValue import ProductOfValue
from geniusweb.profile.utilityspace.ValueSetUtilities import ValueSetUtilities
from tudelft.utilities.tools.safehash import safehash

if TYPE_CHECKING:
    pass


class PartUtil:
    """
    Contains list of values, and the utility for this combi of values. The values
    make only sense with a corresponding list of issues, but that is managed in
    (see PartsUtilities).

    Immutable.
    """

    def __init__(self, values: list[Optional[Value]], util: Decimal):
        self.__values: list[Optional[Value]] = values
        self.__util: Decimal = util

    def getValues(self) -> list[Optional[Value]]:
        return self.__values

    def getUtil(self) -> Decimal:
        return self.__util


class PartsUtilities(ValueSetUtilities):
    """
    Contains utilities of a ProductOfValue of a SumOfGroupsUtilitySpace.
    So this is similar to a DiscreteValueSetUtilities but instead of
    issues this contains an (ordered) list of issues. This object serializes to
    something like:

        {"partsutils":
        {"issues":["issue1","issue2"],
        "utilslist":[{"values":["low","low"],"util":0.3},{"values":["high","high"],"util":0.9}]}}

    The issues field contains a list of N issues in the domain, The
    utilslist contains a list of dictionaries, with "values" containing a list of
    N issue values, in the same order as the issues list and with "util"
    containing the utility value of that set of values.
    """

    def __init__(
        self,
        issues: list[str],
        utils: Union[list[PartUtil], dict[ProductOfValue, Decimal]],
    ):
        """
        Initialize PartsUtilities.

        Args:
            issues: list of issues
            utils: Either a list of PartUtil objects, or a dict mapping
                   ProductOfValue to Decimal utilities. All list-of-values
                   missing from the map are assumed to have utility 0.
        """
        super().__init__()
        self.__issues: list[str] = []
        self.__utilities: dict[ProductOfValue, Decimal] = {}
        self.__utilslist: list[PartUtil] = []

        if issues is None or utils is None or not issues:
            raise ValueError("issues and utils must be not null or empty")

        self.__issues = issues

        # Handle both list and dict inputs
        if isinstance(utils, list):
            # Convert list of PartUtil to dict
            utils_dict = self.__list2map(utils)
        else:
            utils_dict = utils

        self.__utilities.update(utils_dict)
        self.__checkUtilities()

        for pval in self.__utilities.keys():
            util = self.__utilities.get(pval)
            if util is not None:
                self.__utilslist.append(PartUtil(pval.getValues(), util))

    def getUtility(self, value: Value) -> Decimal:
        """
        Get the utility of a value.

        Args:
            value: the ProductOfValue value

        Returns:
            the utility of the value. Returns 0 if there is no utility set for
            the given combination of values. Notice, partial bids will
            usually have utility 0.
        """
        if not isinstance(value, ProductOfValue):
            return Decimal(0)
        val: Optional[Decimal] = self.__utilities.get(value)
        if val is None:
            return Decimal(0)
        return val

    def getUtilsList(self) -> list[PartUtil]:
        return list(self.__utilslist)

    def isFitting(self, valueset: ValueSet) -> Optional[str]:
        # what can we test here?
        return None

    def getIssues(self) -> list[str]:
        """
        Returns:
            the issues that are contained here.
        """
        return self.__issues

    def getUtilities(self) -> dict[ProductOfValue, Decimal]:
        """
        Returns:
            map with all available values and their utilities. The map and
            its contents should all be immutable.
        """
        return dict(self.__utilities)

    def add(self, other: PartsUtilities) -> PartsUtilities:
        """
        Combine two PartsUtilities maps.

        Args:
            other: another PartsUtilities map. The issues in the other
                   map must be different from self.issues.

        Returns:
            new PartsUtils, with the powermap of all combinations of one
            element from this and one from the other map, and with the
            utilities computed as the sum of thisvalue + othervalue.
        """
        for issue in self.__issues:
            if issue in other.__issues:
                raise ValueError(f"Issue {issue} exists already")

        combinedissues: list[str] = list(self.__issues)
        combinedissues.extend(other.__issues)
        combinedvalues: dict[ProductOfValue, Decimal] = {}

        for productOfValue in self.__utilities.keys():
            for otherProductOfValue in other.__utilities.keys():
                combinedutil: Decimal = self.getUtility(
                    productOfValue
                ) + other.getUtility(otherProductOfValue)
                combinedvalues[productOfValue.merge(otherProductOfValue)] = combinedutil

        return PartsUtilities(combinedissues, combinedvalues)

    def __hash__(self) -> int:
        prime: int = 31
        result: int = 1
        result = (prime * result) + (
            0 if self.__issues is None else safehash(self.__issues)
        )
        result = (prime * result) + (
            0 if self.__utilities is None else safehash(self.__utilities)
        )
        return result

    def __eq__(self, obj: Optional[Any]) -> bool:
        if self is obj:
            return True
        if obj is None:
            return False
        if type(self) is not type(obj):
            return False
        other: PartsUtilities = obj
        if self.__issues is None:
            if other.__issues is not None:
                return False
        elif self.__issues != other.__issues:
            return False
        if self.__utilities is None:
            if other.__utilities is not None:
                return False
        elif self.__utilities != other.__utilities:
            return False
        return True

    def __repr__(self) -> str:
        return f"PartsUtilities[{self.__issues},{self.__utilities}]"

    def __checkUtilities(self) -> None:
        if any(x is None or x < 0 or x > 1 for x in self.__utilities.values()):
            raise ValueError("part weights must all be in [0,1]")

    @staticmethod
    def __list2map(lst: list[PartUtil]) -> dict[ProductOfValue, Decimal]:
        result: dict[ProductOfValue, Decimal] = {}
        for partutil in lst:
            result[ProductOfValue(partutil.getValues())] = partutil.getUtil()
        return result

    def getMaxUtility(self) -> Decimal:
        """
        Returns:
            the max utility of all values contained here.
        """
        maxutil: Decimal = Decimal(0)
        for key in self.__utilities.keys():
            val = self.__utilities.get(key)
            if val is not None and val.compare(maxutil) > 0:
                maxutil = val
        return maxutil
