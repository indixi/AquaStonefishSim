import unittest
from optical_comm.codecs import BlueGreen2BitCodec, BlueLevel1BitCodec
from optical_comm.protocol.frame import Frame, Kind, FrameError, FrameCodec, crc8

class CodecTest(unittest.TestCase):
    def test_literal_mapping_and_odd_length(self):
        codec = BlueGreen2BitCodec()
        self.assertEqual(codec.encode("00011011"), ("BLUE_HIGH", "BLUE_LOW", "GREEN_HIGH", "GREEN_LOW"))
        self.assertEqual(codec.decode(codec.encode("10101"), valid_bits=5), "10101")
        with self.assertRaises(ValueError):
            codec.encode("102")
        with self.assertRaises(ValueError):
            codec.decode(("OFF",))

    def test_replace_mapping_without_protocol_changes(self):
        frame = Frame(Kind.WRITE, 4, 2, "101011101")
        wire = FrameCodec().encode(frame)
        for codec in (BlueGreen2BitCodec(), BlueLevel1BitCodec()):
            recovered = codec.decode(codec.encode(wire), valid_bits=len(wire))
            self.assertEqual(FrameCodec().decode(recovered), frame)

    def test_crc_reference_and_corruption(self):
        self.assertEqual(crc8("".join(format(x, "08b") for x in b"123456789")), 0xf4)
        codec = FrameCodec()
        frame = Frame(Kind.OPEN, 3, 0, "0"*32, 1, 2)
        wire = codec.encode(frame)
        self.assertEqual(codec.decode(wire), frame)
        self.assertEqual(codec.expected_bits(wire[:31]), len(wire))
        bad = wire[:5] + str(1-int(wire[5])) + wire[6:]
        with self.assertRaises(FrameError):
            codec.decode(bad)
        with self.assertRaises(ValueError):
            codec.encode(Frame(Kind.WRITE, 1, 1, "1"*257))

    def test_lengths_above_twenty_and_ack_kind(self):
        codec = FrameCodec(max_payload_bits=512)
        frame = Frame(Kind.DATA, 7, 4, "01"*140)
        self.assertEqual(codec.decode(codec.encode(frame)), frame)
        self.assertEqual(Frame.ack(frame).ack_kind, Kind.DATA)
        with self.assertRaises(FrameError):
            codec.decode(codec.encode(frame)[:-1])

if __name__ == "__main__":
    unittest.main()
