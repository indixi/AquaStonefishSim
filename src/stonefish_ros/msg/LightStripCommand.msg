# One complete configuration for all lights registered on a strip topic.
uint8 OFF=0
uint8 STEADY=1
uint8 BLINK=2
uint8 mode
float32 r
float32 g
float32 b
# Scale the per-light maximum luminous power loaded from the SCN.
float32 brightness
# Full on/off cycles per simulated second; must be > 0 in BLINK mode.
float32 blink_hz
# Fraction of each cycle spent on, in [0,1].
float32 duty_cycle
