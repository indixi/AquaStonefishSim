"""Whole-image BGR color/brightness changes; no object detector or fixed ROI."""
from dataclasses import dataclass
import math
import numpy as np

@dataclass(frozen=True)
class Observation:
    symbol: str
    confidence: float
    brightness: float = 0
    blue_pixels: int = 0
    green_pixels: int = 0

class ColorBrightnessClassifier:
    def __init__(self,background_frames=8,min_pixels=8,minimum_change=15,
                 minimum_value=40,high_threshold=170,threshold_margin=8,
                 color_ratio=1.3,minimum_saturation=.35,dominance=.7,
                 blue_high_threshold=None,green_high_threshold=None):
        if type(background_frames) is not int or type(min_pixels) is not int:
            raise ValueError("image sample counts must be integers")
        if background_frames<1 or min_pixels<1 or not 0<dominance<=1:
            raise ValueError("invalid image sampling configuration")
        if not minimum_value<high_threshold<=255 or threshold_margin<0 or minimum_change<0:
            raise ValueError("invalid brightness thresholds")
        if color_ratio<=1 or not 0<=minimum_saturation<=1:
            raise ValueError("invalid color thresholds")
        values=(minimum_change,minimum_value,high_threshold,threshold_margin,color_ratio,minimum_saturation,dominance)
        if any(not math.isfinite(v) for v in values):raise ValueError("non-finite vision setting")
        thresholds={"BLUE":high_threshold if blue_high_threshold is None else blue_high_threshold,
                    "GREEN":high_threshold if green_high_threshold is None else green_high_threshold}
        if any(not math.isfinite(v) or not minimum_value<v<=255 for v in thresholds.values()):
            raise ValueError("invalid per-color brightness threshold")
        self.high_thresholds=thresholds
        self.background_frames=background_frames;self.min_pixels=min_pixels
        self.minimum_change=minimum_change;self.minimum_value=minimum_value
        self.high_threshold=high_threshold;self.threshold_margin=threshold_margin
        self.color_ratio=color_ratio;self.minimum_saturation=minimum_saturation;self.dominance=dominance
        self._background=None;self._count=0

    @property
    def ready(self):
        return self._count>=self.background_frames

    def reset_background(self):
        self._background=None;self._count=0

    def classify(self,bgr):
        array=np.asarray(bgr)
        if array.ndim!=3 or array.shape[2]!=3 or not array.shape[0] or not array.shape[1] or array.dtype!=np.uint8:
            raise ValueError("expected nonempty uint8 BGR image")
        value=array.astype(np.float32)
        if self._background is not None and self._background.shape!=value.shape:
            self.reset_background()
        if not self.ready:
            self._count+=1
            if self._background is None:self._background=value.copy()
            else:self._background+=(value-self._background)/self._count
            return Observation("OFF",1) if self.ready else Observation("UNKNOWN",0)
        b,g,r=value[:,:,0],value[:,:,1],value[:,:,2]
        maximum=value.max(axis=2)
        saturation=(maximum-value.min(axis=2))/np.maximum(maximum,1)
        # Emissive blue/green can be dimmer than the unlit neutral mesh.
        # Detect color change in either direction, not just a positive V change.
        changed=np.abs(value-self._background).max(axis=2)
        candidate=(changed>=self.minimum_change)&(maximum>=self.minimum_value)&(saturation>=self.minimum_saturation)
        blue=candidate&(b>=self.color_ratio*g)&(b>=self.color_ratio*r)
        green=candidate&(g>=self.color_ratio*b)&(g>=self.color_ratio*r)
        nb,ng=int(blue.sum()),int(green.sum())
        if max(nb,ng)<self.min_pixels:
            return Observation("OFF",1,0,nb,ng)
        fraction=max(nb,ng)/max(1,nb+ng)
        if fraction<self.dominance:
            return Observation("UNKNOWN",0,0,nb,ng)
        mask=blue if nb>ng else green
        feature=float(np.median(maximum[mask]))
        color="BLUE" if nb>ng else "GREEN"
        threshold=self.high_thresholds[color]
        if abs(feature-threshold)<=self.threshold_margin:
            return Observation("UNKNOWN",0,feature,nb,ng)
        level="HIGH" if feature>threshold else "LOW"
        return Observation(color+"_"+level,fraction,feature,nb,ng)
