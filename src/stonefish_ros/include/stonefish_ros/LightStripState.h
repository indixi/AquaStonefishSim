// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <array>
#include <cmath>
#include <cstdint>

namespace sf
{
// Independent of ROS and graphics, so timing and validation can be tested alone.
struct LightStripState
{
    enum Mode : std::uint8_t { OFF = 0, STEADY = 1, BLINK = 2 };
    std::uint8_t mode = STEADY;
    std::array<double, 3> rgb{{1, 1, 1}};
    double brightness = 1;
    double blinkHz = 1;
    double dutyCycle = .5;

    bool valid() const
    {
        if(mode > BLINK || !std::isfinite(brightness) ||
           brightness < 0 || brightness > 1 || !std::isfinite(blinkHz) ||
           blinkHz < 0 || (mode == BLINK && blinkHz == 0) ||
           !std::isfinite(dutyCycle) || dutyCycle < 0 || dutyCycle > 1)
            return false;
        for(double value : rgb)
            if(!std::isfinite(value) || value < 0 || value > 1)
                return false;
        return true;
    }

    bool isOn(double simulationTime) const
    {
        if(!valid() || !std::isfinite(simulationTime) || simulationTime < 0 ||
           mode == OFF || brightness == 0)
            return false;
        if(mode == STEADY)
            return true;
        // Modulo the time first to avoid overflow in time * frequency.
        const double period = 1 / blinkHz;
        return std::fmod(simulationTime, period) < dutyCycle * period;
    }
};
}
