"""Regression inputs based on receiver statistics reported from the demo scene.

Images below are synthetic; these tests do not reproduce Stonefish rendering.
"""
from pathlib import Path
import unittest
import numpy as np
import yaml

from optical_comm.codecs import BlueGreen2BitCodec
from optical_comm.physical.link import Timing, Transmitter, Receiver
from optical_comm.protocol.frame import Frame, FrameCodec, Kind
from optical_comm.vision.color_brightness import ColorBrightnessClassifier

CONFIG = Path(__file__).resolve().parents[1] / "config/vision.yaml"


def scene_image(symbol):
    image = np.full((480, 640, 3), 10, dtype=np.uint8)
    pixels = image.reshape(-1, 3)
    # The dark scene still contains changed blue background pixels.
    pixels[:2660] = (100, 25, 5)
    states = {"BLUE_HIGH": (77000, (124, 25, 5)),
              "BLUE_LOW": (19000, (86, 20, 5)),
              "GREEN_HIGH": (140000, (10, 92, 5)),
              "GREEN_LOW": (14500, (5, 65, 2))}
    if symbol != "OFF":
        count, color = states[symbol]
        pixels[5000:5000+count] = color
    return image


def detector():
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["vision"]
    vision = ColorBrightnessClassifier(**config)
    startup = np.full((480, 640, 3), 10, dtype=np.uint8)
    for _ in range(config["background_frames"]):
        vision.classify(startup)
    return vision


class DemoSceneVisionTest(unittest.TestCase):
    def test_reported_idle_blue_background_does_not_count_as_data(self):
        observation = detector().classify(scene_image("OFF"))
        self.assertEqual(observation.blue_pixels, 2660)
        self.assertEqual(observation.symbol, "OFF")

    def test_blue_and_green_use_their_own_observed_brightness_ranges(self):
        vision = detector()
        for symbol in ("BLUE_HIGH", "BLUE_LOW", "GREEN_HIGH", "GREEN_LOW"):
            with self.subTest(symbol=symbol):
                self.assertEqual(vision.classify(scene_image(symbol)).symbol, symbol)

    def test_open_frame_recovers_with_idle_background_and_15_hz_images(self):
        codec = BlueGreen2BitCodec()
        frames = FrameCodec()
        timing = Timing()
        transmitter = Transmitter(codec, frames, timing)
        receiver = Receiver(codec, frames, timing)
        vision = detector()
        images = {symbol: scene_image(symbol) for symbol in ("OFF", "BLUE_HIGH", "BLUE_LOW", "GREEN_HIGH", "GREEN_LOW")}
        target = Frame(Kind.OPEN, 1, 0, "00011011" * 4, 1, 2)
        transmitter.start(target, 0.)
        recovered = []
        for tick in range(int((transmitter.duration(target) + 1) * 60)):
            now = tick / 60.
            symbol, _ = transmitter.step(now)
            if tick % 4:
                continue
            observation = vision.classify(images[symbol])
            frame = receiver.observe(now + 1234., observation.symbol, observation.confidence)
            if frame is not None:
                recovered.append(frame)
        self.assertEqual(recovered, [target])


if __name__ == "__main__":
    unittest.main()
