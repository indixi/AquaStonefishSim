#include "stonefish_ros/LightStripState.h"
#include "stonefish_ros/LightBackend.h"
#include <cmath>
#include <limits>
#include <iostream>

struct TestColor { double r, g, b; };
struct NativeLight
{
    bool on = false;
    void Switch(bool value) { on = value; }
};
struct ExtendedLight : NativeLight
{
    double power = 0;
    TestColor color{0, 0, 0};
    void setLightProperties(const TestColor& rgb, double luminousPower, bool enabled)
    { color = rgb; power = luminousPower; on = enabled; }
};

// Keep checks and their side effects active in Release/NDEBUG builds.
#define CHECK(condition) do { if(!(condition)) { \
    std::cerr << "Check failed at line " << __LINE__ << ": " #condition "\n"; \
    return 1; } } while(false)

int main()
{
    using sf::LightStripState;
    LightStripState state;
    CHECK(state.valid() && state.isOn(0));
    state.mode = LightStripState::BLINK;
    state.blinkHz = 1;
    state.dutyCycle = .5;
    CHECK(state.isOn(0) && state.isOn(.49));
    CHECK(!state.isOn(.5) && !state.isOn(.99));
    CHECK(state.isOn(1) && !state.isOn(1.75));
    // Editing appearance preserves the shared simulation-time phase.
    state.brightness = .25;
    state.rgb = {{1, 0, 0}};
    CHECK(!state.isOn(.75) && state.isOn(1.25));
    state.dutyCycle = 0;
    CHECK(!state.isOn(0));
    state.dutyCycle = 1;
    CHECK(state.isOn(.75));
    state.brightness = 0;
    CHECK(!state.isOn(0));
    state.brightness = 1;
    state.mode = LightStripState::OFF;
    CHECK(!state.isOn(0));
    state.mode = LightStripState::BLINK;
    state.blinkHz = 0;
    CHECK(!state.valid());
    state.blinkHz = 1;
    state.rgb[0] = 1.1;
    CHECK(!state.valid());
    state.rgb[0] = std::numeric_limits<double>::quiet_NaN();
    CHECK(!state.valid());
    state.rgb[0] = 1;
    state.brightness = -1;
    CHECK(!state.valid());
    state.brightness = 1;
    state.dutyCycle = 1.1;
    CHECK(!state.valid());
    state.dutyCycle = .5;
    CHECK(!state.isOn(-1));
    CHECK(!state.isOn(std::numeric_limits<double>::infinity()));

    NativeLight native;
    ExtendedLight extended;
    TestColor red{1, 0, 0};
    static_assert(!sf::HasLightProperties<NativeLight, TestColor, double>::value);
    static_assert(sf::HasLightProperties<ExtendedLight, TestColor, double>::value);
    CHECK(!sf::ApplyLightProperties(native, red, 25.0, true));
    CHECK(native.on);
    sf::ApplyLightProperties(native, red, 0.0, false);
    CHECK(!native.on);
    CHECK(sf::ApplyLightProperties(extended, red, 25.0, true));
    CHECK(extended.on && extended.power == 25 && extended.color.r == 1);
    sf::ApplyLightProperties(extended, red, 50.0, true);
    CHECK(extended.power == 50); // Absolute power, never cumulative scaling.
    sf::ApplyLightProperties(extended, red, 50.0, false);
    CHECK(!extended.on);
    std::cout << "Light-strip state and stock/extended backend checks passed\n";
}
