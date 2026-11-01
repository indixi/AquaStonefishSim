import unittest
import numpy as np
from optical_comm.codecs import BlueGreen2BitCodec,BlueLevel1BitCodec
from optical_comm.protocol.frame import Frame,Kind,FrameCodec
from optical_comm.physical.link import Timing,Transmitter,Receiver
from optical_comm.vision.color_brightness import ColorBrightnessClassifier

PIXELS={"OFF":(12,12,12),"BLUE_HIGH":(245,55,5),"BLUE_LOW":(95,22,2),
        "GREEN_HIGH":(20,245,5),"GREEN_LOW":(8,95,2)}

def image(symbol):
    value=np.full((12,12,3),12,dtype=np.uint8)
    if symbol!="OFF": value[3:9,3:9]=PIXELS[symbol]
    return value

class PhysicalTest(unittest.TestCase):
    def test_image_round_trip_with_unrelated_receiver_clock(self):
        for codec in (BlueGreen2BitCodec(),BlueLevel1BitCodec()):
            frames=FrameCodec()
            timing=Timing(period=.12,min_samples=2)
            tx=Transmitter(codec,frames,timing)
            rx=Receiver(codec,frames,timing)
            vision=ColorBrightnessClassifier(background_frames=3,min_pixels=4)
            for i in range(3): vision.classify(image("OFF"))
            target=Frame(Kind.WRITE,7,4,"000000001111101")
            tx.start(target,10)
            recovered=[]
            t=9.8
            while t<10+tx.duration(target)+.5:
                state,finished=tx.step(t)
                observation=vision.classify(image(state))
                frame=rx.observe(t+1234,observation.symbol,observation.confidence)
                if frame: recovered.append(frame)
                t+=.015
            self.assertEqual(recovered,[target])

    def test_unknown_samples_do_not_invent_bits(self):
        codec=BlueGreen2BitCodec();frames=FrameCodec();timing=Timing(period=.1,min_samples=2)
        tx=Transmitter(codec,frames,timing);rx=Receiver(codec,frames,timing)
        target=Frame(Kind.WRITE,2,1,"111000")
        tx.start(target,0)
        output=[]
        for i in range(1500):
            t=i*.01;symbol,_=tx.step(t)
            if .9<t<1.2:symbol="UNKNOWN"
            frame=rx.observe(t,symbol,1)
            if frame:output.append(frame)
        self.assertEqual(output,[])

    def test_late_scheduler_aborts_instead_of_skipping_symbols(self):
        codec=BlueGreen2BitCodec();frames=FrameCodec();timing=Timing(period=.1)
        tx=Transmitter(codec,frames,timing)
        tx.start(Frame(Kind.END,1,0),0)
        tx.step(0)
        with self.assertRaises(RuntimeError): tx.step(.5)
        self.assertFalse(tx.busy)

if __name__=="__main__":unittest.main()
