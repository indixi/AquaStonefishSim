# 灯带控制与 model 资源迁移（2026-10-28）

## 本次范围与能力边界

本次修改 ROS 工程，**没有修改、下载替换或安装 Stonefish 引擎源码**。保留用户当前的八个原生灯珠、位置、半径、颜色及每灯 `illuminance=100.0`；模型资源按用户新目录组织。未改 PID、推力分配算法、质量或浮力配置。

| 环境 | 开关/常亮/闪烁 | RGB 变化 | 非零亮度比例 |
|---|---|---|---|
| 原版 Stonefish 1.6 | 接入原生 `Light::Switch(bool)` | 保持 SCN 初始颜色 | 保持 SCN 初始发光量；比例为 0 可关闭 |
| 完成本文件约定的引擎补丁，并重编 ROS | 支持 | 支持 | 支持 |

“原版可闪烁”指接口和调度已经接通；当前编辑电脑不是 ROS/Stonefish 运行环境，仍须在仿真电脑上完成本文的画面验收。面板上 RGB 和亮度字段可操作，并不表示未打补丁的库已经支持它们。原版后端启动时会输出能力警告，并发布锁存的能力标志。

## 工作区决定与实施记录

用户要求修改当前工程并将说明放在 `src/doc/`，因此直接在当前工作目录实施，保留已有的资源迁移。未创建额外工作树，未提交或推送。

- [x] 同步启动、SCN、URDF 与安装路径。
- [x] 实现消息、分组控制器及原版/扩展库兼容接口。
- [x] 实现参数面板、独立启动入口和主 launch 集成。
- [x] 记录引擎补丁位置、接口、构建及验收方式。
- [ ] 完成目标 Linux ROS 环境的 catkin 构建与 Stonefish 画面验收。

接口决定：使用新增的 `setLightProperties(const sf::Color&, sf::Scalar luminousPower, bool enabled)`。C++17 编译期检测原版库有没有这个方法，没有则编译到原生开关分支；不会直接引用不存在的符号。引擎打补丁之后必须重编译 `stonefish_ros`，检测分支才会改变。

线程决定：ROS 回调只缓存参数；物理回调仅累计仿真步长；ROS 自己的 `GraphicalSimulationApp` 子类在 `ProcessInputs()` 中统一应用灯光。该方法在每帧渲染之前执行，调用开关或颜色 setter 的是渲染线程。新增类位于 `stonefish_ros/src/parsed_simulator.cpp`，不是引擎修改。

## 资源目录与路径迁移

资源根目录由 `$(find aquaflow_stonefish)/data` 改成 `$(find aquaflow_stonefish)/model`：

- `model/robot/bricsbot/`：BricsBot 网格、材质、纹理和 URDF。
- `model/robot/bluerov2/`：BlueROV2 网格、纹理及螺旋桨。
- `model/robot/bluerov2.urdf`：BlueROV2 的 RViz 描述。
- `model/scn/`：flat、wavetank 等场景资源。
- `scenarios/models/`：现有岩石、海胆资源，继续沿用包路径引用。

同步内容：

1. `aquaflow_stonefish/launch/{rock_seaurchin,aquaflow_pool,bluerov2_reference}.launch` 的资源根目录。
2. `algorithm/objectnav/expert_data_rule/launch/continuous_expert_collection.launch` 的默认资源根目录。
3. `scenarios/bricsbot_reference.scn`、`bluerov2_reference.scn` 中的 `bricsbot/...`、`bluerov2/...` 分别改为 `robot/bricsbot/...`、`robot/bluerov2/...`，包含螺旋桨。
4. `scenarios/bluerov2_reference_tank.scn` 的 `flat.obj` 改为 `scn/flat.obj`。
5. `visualization.launch` 的 URDF 路径及两个 URDF 内的 `package://` 网格路径。
6. `aquaflow_stonefish/CMakeLists.txt` 安装目录由 `data` 改为 `model`。
7. 两个 Blender 网格工具脚本的命令示例更新为新路径。

SCN 内的灯珠 `origin`、`radius`、初始颜色和发光量保持当前值。只修改模型路径字符串，未重导出 OBJ。MTL 与 PNG 仍在同一目录，原有纹理相对引用保留。

## 新增与修改文件

### stonefish_ros

