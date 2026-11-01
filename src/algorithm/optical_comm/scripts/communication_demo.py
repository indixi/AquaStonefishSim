#!/usr/bin/env python3
"""Example upper-layer application. The communication component has no fixed payload."""
import argparse
import json
import threading
import time
import uuid

def main():
    import rospy
    from std_msgs.msg import String
    from optical_comm.msg import CommRequest,CommEvent
    parser=argparse.ArgumentParser()
    parser.add_argument("--role",choices=("leader","follower"),required=True)
    parser.add_argument("--vehicle",required=True)
    parser.add_argument("--peers",default="2,3")
    parser.add_argument("--payload",default="00011011")
    parser.add_argument("--reply",default="1010101010")
    parser.add_argument("--timeout",type=float,default=None)
    args=parser.parse_args(rospy.myargv()[1:])
    if args.timeout is not None and args.timeout<=0:parser.error("timeout must be positive")
    for bits in (args.payload,args.reply):
        if any(c not in "01" for c in bits):parser.error("payload/reply must contain only 0 and 1")
    rospy.init_node("optical_comm_business",anonymous=True)
    topic="/"+args.vehicle+"/optical_comm"
    publisher=rospy.Publisher(topic+"/request",CommRequest,queue_size=10)
    condition=threading.Condition();results={};state={"ready":False}
    def on_state(message):
        with condition:
            state.update(json.loads(message.data));condition.notify_all()
    def on_event(event):
        rospy.loginfo("%s: %s peer=%d bits=%s detail=%s",args.vehicle,event.kind,event.peer_id,event.bits,event.detail)
        if args.role=="follower" and event.kind=="DATA_REQUEST":
            publisher.publish(CommRequest(operation=CommRequest.PROVIDE,peer_id=event.peer_id,
                                          bits=args.reply,request_id=event.request_id))
        if event.request_id and event.kind in ("SESSION_OPENED","WRITE_CONFIRMED","READ_COMPLETED","SESSION_ENDED","FAILED","REJECTED"):
            with condition:
                results[event.request_id]=event;condition.notify_all()
    subscribers=[rospy.Subscriber(topic+"/state",String,on_state,queue_size=1),
                 rospy.Subscriber(topic+"/event",CommEvent,on_event,queue_size=100)]
    if args.role=="follower":
        rospy.spin();return
    def command(operation,peer,bits=""):
        token=uuid.uuid4().hex[:12]
        publisher.publish(CommRequest(operation=operation,peer_id=peer,bits=bits,request_id=token))
        wait=args.timeout if args.timeout is not None else max(30.,float(state.get("operation_wait_bound",600)))
        deadline=time.monotonic()+wait
        with condition:
            while token not in results and not rospy.is_shutdown():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise RuntimeError("upper-layer wait timed out; session was not switched")
                condition.wait(min(remaining,.5))
            if rospy.is_shutdown():raise RuntimeError("ROS shutdown")
            event=results.pop(token)
        if event.kind in ("FAILED","REJECTED"):raise RuntimeError(event.detail)
        return event
    deadline=time.monotonic()+(args.timeout if args.timeout is not None else 120)
    with condition:
        while not state.get("ready") or publisher.get_num_connections()==0:
            if rospy.is_shutdown():return
            if time.monotonic()>deadline:raise RuntimeError("optical component did not become ready")
            condition.wait(.5)
    for peer in [int(value) for value in args.peers.split(",")]:
        command(CommRequest.OPEN,peer)
        command(CommRequest.WRITE,peer,args.payload)
        response=command(CommRequest.READ,peer,"")
        rospy.loginfo("Verified reply from %d: %s",peer,response.bits)
        command(CommRequest.END,peer)
    rospy.loginfo("All requested optical sessions completed")

if __name__=="__main__":
    main()
