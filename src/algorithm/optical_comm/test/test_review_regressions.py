import unittest
from unittest.mock import patch
from optical_comm.protocol.frame import Frame,Kind
from optical_comm.protocol.state_machine import Protocol,ProtocolConfig
from optical_comm.codecs import BlueGreen2BitCodec
from optical_comm.physical.link import Timing,Transmitter
from optical_comm.protocol.frame import FrameCodec
from optical_comm.runtime_config import derive_protocol_config

class ReviewRegressionTest(unittest.TestCase):
    def opened(self):
        cfg=ProtocolConfig(ack_timeout=1,read_timeout=5,max_retries=1)
        with patch("secrets.randbits",return_value=123):
            leader=Protocol("leader",1,config=cfg)
        follower=Protocol("follower",2,config=cfg)
        leader.submit("OPEN",2,"","open",0)
        opening=leader.pop_tx();leader.tx_done(opening,0);follower.receive(opening,0)
        ack=follower.pop_tx();leader.receive(ack,0)
        leader.drain_events();follower.drain_events()
        return leader,follower,opening

    def test_follower_data_retry_requires_another_leader_read(self):
        leader,follower,_=self.opened()
        leader.submit("READ",2,"","read",0)
        request=leader.pop_tx();leader.tx_done(request,0);follower.receive(request,0)
        leader.receive(follower.pop_tx(),0)
        token=next(e.request_id for e in follower.drain_events() if e.kind=="DATA_REQUEST")
        follower.provide_bits(token,"1"*100,0)
        response=follower.pop_tx();follower.tx_done(response,4)
        # DATA was lost. At t=5 both old autonomous retry timers would fire.
        follower.tick(5.1);leader.tick(5.1)
        self.assertEqual(follower.drain_tx(),[],"follower must not contend with leader READ retry")
        repeated=leader.pop_tx();self.assertEqual(repeated,request)
        follower.receive(repeated,5.2)
        replies=follower.drain_tx()
        self.assertEqual(replies,[Frame.ack(request),response])
        self.assertEqual([e for e in follower.drain_events() if e.kind=="DATA_REQUEST"],[])
        leader.receive(replies[1],6)
        self.assertEqual([e.bits for e in leader.drain_events() if e.kind=="READ_COMPLETED"],["1"*100])

    def test_end_cache_bound_uses_explicit_ack_timeout(self):
        codec=BlueGreen2BitCodec();frames=FrameCodec();timing=Timing()
        with self.assertRaises(ValueError):
            derive_protocol_config(codec,frames,timing,1.2,{"ack_timeout":200,"closed_cache_time":300})
        valid=derive_protocol_config(codec,frames,timing,1.2,{"ack_timeout":200,"closed_cache_time":1000})
        self.assertEqual(valid.ack_timeout,200)

    def test_restart_cannot_acknowledge_old_session_as_new_delivery(self):
        leader,follower,_=self.opened()
        leader.submit("WRITE",2,"01","old",0)
        write=leader.pop_tx();follower.receive(write,0);follower.drain_tx();follower.drain_events()
        with patch("secrets.randbits",return_value=456):
            restarted=Protocol("leader",1)
        restarted.submit("OPEN",2,"","new",1)
        follower.receive(restarted.pop_tx(),1)
        reply=follower.pop_tx()
        self.assertEqual(reply.kind,Kind.ERROR)
        restarted.receive(reply,1)
        self.assertFalse(restarted.connected)
        self.assertIn("FAILED",[e.kind for e in restarted.drain_events()])

    def test_open_control_nonce_not_limited_by_application_payload_bound(self):
        with patch("secrets.randbits",return_value=123):
            leader=Protocol("leader",1,config=ProtocolConfig(max_payload_bits=10))
        leader.submit("OPEN",2,"","open",0)
        frame=leader.pop_tx()
        self.assertEqual(len(frame.bits),32)
        self.assertEqual(FrameCodec(max_payload_bits=10).decode(FrameCodec(max_payload_bits=10).encode(frame)),frame)

    def test_leader_can_advance_after_data_ack_loss_with_long_ack_timeout(self):
        cfg=ProtocolConfig(ack_timeout=200,read_timeout=400,closed_cache_time=1000)
        leader=Protocol("leader",1,config=cfg);follower=Protocol("follower",2,config=cfg)
        leader.submit("OPEN",2,"","open",0);follower.receive(leader.pop_tx(),0);leader.receive(follower.pop_tx(),0)
        leader.submit("READ",2,"","read",0);follower.receive(leader.pop_tx(),0);leader.receive(follower.pop_tx(),0)
        token=next(e.request_id for e in follower.drain_events() if e.kind=="DATA_REQUEST")
        follower.provide_bits(token,"01",0);data=follower.pop_tx();follower.tx_done(data,1)
        leader.receive(data,1);leader.drain_tx()  # DATA ACK was lost.
        leader.submit("WRITE",2,"11","next",2);follower.receive(leader.pop_tx(),2)
        self.assertEqual([e.bits for e in follower.drain_events() if e.kind=="DATA_RECEIVED"],["11"])
        self.assertEqual(follower.pop_tx().kind,Kind.ACK)

if __name__=="__main__":unittest.main()
