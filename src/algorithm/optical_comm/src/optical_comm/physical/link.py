"""Timed light waveform and relative-time recovery from observed symbols."""
from collections import Counter,deque
from dataclasses import dataclass
import math
from optical_comm.codecs.base import OFF,UNKNOWN
from optical_comm.protocol.frame import FrameError

@dataclass(frozen=True)
class Timing:
    period: float = .4
    guard_symbols: int = 2
    min_samples: int = 2
    vote_fraction: float = .65
    edge_margin: float = .2
    confidence: float = .6

    def __post_init__(self):
        if type(self.guard_symbols) is not int or type(self.min_samples) is not int:
            raise ValueError("guard_symbols and min_samples must be integers")
        if not math.isfinite(self.period) or self.period<=0 or self.guard_symbols<1 or self.min_samples<1:
            raise ValueError("invalid symbol timing")
        if not .5<self.vote_fraction<=1 or not 0<self.edge_margin<.45 or not 0<=self.confidence<=1:
            raise ValueError("invalid sampling window")

class Transmitter:
    def __init__(self,codec,frames,timing):
        self.codec,self.frames,self.timing=codec,frames,timing
        self.busy=False;self._frame=None;self._last_time=None

    def duration(self,frame):
        count=len(self.codec.encode(self.frames.encode(frame)))
        return (2*self.timing.guard_symbols+6+count)*self.timing.period

    def start(self,frame,now):
        if self.busy:raise ValueError("transmitter is busy")
        data=self.codec.encode(self.frames.encode(frame))
        self._states=(OFF,)*self.timing.guard_symbols+(self.codec.sync_symbol,OFF)*3+data+(OFF,)*self.timing.guard_symbols
        self._frame=frame;self._start=now;self._last_time=None;self.busy=True

    def step(self,now):
        if not self.busy:return OFF,None
        if now<self._start:return OFF,None
        reference=self._start if self._last_time is None else self._last_time
        if now-reference>self.timing.period*.75:
            self.busy=False;self._frame=None
            raise RuntimeError("scheduler missed a symbol deadline")
        self._last_time=now
        index=int((now-self._start)/self.timing.period)
        if index>=len(self._states):
            frame=self._frame;self.busy=False;self._frame=None
            return OFF,frame
        return self._states[index],None

    def abort(self):
        self.busy=False;self._frame=None

class Receiver:
    def __init__(self,codec,frames,timing):
        self.codec,self.frames,self.timing=codec,frames,timing
        self.errors=0;self.last_error=""
        self.reset()

    def reset(self):
        self.history=deque();self.candidates=[]
        self.body_start=None;self.index=0;self.bits="";self.expected=None
        self._last_symbol=None;self._last_time=None

    def _vote(self,start,end,allowed):
        samples=[(symbol,confidence) for t,symbol,confidence in self.history if start<=t<=end]
        valid=[symbol for symbol,confidence in samples if symbol in allowed and confidence>=self.timing.confidence]
        if len(valid)<self.timing.min_samples:return None
        symbol,count=Counter(valid).most_common(1)[0]
        if count/max(1,len(samples))<self.timing.vote_fraction:return None
        return symbol

    def _error(self,detail):
        self.errors+=1;self.last_error=detail;self.reset()

    def observe(self,now,symbol,confidence=1.0):
        if not math.isfinite(now) or not math.isfinite(confidence):
            return None
        if self.history and now<self.history[-1][0]:
            self._error("observation time moved backwards")
        self.history.append((now,symbol,confidence))
        period=self.timing.period
        if self.body_start is None:
            if confidence>=self.timing.confidence and symbol!=UNKNOWN:
                if symbol==self.codec.sync_symbol and self._last_symbol==OFF:
                    self.candidates.append((now+self._last_time)*.5)
                self._last_symbol=symbol;self._last_time=now
            for anchor in list(self.candidates):
                if now<anchor+5.85*period:continue
                expected=(self.codec.sync_symbol,OFF)*3
                good=all(self._vote(anchor+(i+self.timing.edge_margin)*period,
                                    anchor+(i+1-self.timing.edge_margin)*period,
                                    {OFF,self.codec.sync_symbol})==state
                         for i,state in enumerate(expected))
                self.candidates.remove(anchor)
                if good:
                    self.body_start=anchor+6*period;self.candidates=[]
                    break
            if self.body_start is None:
                cutoff=now-8*period
                while self.history and self.history[0][0]<cutoff:self.history.popleft()
                return None
        while now>=self.body_start+(self.index+1-self.timing.edge_margin)*period:
            start=self.body_start+(self.index+self.timing.edge_margin)*period
            end=self.body_start+(self.index+1-self.timing.edge_margin)*period
            picked=self._vote(start,end,self.codec.data_symbols)
            if picked is None:
                self._error("unreliable symbol window");return None
            self.bits+=self.codec.decode((picked,));self.index+=1
            try:
                self.expected=self.frames.expected_bits(self.bits)
                if self.expected is not None and len(self.bits)>=self.expected:
                    if any(c!="0" for c in self.bits[self.expected:]):
                        raise FrameError("nonzero symbol padding")
                    frame=self.frames.decode(self.bits[:self.expected])
                    self.reset();return frame
            except ValueError as error:
                self._error(str(error));return None
            cutoff=self.body_start+(self.index-.1)*period
            while self.history and self.history[0][0]<cutoff:self.history.popleft()
        return None
