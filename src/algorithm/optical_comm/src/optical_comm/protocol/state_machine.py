"""Leader-owned half-duplex sessions. No ROS, camera or LED dependencies."""
from collections import deque
import secrets
from dataclasses import dataclass
from optical_comm.codecs.base import validate_bits
from .frame import Frame, Kind

@dataclass(frozen=True)
class ProtocolConfig:
    ack_timeout: float = 12.0
    read_timeout: float = 90.0
    app_timeout: float = 15.0
    max_retries: int = 2
    session_timeout: float = 300.0
    closed_cache_time: float = 300.0
    max_payload_bits: int = 256

    def __post_init__(self):
        import math
        durations=(self.ack_timeout,self.read_timeout,self.app_timeout,self.session_timeout,self.closed_cache_time)
        if any(not math.isfinite(x) or x<=0 for x in durations):
            raise ValueError("timeouts must be finite and positive")
        if type(self.max_retries) is not int or type(self.max_payload_bits) is not int:
            raise ValueError("retry and payload limits must be integers")
        if self.max_retries<0 or not 0<=self.max_payload_bits<=4095:
            raise ValueError("invalid retry/payload limit")

@dataclass(frozen=True)
class Event:
    kind: str
    request_id: str = ""
    peer_id: int = 0
    bits: str = ""
    detail: str = ""

@dataclass
class Pending:
    frame: Frame
    request_id: str
    retries: int = 0
    deadline: float = None
    accepted: bool = False