- 新增 `msg/LightStripCommand.msg`：完整分组指令。
- 新增 `include/stonefish_ros/LightStripState.h`：数值校验与闪烁相位计算，无 ROS/图形依赖。
- 新增 `include/stonefish_ros/LightBackend.h`：编译期选择原生或扩展接口。
- 新增 `include/stonefish_ros/ROSLightController.h`、`src/ROSLightController.cpp`：一个命令话题对应一组灯珠、一个订阅；ROS 缓存、仿真计时、渲染应用。
- 修改 `ROSSimulationManager.h/.cpp`：管理控制器生命周期，推进模拟时间，销毁实体之前清理订阅和灯珠引用；SCN 解析失败时同样清空，避免引擎删除灯珠后保留悬空指针。
- 修改 `ROSScenarioParser.cpp`：扩展 `<ros_subscriber command="..."/>`，保留原有 `origin` 订阅能力。
- 修改 `parsed_simulator.cpp`：在渲染线程应用灯光状态。
- 修改 `CMakeLists.txt`：生成消息、编译模块、注册独立 C++ 测试。
- 新增 `test/light_strip_state_test.cpp`：时序、边界值与两种后端接口的独立测试。

### aquaflow_stonefish

- 新增 `cfg/LedStrips.cfg`、`scripts/led_strip_controller.py`：运行时面板参数及锁存消息发布。
- 新增 `launch/led_strips.launch`：可独立启动控制节点及可选面板。
- 修改 `tracking_urchin.launch`：默认启动灯带控制节点；面板默认不弹出。
- 修改 `bricsbot_reference.scn`：左右四灯分别关联一个命令话题。
- 修改 `CMakeLists.txt`、`package.xml`：dynamic_reconfigure、面板和测试依赖。
- 新增 `test/test_led_strip_controller.py`、`test/test_model_resources.py`：控制消息边界及真实资源路径检查。

## 控制接口

命令话题：

- `/bricsbot/lights/left/cmd`
- `/bricsbot/lights/right/cmd`

消息类型：`stonefish_ros/LightStripCommand`。控制节点的 `vehicle_name` 必须与 SCN 实际机器人名称一致；当前 rock_seaurchin 场景中的 BricsBot 名称固定为 `bricsbot`，仅改 launch 参数不会重命名 SCN 内的机器人。

| 字段 | 含义 |
|---|---|
| mode | 0 关闭，1 常亮，2 闪烁 |
| r/g/b | RGB，分别在 0～1 内 |
| brightness | 相对 SCN 初始发光量的比例，0～1 |
| blink_hz | 每仿真秒完整亮灭周期数；闪烁模式必须 > 0 |
| duty_cycle | 每周期亮灯比例，0～1 |

以当前每灯 100 为例，扩展后端收到 brightness=0.5 会请求绝对发光量 50，重复提交仍为 50，不进行累计相乘。SCN 字段虽叫 illuminance，官方 Light 接口将其作为光通量参数 luminous power，单位 lm。

非法模式、NaN/无穷值、越界颜色/亮度/占空比、闪烁模式的零频率会被拒绝，保持上一条有效配置。暂停时仿真累计步长不再增长，闪烁相位冻结；修改颜色或亮度不重置相位。同频同占空比的左右组共用同一个仿真时间基准。

能力话题（`std_msgs/Bool`，锁存）：

- `/bricsbot/lights/left/cmd/appearance_supported`
- `/bricsbot/lights/right/cmd/appearance_supported`

false 表示仅原生开关后端；true 表示本次构建检测到约定的扩展 API。它是接口检测结果，不替代实际渲染验收。

直接测试闪烁（停止面板控制节点后使用，避免下一次面板修改覆盖指令）：

```bash
rostopic pub -1 /bricsbot/lights/left/cmd stonefish_ros/LightStripCommand \
  "{mode: 2, r: 0.05, g: 1.0, b: 0.1, brightness: 1.0, blink_hz: 1.0, duty_cycle: 0.5}"
```

1 Hz、0.5 占空比表示亮 0.5 秒、灭 0.5 秒。高于显示帧率可分辨范围的闪烁不保证能在窗口逐次看清；本轮用于可见灯效，不实现通信接收与编码。

## 编译与使用

在实际 Linux ROS1 工作空间内安装依赖并构建：

