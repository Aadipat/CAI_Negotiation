from _decimal import Decimal

from pyson.Deserializer import Deserializer

from geniusweb.issuevalue.DiscreteValue import DiscreteValue
from geniusweb.issuevalue.NumberValue import NumberValue
from geniusweb.issuevalue.Value import Value


class ValueDeserializer (Deserializer):
    def deserialize(self, data:object, clas: object) -> Value:
        if isinstance(data, float) or isinstance(data, int):
            return NumberValue(Decimal(str(data)))
        if isinstance(data,str):
            return DiscreteValue(data)
        raise ValueError("Expected number or double quoted string but found " + str(data)
                            + " of type " + str(type(data)))

