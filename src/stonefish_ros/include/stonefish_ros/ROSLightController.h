// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <Stonefish/StonefishCommon.h>
#include <ros/ros.h>
#include <stonefish_ros/LightStripCommand.h>
#include "stonefish_ros/LightStripState.h"
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace sf
{
class Light;

class ROSLightController
{
public:
    explicit ROSLightController(const ros::NodeHandle& node);
    bool RegisterLight(Light* light, const std::string& commandTopic,
                       Scalar maxPower, const LightStripState& initial);
    void Advance(Scalar timeStep);
    // Only called by the graphical app's ProcessInputs() on its rendering thread.
    void ApplyOnRenderThread();
    // Call after stopping the ROS spinner and before destroying engine entities.
    void Reset();

private:
    struct Lamp { Light* light; Scalar maxPower; };
    struct Group
    {
        LightStripState state;
        std::vector<Lamp> lamps;
        ros::Subscriber subscriber;
        ros::Publisher appearanceSupported;
    };
    void Receive(const stonefish_ros::LightStripCommandConstPtr& msg,
                 const std::string& topic);

    ros::NodeHandle node;
    std::mutex mutex;
    std::map<std::string, Group> groups;
    double elapsed = 0;
};
}