```bash
rosdep install --from-paths src --ignore-src -r -y
catkin_make
source devel/setup.bash
```

使用原版 Stonefish 时也可以构建；此时调色与非零亮度比例不会生效，日志会说明原因。ROS 消息及 Python cfg 都是编译生成，直接运行脚本而不先构建会缺少这些模块。

启动仿真并显示控制面板：

```bash
roslaunch aquaflow_stonefish tracking_urchin.launch \
  scene:=rock_seaurchin vehicle_model:=bricsbot vehicle_name:=bricsbot \
  enable:=true show_led_panel:=true
```

也可在仿真已运行时单独启动：

```bash
roslaunch aquaflow_stonefish led_strips.launch show_panel:=true
```

此时主启动命令应加 `start_led_controller:=false`，保证只有一个锁存控制节点。面板选择 `/led_strip_controller`，分别设置左右 mode、RGB、brightness、blink_hz、duty_cycle。当前发布节点在参数变更时发布完整左右配置，不高频发送亮灭消息。

## Stonefish 引擎后续需要的补丁（本次未应用）

以下是给引擎维护者的接口与实现要求。应核对目标机实际使用的 Stonefish 1.6 源码版本；先修改源码，再构建安装库，不能只改安装目录中的头文件。

### 1. Library/include/actuators/Light.h

在 public 增加 ROS 兼容层检测的精确接口：

```cpp
void setLightProperties(const Color& color, Scalar luminousPower, bool enabled);
```

在 private 增加构造时光通量到渲染光强的换算系数，例如：

```cpp
GLfloat powerToIntensity = 0.f;
```

本工程约定从渲染线程调用该 setter。不要在 ROS 回调线程直接调用，也不要在该函数中重新创建光源、网格或 GPU 对象。

### 2. Library/include/graphics/OpenGLLight.h 与 src/graphics/OpenGLLight.cpp

增加更新现有光源颜色与已换算强度的方法：

```cpp
// Called on the rendering thread. intensity is the value stored in colorLi.w.
void setColorIntensity(glm::vec3 rgb, GLfloat intensity);
```

实现核心为对现有 colorLi 赋值，例如：

```cpp
void OpenGLLight::setColorIntensity(glm::vec3 rgb, GLfloat intensity)
{
    colorLi = glm::vec4(rgb, glm::max(0.f, intensity));
}
```

正式补丁应校验非有限值，并约束 RGB 范围；本 ROS 入口已有同样的指令校验。这一入口保持既有着色器从 colorLi 读取颜色和强度的方式。

### 3. Library/src/actuators/Light.cpp

修改 `InitGraphics()`：使用“单位光通量”创建对应点光源/聚光灯，读取构造函数已有的换算结果并保存为固定系数，再恢复 SCN 的实际发光量。

原本传入最后一个参数 Fi 的两个构造调用，改为传入 1.0f；创建成功后增加：

```cpp
powerToIntensity = glLight->getColorLi().w;
glLight->setColorIntensity(c.rgb, powerToIntensity * static_cast<GLfloat>(Fi));
```

保留原来的位置更新、开启光源、注册光源等初始化步骤。此方案复用点光源和聚光灯自身的光强归一化公式，不需要在 ROS 代码中重复写各自的公式。

新增 setter 的核心逻辑：

```cpp
void Light::setLightProperties(const Color& color, Scalar luminousPower, bool enabled)
{
    // Validate finite RGB/power before assigning; reject invalid values.
    c = color;
    Fi = btMax(Scalar(0), luminousPower);
    if(glLight != nullptr)
    {
        glLight->setColorIntensity(c.rgb, powerToIntensity * static_cast<GLfloat>(Fi));
        Switch(enabled && Fi > Scalar(0));
    }
}
```

代码块展示核心流程，正式补丁需要加入前述输入校验。使用固定换算系数很重要：**不能拿旧 Fi 作分母计算比例，也不能反复乘旧亮度**，否则发光量为零之后可能无法恢复，或连续拖动滑块导致亮度不断衰减。

### 4. 分组开关的绘制索引检查

目标机若沿用官方源码中“SetupLights 跳过关闭灯光、DrawLightSource 使用原始 lightId”这套实现，还需要检查 `Library/src/graphics/OpenGLContent.cpp` 的光源索引：

