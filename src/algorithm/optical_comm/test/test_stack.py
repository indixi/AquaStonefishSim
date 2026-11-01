"""Three-node optical path: frames are recovered only from synthetic BGR images."""
from collections import defaultdict
import unittest
from test_physical import image
from optical_comm.codecs import BlueGreen2BitCodec
from optical_comm.protocol.frame import FrameCodec
from optical_comm.protocol.state_machine import Protocol,ProtocolConfig
from optical_comm.physical.link import Timing,Transmitter,Receiver
from optical_comm.vision.color_brightness import ColorBrightnessClassifier

class StackTest(unittest.TestCase):
    def _run_optical_exchange(self,drop_first_data=False):
        codec=BlueGreen2BitCodec();frames=FrameCodec();timing=Timing(period=.06,min_samples=2)
        cfg=ProtocolConfig(ack_timeout=4,read_timeout=8,app_timeout=3,session_timeout=100)
        offsets={1:0,2:123,3:777}
        nodes={}
        for identity in (1,2,3):
            vision=ColorBrightnessClassifier(background_frames=1,min_pixels=4);vision.classify(image("OFF"))
            nodes[identity]=dict(core=Protocol("leader" if identity==1 else "follower",identity,config=cfg,peers=(2,3)),
                                 tx=Transmitter(codec,frames,timing),rx=Receiver(codec,frames,timing),
                                 vision=vision,next_tx=0)
        delivered=defaultdict(list);events=[];time=0;dropped=False
        def advance(until):
            nonlocal time,dropped
            while time<until:
                for identity,node in nodes.items():
                    core=node["core"];core.tick(time+offsets[identity])
                    if not node["tx"].busy and time>=node["next_tx"]:
                        frame=core.pop_tx()
                        if frame:
                            node["drop_current"]=bool(drop_first_data and identity==2 and frame.kind.name=="DATA" and not dropped)
                            if node["drop_current"]:dropped=True
                            node["tx"].start(frame,time)
                states={}
                for identity,node in nodes.items():
                    state,done=node["tx"].step(time);states[identity]=state
                    if done:
                        node["core"].tx_done(done,time+offsets[identity]);node["rx"].reset()
                emitting=[identity for identity,state in states.items() if state!="OFF"]
                self.assertLessEqual(len(emitting),1,"two optical transmitters active")
                emitted=states[emitting[0]] if emitting and not nodes[emitting[0]].get("drop_current",False) else "OFF"
                for identity,node in nodes.items():
                    if node["tx"].busy:continue
                    observation=node["vision"].classify(image(emitted))
                    frame=node["rx"].observe(time+offsets[identity],observation.symbol,observation.confidence)
                    if frame:
                        node["core"].receive(frame,time+offsets[identity])
                        node["next_tx"]=time+(timing.guard_symbols+1)*timing.period
                    for event in node["core"].drain_events():
                        events.append((identity,event))
                        if event.kind=="DATA_REQUEST":
                            node["core"].provide_bits(event.request_id,"10101" if identity==2 else "00110",time+offsets[identity])
                        if event.kind=="DATA_RECEIVED":delivered[identity].append(event.bits)
                time+=.005
        def command(op,peer,bits="",expected=None):
            request=op+str(peer)+str(time)
            nodes[1]["core"].submit(op,peer,bits,request,time)
            deadline=time+25
            while time<deadline:
                advance(time+.1)
                if any(i==1 and e.request_id==request and e.kind==expected for i,e in events):return
                failed=[e for i,e in events if i==1 and e.request_id==request and e.kind=="FAILED"]
                self.assertEqual(failed,[])
            self.fail("operation did not finish: "+op)
        for peer in (2,3):
            command("OPEN",peer,expected="SESSION_OPENED")
            command("WRITE",peer,"00000010101",expected="WRITE_CONFIRMED")
            command("READ",peer,"11",expected="READ_COMPLETED")
            command("END",peer,expected="SESSION_ENDED")
        self.assertEqual(delivered[2],["00000010101"])
        self.assertEqual(delivered[3],["00000010101"])
        self.assertEqual([e.bits for i,e in events if i==1 and e.kind=="READ_COMPLETED"],["10101","00110"])
        self.assertFalse(nodes[1]["core"].connected)

    def test_three_robots_exchange_then_end_and_switch_using_images(self):
        self._run_optical_exchange()

    def test_lost_optical_data_is_recovered_only_after_leader_regrants_read(self):
        self._run_optical_exchange(drop_first_data=True)

if __name__=="__main__":unittest.main()
