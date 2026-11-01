"""Pure validation shared by the ROS adapter and configuration tests."""
from .protocol.frame import Frame,Kind
from .protocol.state_machine import ProtocolConfig
from .physical.link import Transmitter

def derive_protocol_config(codec,frames,timing,turnaround,settings):
    cfg=dict(settings)
    tx=Transmitter(codec,frames,timing)
    margin=max(1.,2*timing.period)
    minimum_ack=tx.duration(Frame(Kind.ACK,1,1,"011"))+turnaround+margin
    longest=tx.duration(Frame(Kind.DATA,1,1,"0"*frames.max_payload_bits))
    minimum_read=minimum_ack+float(cfg.get("app_timeout",15))+longest+2*turnaround+margin
    for key,minimum in (("ack_timeout",minimum_ack),("read_timeout",minimum_read)):
        configured=float(cfg.get(key,0))
        if configured==0:cfg[key]=minimum
        elif configured<minimum:raise ValueError(key+" is too short; minimum "+str(round(minimum,2)))
    result=ProtocolConfig(**cfg)
    if result.session_timeout<=longest+turnaround+margin:
        raise ValueError("session_timeout must exceed the longest optical frame")
    close_bound=(result.max_retries+1)*(result.ack_timeout+tx.duration(Frame(Kind.END,1,0))+turnaround)
    if result.closed_cache_time<close_bound:
        raise ValueError("closed_cache_time must cover all END retries")
    return result
