#!/usr/bin/env python3
"""Publish complete, latched strip settings; the simulator schedules blinking."""
import rospy
from dynamic_reconfigure.server import Server
from aquaflow_stonefish.cfg import LedStripsConfig
from stonefish_ros.msg import LightStripCommand


class LedStripController:
    def __init__(self):
        vehicle = rospy.get_param("~vehicle_name", "bricsbot")
        self.publishers = {
            side: rospy.Publisher("/{}/lights/{}/cmd".format(vehicle, side),
                                  LightStripCommand, queue_size=1, latch=True)
            for side in ("left", "right")
        }
        self.server = Server(LedStripsConfig, self.configure)

    def configure(self, config, _level):
        for side, publisher in self.publishers.items():
            publisher.publish(LightStripCommand(
                mode=int(config[side + "_mode"]),
                r=float(config[side + "_r"]),
                g=float(config[side + "_g"]),
                b=float(config[side + "_b"]),
                brightness=float(config[side + "_brightness"]),
                blink_hz=float(config[side + "_blink_hz"]),
                duty_cycle=float(config[side + "_duty_cycle"])))
        return config


if __name__ == "__main__":
    rospy.init_node("led_strip_controller")
    controller = LedStripController()
    rospy.spin()
