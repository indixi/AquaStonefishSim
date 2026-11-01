"""ROS-only boundary. The receiver subscribes exclusively to its own camera."""
import json
import math
import threading
import uuid
from dataclasses import asdict
from .codecs import make_codec
from .protocol.frame import Frame,Kind,FrameCodec
from .protocol.state_machine import Protocol
from .runtime_config import derive_protocol_config
from .physical.link import Timing,Transmitter,Receiver
from .vision.color_brightness import ColorBrightnessClassifier
from .drivers.clock import MonotonicClock
from .drivers.stonefish_led import LedDriver

class OpticalCommNode:
    def __init__(self):
        import rospy
        from cv_bridge import CvBridge,CvBridgeError
        from sensor_msgs.msg import Image
        from std_msgs.msg import String
        from optical_comm.msg import CommRequest,CommEvent
        self.ros=rospy;self.String=String;self.EventMessage=CommEvent;self.CvBridgeError=CvBridgeError
        self.lock=threading.RLock();self.clock=MonotonicClock();self.cv=CvBridge()
        self.vehicle=rospy.get_param("~vehicle_name")
        self.node_id=int(rospy.get_param("~node_id"))
        self.role=rospy.get_param("~role")
        self.codec=make_codec(rospy.get_param("~codec","blue_green_2bit"))
        self.timing=Timing(**rospy.get_param("~timing",{}))
        self.turnaround=float(rospy.get_param("~turnaround_symbols",self.timing.guard_symbols+1))*self.timing.period
        hz=float(rospy.get_param("~tick_hz",50))
        settle=float(rospy.get_param("~startup_settle",3))
        if not math.isfinite(hz) or hz<=0 or 1/hz>self.timing.period*.25:
            raise ValueError("tick_hz must provide at least four ticks per symbol")
        if not math.isfinite(settle) or settle<0 or not math.isfinite(self.turnaround) or self.turnaround<(self.timing.guard_symbols+1)*self.timing.period:
            raise ValueError("invalid startup/turnaround timing")
        cfg=rospy.get_param("~protocol",{})
        self.frames=FrameCodec(int(cfg.get("max_payload_bits",256)))
        self.tx=Transmitter(self.codec,self.frames,self.timing)
        self.rx=Receiver(self.codec,self.frames,self.timing)
        protocol_cfg=derive_protocol_config(self.codec,self.frames,self.timing,self.turnaround,cfg)
        max_open=self.tx.duration(Frame(Kind.OPEN,1,0,"0"*32,1,2))
        longest=self.tx.duration(Frame(Kind.DATA,1,1,"0"*self.frames.max_payload_bits))
        self.operation_wait_bound=(protocol_cfg.max_retries+1)*(max(protocol_cfg.ack_timeout,protocol_cfg.read_timeout)+max(longest,max_open)+self.turnaround)+2*protocol_cfg.ack_timeout
        self.protocol=Protocol(self.role,self.node_id,int(rospy.get_param("~leader_id",1)),
                               protocol_cfg,rospy.get_param("~peers",[2,3]))
        self.vision=ColorBrightnessClassifier(**rospy.get_param("~vision",{}))
        self.led=LedDriver(self.vehicle,self.codec,rospy.get_param("~symbols"))
        self._settle_until=self.clock.now()+settle
        self._next_tx_at=0.;self._active_frame=None;self._was_ready=False
        self._last_status=-math.inf;self._last_observation=-math.inf
        self.events=rospy.Publisher("~event",CommEvent,queue_size=50)
        self.status=rospy.Publisher("~state",String,queue_size=1,latch=True)
        self.observations=rospy.Publisher("~observation",String,queue_size=1)
        self.image_sub=rospy.Subscriber("/"+self.vehicle+"/rgb/image_color",Image,self._image,queue_size=1,buff_size=2**22)
        self.request_sub=rospy.Subscriber("~request",CommRequest,self._request,queue_size=20)
        self.timer=rospy.Timer(rospy.Duration(1/hz),self._tick)
        rospy.on_shutdown(self._shutdown)
        rospy.loginfo("Optical %s id=%d T=%.3fs ACK timeout=%.2fs READ timeout=%.2fs",
                      self.role,self.node_id,self.timing.period,protocol_cfg.ack_timeout,protocol_cfg.read_timeout)

    @property
    def ready(self):
        return self.led.ready and self.vision.ready and self.clock.now()>=self._settle_until

    def _publish_event(self,kind,request_id="",peer=0,bits="",detail=""):
        msg=self.EventMessage()
        msg.header.stamp=self.ros.Time.now()
        msg.kind=kind;msg.node_id=self.node_id;msg.peer_id=peer
        msg.request_id=request_id;msg.bits=bits;msg.detail=detail
        self.events.publish(msg)

    def _flush(self):
        for event in self.protocol.drain_events():
            self._publish_event(event.kind,event.request_id,event.peer_id,event.bits,event.detail)

    def _request(self,message):
        with self.lock:
            request_id=message.request_id or uuid.uuid4().hex[:12]
            try:
                if not self.ready:raise ValueError("not ready: need patched light backend and idle-camera background")
                names={1:"OPEN",2:"WRITE",3:"READ",4:"END",5:"PROVIDE"}
                operation=names.get(message.operation)
                if operation is None:raise ValueError("unknown operation")
                now=self.clock.now()
                if operation=="PROVIDE":
                    self.protocol.provide_bits(request_id,message.bits,now)
                else:
                    self.protocol.submit(operation,message.peer_id,message.bits,request_id,now)
            except ValueError as error:
                self._publish_event("REJECTED",request_id,message.peer_id,detail=str(error))
            self._flush()

    def _image(self,message):
        try:
            image=self.cv.imgmsg_to_cv2(message,desired_encoding="bgr8")
        except self.CvBridgeError as error:
            self.ros.logwarn_throttle(5,"Optical image conversion failed: "+str(error));return
        with self.lock:
            now=self.clock.now()
            if now<self._settle_until or self.tx.busy:
                return
            try:
                observation=self.vision.classify(image)
            except ValueError as error:
                self.ros.logwarn_throttle(5,"Optical image rejected: "+str(error));return
            if now-self._last_observation>=.2:
                self.observations.publish(self.String(data=json.dumps(asdict(observation))))
                self._last_observation=now
            if not self.ready:return
            previous_errors=self.rx.errors
            frame=self.rx.observe(now,observation.symbol,observation.confidence)
            if self.rx.errors!=previous_errors:
                self._publish_event("RX_REJECTED",detail=self.rx.last_error)
            if frame is not None:
                self._next_tx_at=max(self._next_tx_at,now+self.turnaround)
                self.protocol.receive(frame,now)
                self._flush()

    def _tick(self,_event):
        with self.lock:
            now=self.clock.now()
            ready=self.ready
            if self._was_ready and not ready:
                self.tx.abort();self._active_frame=None;self.rx.reset()
                self.protocol.abort_session("optical hardware became unavailable")
            self._was_ready=ready
            if ready:
                self.protocol.tick(now)
                if not self.tx.busy and now>=self._next_tx_at:
                    frame=self.protocol.pop_tx()
                    if frame is not None:
                        self._active_frame=frame;self.rx.reset()
                        self.tx.start(frame,now)
                try:
                    symbol,finished=self.tx.step(now)
                    self.led.set_symbol(symbol)
                    if finished is not None:
                        self.protocol.tx_done(finished,now)
                        self._active_frame=None;self.rx.reset()
                        self._publish_event("FRAME_SENT",detail=finished.kind.name)
                except RuntimeError as error:
                    failed=self._active_frame;self._active_frame=None
                    self.led.set_symbol("OFF");self.rx.reset()
                    self._next_tx_at=now+self.turnaround
                    if failed:self.protocol.tx_failed(failed,now,str(error))
            else:
                self.led.set_symbol("OFF")
            self._flush()
            if now-self._last_status>=1:
                state={"ready":ready,"role":self.role,"node_id":self.node_id,"vehicle":self.vehicle,
                       "state":self.protocol.state,"peer_id":self.protocol.peer_id,"session":self.protocol.session,
                       "tx_busy":self.tx.busy,"vision_ready":self.vision.ready,
                       "appearance_supported":self.led.capabilities,"rx_errors":self.rx.errors,
                       "operation_wait_bound":self.operation_wait_bound}
                self.status.publish(self.String(data=json.dumps(state)))
                self._last_status=now

    def _shutdown(self):
        with self.lock:
            self.tx.abort()
            try:self.led.set_symbol("OFF",force=True)
            except self.ros.ROSException:pass

def run():
    import rospy
    rospy.init_node("optical_comm")
    try:
        node=OpticalCommNode()
    except (ValueError,KeyError,TypeError) as error:
        rospy.logfatal("Invalid optical communication configuration: %s",error)
        raise
    rospy.spin()
