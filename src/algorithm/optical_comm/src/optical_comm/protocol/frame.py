"""Version-one compact optical frames, independent of ROS and modulation."""
from dataclasses import dataclass
from enum import IntEnum
from optical_comm.codecs.base import validate_bits

class Kind(IntEnum):
    OPEN=1
    ACK=2
    WRITE=3
    READ=4
    DATA=5
    END=6
    ERROR=7

class FrameError(ValueError):
    pass

@dataclass(frozen=True)
class Frame:
    kind: Kind
    session: int
    seq: int
    bits: str = ""
    source: int = None
    target: int = None

    @staticmethod
    def ack(frame):
        return Frame(Kind.ACK,frame.session,frame.seq,format(int(frame.kind),"03b"))

    @property
    def ack_kind(self):
        if self.kind != Kind.ACK or len(self.bits)!=3:
            raise FrameError("invalid ACK payload")
        try:
            return Kind(int(self.bits,2))
        except ValueError as error:
            raise FrameError("invalid acknowledged type") from error

def crc8(bits):
    validate_bits(bits)
    value=0
    for bit in bits:
        feedback=((value>>7)&1)^int(bit)
        value=(value<<1)&255
        if feedback:
            value ^= 0x07
    return value

class FrameCodec:
    header_bits=31  # kind:3, session:8, sequence:8, payload length:12
    def __init__(self,max_payload_bits=256):
        if not 0 <= max_payload_bits <= 4095:
            raise ValueError("max_payload_bits must be in [0,4095]")
        self.max_payload_bits=max_payload_bits

    def encode(self,frame):
        validate_bits(frame.bits)
        try:
            kind=Kind(frame.kind)
        except ValueError as error:
            raise FrameError("invalid frame type") from error
        if not 1<=frame.session<=255 or not 0<=frame.seq<=255:
            raise FrameError("session/sequence outside wire range")
        control_lengths={Kind.OPEN:32,Kind.ACK:3,Kind.END:0,Kind.ERROR:8}
        if kind in control_lengths:
            if len(frame.bits)!=control_lengths[kind]:raise FrameError("invalid control payload length")
        elif len(frame.bits)>self.max_payload_bits:
            raise FrameError("payload exceeds configured maximum")
        header=format(int(kind),"03b")+format(frame.session,"08b")+format(frame.seq,"08b")+format(len(frame.bits),"012b")
        if kind==Kind.OPEN:
            if frame.source is None or frame.target is None or not 1<=frame.source<=15 or not 1<=frame.target<=15:
                raise FrameError("OPEN requires source and target in [1,15]")
            header+=format(frame.source,"04b")+format(frame.target,"04b")
        elif frame.source is not None or frame.target is not None:
            raise FrameError("only OPEN carries addresses")
        if kind==Kind.ACK:
            frame.ack_kind
        body=header+frame.bits
        return body+format(crc8(body),"08b")

    def expected_bits(self,prefix):
        validate_bits(prefix)
        if len(prefix)<self.header_bits:
            return None
        try:
            kind=Kind(int(prefix[:3],2))
        except ValueError as error:
            raise FrameError("invalid header type") from error
        length=int(prefix[19:31],2)
        control_lengths={Kind.OPEN:32,Kind.ACK:3,Kind.END:0,Kind.ERROR:8}
        invalid_length=(length!=control_lengths[kind]) if kind in control_lengths else length>self.max_payload_bits
        if invalid_length or int(prefix[3:11],2)==0:
            raise FrameError("invalid header length/session")
        return self.header_bits+(8 if kind==Kind.OPEN else 0)+length+8

    def decode(self,bits):
        expected=self.expected_bits(bits)
        if expected is None or expected!=len(bits):
            raise FrameError("incomplete or overlong frame")
        if crc8(bits[:-8])!=int(bits[-8:],2):
            raise FrameError("CRC mismatch")
        kind=Kind(int(bits[:3],2)); offset=self.header_bits
        source=target=None
        if kind==Kind.OPEN:
            source=int(bits[offset:offset+4],2);target=int(bits[offset+4:offset+8],2);offset+=8
        frame=Frame(kind,int(bits[3:11],2),int(bits[11:19],2),bits[offset:-8],source,target)
        self.encode(frame)  # Same semantic checks for received and transmitted fields.
        return frame
