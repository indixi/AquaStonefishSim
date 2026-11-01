"""Replaceable, complete fixed-width bit/symbol alphabets."""
from itertools import product

OFF = "OFF"
UNKNOWN = "UNKNOWN"

class TableCodec:
    def __init__(self, mapping):
        self.mapping = dict(mapping)
        if not self.mapping:
            raise ValueError("empty symbol alphabet")
        widths = {len(key) for key in self.mapping}
        if len(widths) != 1 or next(iter(widths)) < 1:
            raise ValueError("keys must have a common positive bit width")
        self.bits_per_symbol = next(iter(widths))
        expected = {"".join(p) for p in product("01", repeat=self.bits_per_symbol)}
        values = tuple(self.mapping.values())
        if set(self.mapping) != expected or len(set(values)) != len(values):
            raise ValueError("alphabet must cover every bit pattern exactly once")
        if any(not isinstance(v,str) or v in (OFF,UNKNOWN) for v in values):
            raise ValueError("OFF/UNKNOWN are not data symbols")
        self.inverse = {v:k for k,v in self.mapping.items()}
        self.data_symbols = frozenset(values)
        self.sync_symbol = self.mapping["0"*self.bits_per_symbol]

    def encode(self, bits):
        validate_bits(bits)
        width = self.bits_per_symbol
        padded = bits + "0"*((-len(bits))%width)
        return tuple(self.mapping[padded[i:i+width]] for i in range(0,len(padded),width))

    def decode(self, symbols, valid_bits=None):
        try:
            bits = "".join(self.inverse[s] for s in symbols)
        except KeyError as error:
            raise ValueError("unknown data symbol") from error
        if valid_bits is None:
            return bits
        if not isinstance(valid_bits,int) or valid_bits < 0 or valid_bits > len(bits):
            raise ValueError("invalid effective bit length")
        if any(c != "0" for c in bits[valid_bits:]):
            raise ValueError("nonzero padding")
        return bits[:valid_bits]

class BlueGreen2BitCodec(TableCodec):
    def __init__(self):
        super().__init__({"00":"BLUE_HIGH","01":"BLUE_LOW","10":"GREEN_HIGH","11":"GREEN_LOW"})

class BlueLevel1BitCodec(TableCodec):
    def __init__(self):
        super().__init__({"0":"BLUE_HIGH","1":"BLUE_LOW"})

def make_codec(name):
    factories = {"blue_green_2bit":BlueGreen2BitCodec,"blue_level_1bit":BlueLevel1BitCodec}
    if name not in factories:
        raise ValueError("unknown codec: "+name)
    return factories[name]()

def validate_bits(bits):
    if not isinstance(bits,str) or any(c not in "01" for c in bits):
        raise ValueError("payload must be a string of 0 and 1")
