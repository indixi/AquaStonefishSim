import unittest
from optical_comm.protocol.frame import Frame, Kind
from optical_comm.protocol.state_machine import Protocol, ProtocolConfig

class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.cfg = ProtocolConfig(ack_timeout=1, read_timeout=4, app_timeout=2,
                                  max_retries=1, session_timeout=30)
        self.l = Protocol("leader", 1, config=self.cfg, peers=(2,3))
        self.f = Protocol("follower", 2, config=self.cfg)
        self.other = Protocol("follower", 3, config=self.cfg)

    def deliver(self, sender, receivers, now=0):
        frames = sender.drain_tx()
        for frame in frames:
            sender.tx_done(frame, now)
            for receiver in receivers:
                receiver.receive(frame, now)
        return frames

    def opened(self):
        self.l.submit("OPEN", 2, "", "open", 0)
        self.deliver(self.l, [self.f,self.other])
        self.assertEqual(self.other.drain_tx(), [])
        self.deliver(self.f,[self.l])
        self.assertTrue(self.l.connected)
        self.l.drain_events();self.f.drain_events()

    def test_addressing_and_locked_session(self):
        self.opened()
        with self.assertRaises(ValueError):
            self.l.submit("OPEN",3,"","switch",1)
        with self.assertRaises(ValueError):
            self.f.submit("WRITE",1,"01","unsolicited",1)

    def test_ack_loss_retries_without_duplicate_delivery(self):
        self.opened()
        self.l.submit("WRITE",2,"10101","write",0)
        first=self.deliver(self.l,[self.f])
        self.f.drain_tx()  # Lost ACK.
        self.assertEqual([e.bits for e in self.f.drain_events() if e.kind=="DATA_RECEIVED"],["10101"])
        self.l.tick(1.1)
        self.assertEqual(self.deliver(self.l,[self.f],1.1),first)
        self.assertEqual([e for e in self.f.drain_events() if e.kind=="DATA_RECEIVED"],[])
        self.deliver(self.f,[self.l],1.1)
        self.assertIn("WRITE_CONFIRMED",[e.kind for e in self.l.drain_events()])

    def test_read_provider_duplicate_and_data_ack_loss(self):
        self.opened()
        self.l.submit("READ",2,"11","read",0)
        request=self.deliver(self.l,[self.f])[0]
        events=self.f.drain_events()
        token=next(e.request_id for e in events if e.kind=="DATA_REQUEST")
        self.f.receive(request,.1)
        self.assertEqual([e for e in self.f.drain_events() if e.kind=="DATA_REQUEST"],[])
        self.f.provide_bits(token,"0110101",.1)
        self.deliver(self.f,[self.l],.2)
        result=[e for e in self.l.drain_events() if e.kind=="READ_COMPLETED"]
        self.assertEqual([e.bits for e in result],["0110101"])
        self.l.drain_tx()  # Lost DATA ACK.
        self.f.tick(1.3)
        self.deliver(self.f,[self.l],1.3)
        self.assertEqual([e for e in self.l.drain_events() if e.kind=="READ_COMPLETED"],[])
        self.deliver(self.l,[self.f],1.3)
        self.assertIsNone(self.f.pending)

    def test_end_ack_loss_then_switch(self):
        self.opened()
        self.l.submit("END",2,"","end",0)
        self.deliver(self.l,[self.f])
        self.assertFalse(self.f.connected)
        self.f.drain_tx()
        self.l.tick(1.1)
        self.deliver(self.l,[self.f],1.1)
        self.deliver(self.f,[self.l],1.1)
        self.assertFalse(self.l.connected)
        self.l.submit("OPEN",3,"","other",2)
        self.deliver(self.l,[self.f,self.other],2)
        self.assertEqual(self.f.drain_tx(),[])
        self.deliver(self.other,[self.l],2)
        self.assertEqual(self.l.peer_id,3)

    def test_timeout_starts_after_transmission_and_is_bounded(self):
        self.l.submit("OPEN",2,"","open",0)
        frame=self.l.drain_tx()[0]
        self.l.tick(100)
        self.assertEqual(self.l.drain_tx(),[])
        self.l.tx_done(frame,100)
        self.l.tick(101.1)
        self.l.drain_tx()
        self.l.tx_done(frame,102)
        self.l.tick(103.1)
        self.assertFalse(self.l.connected)
        self.assertIn("FAILED",[e.kind for e in self.l.drain_events()])

    def test_wrong_ack_and_provider_timeout(self):
        self.opened()
        self.l.submit("WRITE",2,"01","write",0)
        frame=self.deliver(self.l,[self.f])[0]
        self.l.receive(Frame(Kind.ACK,frame.session,frame.seq,"110"),.1)
        self.assertIsNotNone(self.l.pending)
        self.deliver(self.f,[self.l],.2)
        self.l.submit("READ",2,"","read",.3)
        self.deliver(self.l,[self.f],.3)
        self.f.tick(2.4)
        self.deliver(self.f,[self.l],2.4)
        self.assertIn("FAILED",[e.kind for e in self.l.drain_events()])

if __name__ == "__main__":
    unittest.main()
