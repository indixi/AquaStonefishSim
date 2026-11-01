import unittest
import numpy as np
from optical_comm.vision.color_brightness import ColorBrightnessClassifier

class VisionTest(unittest.TestCase):
    def test_fixed_background_is_not_decoded_as_blue_data(self):
        background=np.full((20,20,3),(120,60,20),dtype=np.uint8)
        detector=ColorBrightnessClassifier(background_frames=2,min_pixels=4)
        detector.classify(background);detector.classify(background)
        self.assertTrue(detector.ready)
        self.assertEqual(detector.classify(background).symbol,"OFF")
        for pixel,want in [((245,50,5),"BLUE_HIGH"),((95,20,2),"BLUE_LOW"),
                           ((20,245,5),"GREEN_HIGH"),((8,95,2),"GREEN_LOW")]:
            # Independent dark background for the four emitted states.
            d=ColorBrightnessClassifier(background_frames=1,min_pixels=4)
            dark=np.full((20,20,3),10,dtype=np.uint8);d.classify(dark)
            sample=dark.copy();sample[4:10,4:10]=pixel
            self.assertEqual(d.classify(sample).symbol,want)

    def test_competing_colors_and_bad_images_are_rejected(self):
        d=ColorBrightnessClassifier(background_frames=1,min_pixels=4)
        image=np.full((20,20,3),10,dtype=np.uint8);d.classify(image)
        image[1:5,1:5]=(245,20,0);image[10:14,10:14]=(0,245,20)
        self.assertEqual(d.classify(image).symbol,"UNKNOWN")
        with self.assertRaises(ValueError):d.classify(np.zeros((4,4),dtype=np.uint8))

    def test_dim_colored_emission_can_replace_brighter_neutral_background(self):
        detector=ColorBrightnessClassifier(background_frames=1,min_pixels=4)
        background=np.full((20,20,3),180,dtype=np.uint8)
        detector.classify(background)
        sample=background.copy();sample[4:10,4:10]=(95,22,2)
        self.assertEqual(detector.classify(sample).symbol,"BLUE_LOW")

    def test_color_specific_threshold_leaves_other_color_on_legacy_fallback(self):
        detector=ColorBrightnessClassifier(background_frames=1,min_pixels=4,green_high_threshold=80)
        background=np.full((20,20,3),10,dtype=np.uint8)
        detector.classify(background)
        for pixel,want in (((124,25,5),"BLUE_LOW"),((10,92,5),"GREEN_HIGH"),((5,65,2),"GREEN_LOW")):
            sample=background.copy();sample[4:10,4:10]=pixel
            self.assertEqual(detector.classify(sample).symbol,want)

    def test_invalid_color_thresholds_are_rejected(self):
        for name in ("blue_high_threshold","green_high_threshold"):
            for value in (float("nan"),float("inf"),0,40,256):
                with self.subTest(name=name,value=value):
                    with self.assertRaises(ValueError):
                        ColorBrightnessClassifier(**{name:value})

if __name__=="__main__":unittest.main()
