// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <type_traits>
#include <utility>

namespace sf
{
// The optional extension is documented in src/doc/2026-10-28-led-strip-control.md.
// Stock Stonefish must compile without any declaration of this method.
template<class Light, class Color, class Power, class = void>
struct HasLightProperties : std::false_type {};

template<class Light, class Color, class Power>
struct HasLightProperties<Light, Color, Power, std::void_t<decltype(
    std::declval<Light&>().setLightProperties(
        std::declval<const Color&>(), std::declval<Power>(), bool{}))>>
    : std::true_type {};

template<class Light, class Color, class Power>
bool ApplyLightProperties(Light& light, const Color& color, Power power, bool on)
{
    if constexpr(HasLightProperties<Light, Color, Power>::value)
    {
        light.setLightProperties(color, power, on);
        return true;
    }
    else
    {
        light.Switch(on);
        return false; // Appearance remains the one defined in the SCN.
    }
}
}
