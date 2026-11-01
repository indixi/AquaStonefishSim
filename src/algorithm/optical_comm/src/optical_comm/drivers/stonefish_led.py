"""Only this adapter knows the Stonefish ROS light message."""
import math

def validate_profile(codec,profile):
    states={}
    for symbol in codec.data_symbols|{codec.sync_symbol}:
        entry=profile.get(symbol,{})
        rgb=tuple(entry.get("rgb",()))
        power=entry.get("brightness",0)
        if len(rgb)!=3 or any(not math.isfinite(v) or not 0<=v<=1 for v in rgb):
            raise ValueError("invalid RGB for "+symbol)
        if not math.isfinite(power) or not 0<power<=1:
            raise ValueError("data brightness must be in (0,1] for "+symbol)
        states[symbol]=(rgb,float(power))
    return states

class LedDriver:
    def __init__(self,vehicle,codec,profile):
        import rospy
        from std_msgs.msg import Bool
        from stonefish_ros.msg import LightStripCommand
        self.rospy=rospy;self.message=LightStripCommand
        self.states=validate_profile(codec,profile)
        self.capabilities={"left":False,"right":False}
        self.publishers={side:rospy.Publisher("/"+vehicle+"/lights/"+side+"/cmd",LightStripCommand,
                                             queue_size=1,latch=True) for side in self.capabilities}
        self.subscribers={side:rospy.Subscriber("/"+vehicle+"/lights/"+side+"/cmd/appearance_supported",
                                               Bool,self._capability,callback_args=side,queue_size=1)
                          for side in self.capabilities}
        self._last=None
        self.set_symbol("OFF",force=True)

    def _capability(self,message,side):
        self.capabilities[side]=bool(message.data)

    @property
    def ready(self):
        return all(self.capabilities.values()) and all(s.get_num_connections()>0 for s in self.subscribers.values())

    def set_symbol(self,symbol,force=False):
        if symbol==self._last and not force:return
        if symbol=="OFF":
            rgb,power=(0.,0.,0.),0.
        else:
            rgb,power=self.states[symbol]
        command=self.message(mode=0 if symbol=="OFF" else 1,r=rgb[0],g=rgb[1],b=rgb[2],
                             brightness=power,blink_hz=1.,duty_cycle=.5)
        for publisher in self.publishers.values():publisher.publish(command)
        self._last=symbol
