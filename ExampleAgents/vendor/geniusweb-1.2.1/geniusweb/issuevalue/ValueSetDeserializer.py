from typing import List

from pyson.Deserializer import Deserializer
from pyson.ObjectMapper import ObjectMapper
from tudelft.utilities.immutablelist.Range import Range

from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.DiscreteValueSet import DiscreteValueSet
from geniusweb.issuevalue.NumberValueSet import NumberValueSet
from geniusweb.issuevalue.ValueSet import ValueSet


class ValueSetDeserializer (Deserializer):
    
    pyson= ObjectMapper()
    '''
    Deserializes a ValueSet by checking the name of the (one and only) property
    in there.}. This property is coming from the concrete implementations that we
    have: {@link NumberValueSet} and {@link DiscreteValueSet}. This way we can
    avoid putting (redundant) type info in each and every valueset.

    '''
    def deserialize(self, data:object, clas: object) -> ValueSet:
        if not isinstance(data, dict):
            raise ValueError("Expected dict containing ValueSet but found "+str(data))
        if "range" in data:
            rangev:Range=self.pyson.parse(data['range'], Range)
            return NumberValueSet(rangev)
        if "values" in data:
            values = self.pyson.parse(data['values'], List[DiscreteValue])
            return DiscreteValueSet(values)
        raise ValueError("Expected 'range' or 'values' property for ValueSet contents")
