"""Exercise our parameter-to-message boundary without a ROS installation."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class Message:
    def __init__(self, **values):
        self.__dict__.update(values)


class Publisher:
    def __init__(self, topic, message_type, **options):
        self.topic, self.options, self.messages = topic, options, []

    def publish(self, message):
        self.messages.append(message)


def module(name, **values):
    result = types.ModuleType(name)
    result.__dict__.update(values)
    return result


class ControllerTest(unittest.TestCase):
    def test_independent_left_right_payloads_are_latched(self):
        # A shared message object or crossed parameter prefix corrupts a side.
        modules = {
            'rospy': module('rospy', Publisher=Publisher,
                            get_param=lambda name, default: default),
            'dynamic_reconfigure': module('dynamic_reconfigure'),
            'dynamic_reconfigure.server': module('dynamic_reconfigure.server',
                                                 Server=lambda *args: None),
            'aquaflow_stonefish': module('aquaflow_stonefish'),
            'aquaflow_stonefish.cfg': module('aquaflow_stonefish.cfg', LedStripsConfig=object),
            'stonefish_ros': module('stonefish_ros'),
            'stonefish_ros.msg': module('stonefish_ros.msg', LightStripCommand=Message),
        }
        path = Path(__file__).parents[1] / 'scripts/led_strip_controller.py'
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location('led_strip_controller', path)
            script = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(script)
            node = script.LedStripController()
            config = dict(left_mode=2, left_r=1, left_g=0, left_b=0,
                          left_brightness=.25, left_blink_hz=2, left_duty_cycle=.3,
                          right_mode=1, right_r=0, right_g=0, right_b=1,
                          right_brightness=.75, right_blink_hz=1, right_duty_cycle=.5)
            self.assertIs(node.configure(config, 0), config)
            left, right = node.publishers['left'], node.publishers['right']
            self.assertEqual(left.topic, '/bricsbot/lights/left/cmd')
            self.assertEqual(right.topic, '/bricsbot/lights/right/cmd')
            self.assertTrue(left.options['latch'] and right.options['latch'])
            self.assertEqual(left.messages[0].__dict__,
                             dict(mode=2, r=1., g=0., b=0., brightness=.25,
                                  blink_hz=2., duty_cycle=.3))
            self.assertEqual(right.messages[0].__dict__,
                             dict(mode=1, r=0., g=0., b=1., brightness=.75,
                                  blink_hz=1., duty_cycle=.5))
            config['left_r'] = .4
            node.configure(config, 0)
            self.assertEqual(left.messages[0].r, 1.)
            self.assertEqual(left.messages[1].r, .4)
            self.assertEqual(right.messages[1].b, 1.)


if __name__ == '__main__':
    unittest.main()
