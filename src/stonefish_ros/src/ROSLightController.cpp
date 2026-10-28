// SPDX-License-Identifier: GPL-3.0-or-later
#include "stonefish_ros/ROSLightController.h"
#include "stonefish_ros/LightBackend.h"
#include <Stonefish/actuators/Light.h>
#include <std_msgs/Bool.h>
#include <cmath>

namespace sf
{
ROSLightController::ROSLightController(const ros::NodeHandle& node) : node(node) {}

bool ROSLightController::RegisterLight(Light* light, const std::string& topic,
                                      Scalar maxPower, const LightStripState& initial)
{
    if(light == nullptr || topic.empty() || !std::isfinite(maxPower) ||
       maxPower < 0 || !initial.valid())
        return false;
    std::lock_guard<std::mutex> lock(mutex);
    auto result = groups.try_emplace(topic);
    Group& group = result.first->second;
    if(result.second)
    {
        group.state = initial;
        try
        {
            group.subscriber = node.subscribe<stonefish_ros::LightStripCommand>(
                topic, 1,
                [this, topic](const stonefish_ros::LightStripCommandConstPtr& msg)
                { Receive(msg, topic); });
            group.appearanceSupported = node.advertise<std_msgs::Bool>(
                topic + "/appearance_supported", 1, true);
        }
        catch(const ros::Exception& exception)
        {
            ROS_ERROR_STREAM("Cannot register light strip '" << topic << "': "
                             << exception.what());
            groups.erase(result.first);
            return false;
        }
        std_msgs::Bool capability;
        capability.data = HasLightProperties<Light, Color, Scalar>::value;
        group.appearanceSupported.publish(capability);
        if(!capability.data)
            ROS_WARN_STREAM("Light strip '" << topic
                << "': stock Stonefish backend. Off/steady/blink and brightness=0 work; "
                   "RGB and nonzero brightness scaling need the engine extension "
                   "documented in src/doc/2026-10-28-led-strip-control.md.");
    }
    for(const Lamp& lamp : group.lamps)
        if(lamp.light == light)
            return false;
    group.lamps.push_back({light, maxPower});
    return true;
}

void ROSLightController::Receive(
    const stonefish_ros::LightStripCommandConstPtr& msg, const std::string& topic)
{
    LightStripState state;
    state.mode = msg->mode;
    state.rgb = {{msg->r, msg->g, msg->b}};
    state.brightness = msg->brightness;
    state.blinkHz = msg->blink_hz;
    state.dutyCycle = msg->duty_cycle;
    if(!state.valid())
    {
        ROS_WARN_STREAM_THROTTLE(5.0, "Rejected invalid light-strip command on " << topic);
        return;
    }
    std::lock_guard<std::mutex> lock(mutex);
    const auto group = groups.find(topic);
    if(group != groups.end())
        group->second.state = state;
}

void ROSLightController::Advance(Scalar timeStep)
{
    if(!std::isfinite(timeStep) || timeStep <= 0)
        return;
    std::lock_guard<std::mutex> lock(mutex);
    elapsed += static_cast<double>(timeStep);
}

void ROSLightController::ApplyOnRenderThread()
{
    std::lock_guard<std::mutex> lock(mutex);
    for(auto& entry : groups)
    {
        const Group& group = entry.second;
        const LightStripState& state = group.state;
        const Color color = Color::RGB(state.rgb[0], state.rgb[1], state.rgb[2]);
        const bool on = state.isOn(elapsed);
        for(const Lamp& lamp : group.lamps)
            ApplyLightProperties(*lamp.light, color,
                                 lamp.maxPower * Scalar(state.brightness), on);
    }
}

void ROSLightController::Reset()
{
    std::lock_guard<std::mutex> lock(mutex);
    for(auto& entry : groups)
    {
        entry.second.subscriber.shutdown();
        entry.second.appearanceSupported.shutdown();
    }
    groups.clear();
    elapsed = 0;
}
}