class Protocol:
    def __init__(self,role,node_id,leader_id=1,config=None,peers=None):
        if role not in ("leader","follower") or not 1<=node_id<=15 or not 1<=leader_id<=15:
            raise ValueError("invalid role/address")
        if (role=="leader") != (node_id==leader_id):
            raise ValueError("leader role and configured leader address disagree")
        self.role,self.node_id,self.leader_id=role,node_id,leader_id
        self.config=config or ProtocolConfig()
        self.peers=None if peers is None else frozenset(peers)
        self._generation=secrets.randbits(32) if role=="leader" else 0
        self._peer_generation=None
        self.connected=False
        self.peer_id=0
        self.session=0
        self.pending=None
        self._next_seq=1
        self._session_counter=0
        self._tx=deque();self._events=deque()
        self._cache={};self._received={}
        self._waiting=None
        self._closed={}
        self._last_activity=None

    @property
    def state(self):
        if self.pending:
            return "WAIT_"+self.pending.frame.kind.name
        if self._waiting:
            return "WAIT_APPLICATION"
        return "ESTABLISHED" if self.connected else "IDLE"

    def drain_tx(self):
        result=list(self._tx);self._tx.clear();return result

    def pop_tx(self):
        return self._tx.popleft() if self._tx else None

    def drain_events(self):
        result=list(self._events);self._events.clear();return result

    def _event(self,kind,request_id="",bits="",detail="",peer=None):
        self._events.append(Event(kind,request_id,self.peer_id if peer is None else peer,bits,detail))

    def _bits(self,bits):
        validate_bits(bits)
        if len(bits)>self.config.max_payload_bits:
            raise ValueError("payload exceeds configured maximum")

    def submit(self,operation,peer_id=0,bits="",request_id="",now=0):
        operation=operation.upper()
        if self.role!="leader":
            raise ValueError("followers transmit only when polled; use PROVIDE for a pending read")
        if self.pending:
            raise ValueError("an operation is already pending")
        self._bits(bits)
        if operation=="OPEN":
            if self.connected or self.session:
                raise ValueError("END the current session before switching peers")
            if not 1<=peer_id<=15 or peer_id==self.node_id or (self.peers is not None and peer_id not in self.peers):
                raise ValueError("invalid target")
            if bits:
                raise ValueError("OPEN carries no application data")
            self._session_counter=self._session_counter%255+1
            self.session=self._session_counter;self.peer_id=peer_id
            self._cache.clear();self._received.clear();self._next_seq=1
            frame=Frame(Kind.OPEN,self.session,0,format(self._generation,"032b"),self.node_id,peer_id)
        else:
            if not self.connected or peer_id not in (0,self.peer_id):
                raise ValueError("no session with requested target")
            if operation not in ("WRITE","READ","END"):
                raise ValueError("unsupported operation")
            if operation=="END":
                if bits: raise ValueError("END carries no application data")
                seq=0
            else:
                if operation=="WRITE" and not bits:
                    raise ValueError("WRITE requires nonempty application bits")
                if self._next_seq>255:
                    raise ValueError("sequence space exhausted; END and reopen")
                seq=self._next_seq;self._next_seq+=1
            frame=Frame(Kind[operation],self.session,seq,bits)
        self._last_activity=now
        self._wait(frame,request_id)

    def _wait(self,frame,request_id):
        self.pending=Pending(frame,request_id)
        self._tx.append(frame)

    def tx_done(self,frame,now):
        self._last_activity=now
        if self.pending and self.pending.frame==frame:
            timeout=self.config.read_timeout if frame.kind==Kind.READ else self.config.ack_timeout
            self.pending.deadline=now+timeout

    def tx_failed(self,frame,now,detail):
        self._event("TX_FAILED",detail=detail)
        if self.pending and self.pending.frame==frame:
            self.pending.deadline=now

    def abort_session(self,detail):
        if self.pending:
            self._event("FAILED",self.pending.request_id,detail=detail)
        if self.connected:
            self._event("SESSION_LOST",detail=detail)
        self._reset()

    def _clear_pending(self):
        if self.pending:
            frame=self.pending.frame
            self._tx=deque(x for x in self._tx if x!=frame)
        self.pending=None

    def _reset(self):
        self._clear_pending()
        self._tx.clear();self._cache.clear();self._received.clear()
        self._waiting=None;self.connected=False;self.peer_id=0;self.session=0
        self._peer_generation=None

    def _fail(self,detail):
        pending=self.pending
        if not pending:return
        self._event("FAILED",pending.request_id,detail=detail)
        opening=pending.frame.kind==Kind.OPEN
        self._clear_pending()
        if opening:self._reset()

    def receive(self,frame,now):
        if frame.kind==Kind.OPEN:
            self._open_received(frame,now)
            return
        if self.role=="follower" and frame.kind==Kind.END and frame.session in self._closed:
            until,ack=self._closed[frame.session]
            if now<=until:
                self._tx.append(ack)
                return
        if not self.session or frame.session!=self.session:
            return
        self._last_activity=now
        if frame.kind==Kind.ACK:
            self._ack_received(frame,now)
        elif frame.kind==Kind.ERROR and self.pending and frame.seq==self.pending.frame.seq:
            self._fail("peer error: "+frame.bits)
        elif self.role=="follower" and self.connected:
            self._follower_received(frame,now)
        elif self.role=="leader" and self.connected and frame.kind==Kind.DATA:
            self._data_received(frame)

    def _open_received(self,frame,now):
        if self.role!="follower" or frame.target!=self.node_id or frame.source!=self.leader_id:
            return
        if frame.seq!=0 or len(frame.bits)!=32:
            return
        if self.connected:
            if frame.session==self.session and frame.bits==self._peer_generation:
                self._tx.append(Frame.ack(frame))
            else:
                self._tx.append(Frame(Kind.ERROR,frame.session,frame.seq,"00000001"))
            return
        self._closed.pop(frame.session,None)
        self.session=frame.session;self.peer_id=frame.source;self.connected=True
        self._peer_generation=frame.bits
        self._cache.clear();self._received.clear();self._last_activity=now
        self._tx.append(Frame.ack(frame))
        self._event("SESSION_OPENED")

    def _ack_received(self,frame,now):
        pending=self.pending
        if not pending or frame.seq!=pending.frame.seq:
            return
        try:
            if frame.ack_kind!=pending.frame.kind:
                return
        except ValueError:return
        kind=pending.frame.kind
        if kind==Kind.READ:
            pending.accepted=True;pending.deadline=now+self.config.read_timeout
            return
        request_id=pending.request_id
        self._clear_pending()
        if kind==Kind.OPEN:
            self.connected=True;self._event("SESSION_OPENED",request_id)
        elif kind==Kind.WRITE:
            self._event("WRITE_CONFIRMED",request_id)
        elif kind==Kind.DATA:
            self._event("REPLY_CONFIRMED",request_id)
        elif kind==Kind.END:
            self._event("SESSION_ENDED",request_id)
            self._reset()

    def _follower_received(self,frame,now):
        key=(frame.kind,frame.seq)
        if frame.kind==Kind.END:
            if frame.seq!=0 or frame.bits:return
            ack=Frame.ack(frame)
            self._closed[frame.session]=(now+self.config.closed_cache_time,ack)
            self._event("SESSION_ENDED")
            self._reset();self._tx.append(ack)
            return
        if frame.kind not in (Kind.WRITE,Kind.READ) or frame.seq==0:
            return
        if key in self._cache:
            previous,replies=self._cache[key]
            if previous.bits!=frame.bits:
                self._tx.append(Frame(Kind.ERROR,frame.session,frame.seq,"00000010"))
                return
            for reply in replies:
                if reply not in self._tx:self._tx.append(reply)
            if frame.kind==Kind.READ:
                response=next((reply for reply in replies if reply.kind==Kind.DATA),None)
                if response is not None:
                    token=str(frame.session)+":"+str(frame.seq)
                    self.pending=Pending(response,token)
            return
        # Sequence numbers are shared by READ and WRITE within one session.
        if any(seq==frame.seq for (_,seq) in self._cache):
            self._tx.append(Frame(Kind.ERROR,frame.session,frame.seq,"00000010"))
            return
        if self.pending and self.pending.frame.kind==Kind.DATA and frame.seq!=self.pending.frame.seq:
            self._event("REPLY_UNCONFIRMED",self.pending.request_id,detail="leader advanced to a new operation")
            self._clear_pending()
        if self.pending or self._waiting:
            self._tx.append(Frame(Kind.ERROR,frame.session,frame.seq,"00000001"))
            return
        ack=Frame.ack(frame)
        self._cache[key]=(frame,[ack]);self._tx.append(ack)
        if frame.kind==Kind.WRITE:
            self._event("DATA_RECEIVED",bits=frame.bits)
        else:
            token=str(frame.session)+":"+str(frame.seq)
            self._waiting=(token,frame,now+self.config.app_timeout)
            self._event("DATA_REQUEST",token,frame.bits)

    def provide_bits(self,token,bits,now):
        if self.role!="follower" or not self._waiting or token!=self._waiting[0]:
            raise ValueError("no matching optical READ request")
        self._bits(bits)
        _,request,_=self._waiting
        self._waiting=None
        response=Frame(Kind.DATA,self.session,request.seq,bits)
        self._cache[(Kind.READ,request.seq)][1].append(response)
        self._last_activity=now
        self._wait(response,token)

    def _data_received(self,frame):
        key=(frame.session,frame.seq)
        if key in self._received:
            if self._received[key]==frame.bits:
                self._tx.append(Frame.ack(frame))
            return
        pending=self.pending
        if not pending or pending.frame.kind!=Kind.READ or pending.frame.seq!=frame.seq:
            return
        request_id=pending.request_id
        self._received[key]=frame.bits
        self._clear_pending();self._tx.append(Frame.ack(frame))
        self._event("READ_COMPLETED",request_id,frame.bits)

    def tick(self,now):
        self._closed={sid:value for sid,value in self._closed.items() if now<=value[0]}
        if self._waiting and now>=self._waiting[2]:
            token,request,_=self._waiting;self._waiting=None
            error=Frame(Kind.ERROR,self.session,request.seq,"00000011")
            self._cache[(Kind.READ,request.seq)][1].append(error)
            self._tx.append(error);self._event("FAILED",token,detail="application response timeout")
        pending=self.pending
        if pending and pending.deadline is not None and now>=pending.deadline:
            if self.role=="follower" and pending.frame.kind==Kind.DATA:
                # Only another leader READ grants another optical DATA transmission.
                # Retain the cached reply without contending with leader retries.
                self._event("REPLY_UNCONFIRMED",pending.request_id,detail="waiting for leader retry grant")
                self._clear_pending()
            elif pending.retries>=self.config.max_retries:
                self._fail("retry limit reached")
            else:
                pending.retries+=1;pending.deadline=None
                if pending.frame not in self._tx:self._tx.append(pending.frame)
                self._event("RETRY",pending.request_id,detail=pending.frame.kind.name)
        if self.connected and not self.pending and not self._waiting and self._last_activity is not None:
            if now-self._last_activity>=self.config.session_timeout:
                self._event("SESSION_EXPIRED")
                self._reset()