- 光照 UBO 只含开启的点光源/聚光灯，索引是压缩后的索引。
- DrawLightSource 对开启灯珠设置 lightId 时，应分别计数前面开启的同类型光源。
- 不能在关闭左组后，继续用右组的原始数组下标去索引压缩后的 UBO。

因此验收必须包含“左灭右亮”和“左右不同步闪烁”。根据目标版本是否已修复该问题决定是否需要此项补丁；本次没有修改任何引擎文件。

### 5. 补丁后的构建顺序

```bash
# STONEFISH_SRC 指向目标机实际的引擎源码目录。
cmake -S "$STONEFISH_SRC" -B "$STONEFISH_SRC/build-led" -DCMAKE_BUILD_TYPE=Release
cmake --build "$STONEFISH_SRC/build-led" -j2
sudo cmake --install "$STONEFISH_SRC/build-led"
sudo ldconfig
# 回到包含 src/ 的 ROS 工作空间根目录。
catkin_make --force-cmake
source devel/setup.bash
```

重新启动仿真后，能力话题应为 true；再验证 RGB 与亮度实际画面。分发到另一台电脑时，除 ROS 工程外，还要同步引擎补丁、头文件和库的构建版本。

## 验证方式与验收清单

本地独立测试命令：

```bash
python -B -m unittest discover -s src/aquaflow_stonefish/test -p 'test_*.py'
g++ -std=c++17 -Wall -Wextra -I src/stonefish_ros/include \
  src/stonefish_ros/test/light_strip_state_test.cpp -o /tmp/light_strip_state_test
/tmp/light_strip_state_test
```

工作空间构建后也可运行：

```bash
catkin_make run_tests_aquaflow_stonefish
ctest --test-dir build -R light_strip_state_test --output-on-failure
```

本次本地验证结果：

- Python unittest：5 项通过，包含左右消息独立性、锁存发布和新资源路径。
- 独立 C++17 测试：编译并运行通过，覆盖开关/闪烁时序、非法输入、原版/扩展接口分支和绝对发光量。以 `-DNDEBUG` 重新编译运行也通过，检查不会在 Release 模式被省略。编辑电脑临时使用 Zig 0.13.0 的 C++ 编译器，不构成 ROS 工程依赖。
- 资源内容：22 个迁移后的网格、材质、纹理文件与原 Git HEAD 内容一致；两个 URDF 更新路径。
- XML：23 个 launch/SCN/URDF/package 文件解析通过。
- Python/CFG：6 个相关文件语法检查通过。
- Git diff --check：通过。

独立代码审查发现并修正了一项失败路径问题：SCN 解析失败时先清空灯带缓存，防止访问已由引擎删除的灯珠。已复核清理顺序，尚未在 ROS 运行环境执行故障注入。

当前编辑环境无 ROS/catkin/Stonefish 运行库，尚未进行完整 catkin 构建和实际灯光渲染验证。

目标机验收：

1. 场景、纹理、螺旋桨和 RViz 模型均能从新目录加载。
2. 默认仍为左绿右蓝、每侧四灯，安装位置和机器人运动保持当前配置。
3. 关闭、常亮、1 Hz/50% 闪烁正确；左右可独立设置，组内同步。
4. 暂停后闪烁停止推进，恢复后继续。
5. 引擎补丁前明确显示不支持调色/非零调光；补丁后能力标志为 true。
6. 补丁后红绿蓝切换、0/0.5/1 亮度及灭灯再恢复均正确。
7. 左组关闭、右组开启，及左右不同闪烁频率时无光源索引或渲染异常。

## 引擎接口核对来源

引擎补丁以目标机的实际源码为准。接口说明参考官方 [Light](https://github.com/patrykcieslak/stonefish/blob/master/Library/include/actuators/Light.h)、[Light.cpp](https://github.com/patrykcieslak/stonefish/blob/master/Library/src/actuators/Light.cpp)、[GraphicalSimulationApp](https://github.com/patrykcieslak/stonefish/blob/master/Library/include/core/GraphicalSimulationApp.h) 和 [OpenGLContent.cpp](https://github.com/patrykcieslak/stonefish/blob/master/Library/src/graphics/OpenGLContent.cpp)。这些链接的 master 可能随上游更新，不能替代目标机版本核对。
