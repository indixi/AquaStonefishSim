import unittest
from optical_comm.codecs import BlueGreen2BitCodec
from optical_comm.drivers.stonefish_led import validate_profile
from optical_comm.protocol.state_machine import Protocol,ProtocolConfig

class RuntimeContractTest(unittest.TestCase):
    def test_hardware_loss_aborts_pending_operation_and_clears_session(self):
        protocol=Protocol("leader",1)
        protocol.submit("OPEN",2,"","connect",0)
        protocol.abort_session("engine disconnected")
        self.assertEqual(protocol.drain_tx(),[])
        self.assertIsNone(protocol.pending)
        self.assertFalse(protocol.connected)
        self.assertIn("FAILED",[e.kind for e in protocol.drain_events()])

    def test_failed_local_transmission_can_retry_instead_of_hanging(self):
        protocol=Protocol("leader",1,config=ProtocolConfig(max_retries=1))
        protocol.submit("OPEN",2,"","connect",0)
        frame=protocol.pop_tx()
        protocol.tx_failed(frame,1,"missed deadline")
        protocol.tick(1)
        self.assertEqual(protocol.pop_tx(),frame)

    def test_invalid_physical_symbols_never_reach_led_driver(self):
        codec=BlueGreen2BitCodec()
        with self.assertRaises(ValueError):validate_profile(codec,{})
        profile={symbol:{"rgb":[0,0,1],"brightness":.5} for symbol in codec.data_symbols}
        profile["BLUE_LOW"]["brightness"]=0
        with self.assertRaises(ValueError):validate_profile(codec,profile)

    def test_noninteger_or_nonfinite_counts_cannot_disable_retry_bounds(self):
        from optical_comm.physical.link import Timing
        from optical_comm.vision.color_brightness import ColorBrightnessClassifier
        for invalid in (float("nan"),1.5,True):
            with self.assertRaises(ValueError):ProtocolConfig(max_retries=invalid)
            with self.assertRaises(ValueError):Timing(guard_symbols=invalid)
            with self.assertRaises(ValueError):ColorBrightnessClassifier(background_frames=invalid)

if __name__=="__main__":unittest.main()
