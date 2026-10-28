# 灯带功能整体架构、源码改动与运行指南（2026-10-28）

本文合并 ROS 灯带控制、模型资源迁移和 Stonefish 引擎补丁说明，作为 `src/doc` 下的统一入口。

## 新增与修改架构总览

下列标记表示相对灯带功能接入之前的改动，不代表当前 Git 的提交状态。

### ROS 工程

```text
AquaStonefishSim/src/
├── stonefish_ros/
│   ├── msg/LightStripCommand.msg                     【新增】
│   ├── include/stonefish_ros/LightStripState.h       【新增】
│   ├── include/stonefish_ros/LightBackend.h          【新增】
│   ├── include/stonefish_ros/ROSLightController.h    【新增】
│   ├── src/ROSLightController.cpp                    【新增】
│   ├── include/stonefish_ros/ROSSimulationManager.h  【修改】
│   ├── src/ROSSimulationManager.cpp                  【修改】
│   ├── src/ROSScenarioParser.cpp                     【修改】
│   ├── src/parsed_simulator.cpp                      【修改】
│   ├── test/light_strip_state_test.cpp               【新增】
│   └── CMakeLists.txt                                【修改】
│
├── aquaflow_stonefish/
│   ├── cfg/LedStrips.cfg                             【新增】
│   ├── scripts/led_strip_controller.py               【新增】
│   ├── launch/led_strips.launch                      【新增】
│   ├── scenarios/bricsbot_reference.scn              【修改】
│   ├── launch/tracking_urchin.launch                 【修改】
│   ├── test/test_led_strip_controller.py             【新增】
│   ├── test/test_model_resources.py                  【新增】
│   ├── CMakeLists.txt                                【修改】
│   └── package.xml                                   【修改】
│
└── doc/
    └── 2026-10-28-led-strip-control.md               【合并整理】
```

资源路径迁移还涉及其他 launch、SCN、URDF 和工具脚本，见后文“资源目录与路径迁移”。

### Stonefish 引擎

```text
AquaStonefishSim/third_party/stonefish/
├── Library/include/core/ScenarioParser.h             【修改】
├── Library/include/actuators/Light.h                 【修改】
├── Library/src/actuators/Light.cpp                   【修改】
├── Library/include/graphics/OpenGLLight.h            【修改】
├── Library/src/graphics/OpenGLLight.cpp              【修改】
├── Library/include/graphics/OpenGLSpotLight.h        【修改】
├── Library/src/graphics/OpenGLSpotLight.cpp          【修改】
├── Library/src/graphics/OpenGLContent.cpp            【修改】
├── Library/src/graphics/OpenGLPipeline.cpp           【修改】
├── Tests/LightParserAccessTest.cpp                   【新增】
├── Tests/LightControlTest.cpp                        【新增】
└── CMakeLists.txt                                    【修改】
```

子模块内部另保留 `third_party/stonefish/usr_doc/khd/2026-10-28-led-strip-source-changes.md`，用于单独维护引擎源码说明。

## 整体增加了什么

在已有八个原生灯珠上增加运行时控制：左右各四灯成组，支持独立关闭、常亮、闪烁，以及 RGB 和亮度调整。

| 模块 | 增加的能力 |
|---|---|
| 参数面板 | 分别配置左右灯带的模式、RGB、亮度、频率与占空比 |
| ROS 消息与发布 | 发送完整分组配置，锁存最近一次设置 |
| 仿真调度 | 按仿真时间计算闪烁，组内同步，暂停时冻结相位 |
| 引擎接口 | 更新现有光源的颜色、绝对光通量和开关状态 |
| 绘制与阴影 | 修正独立开关后的灯光索引、聚光灯阴影层及矩阵更新顺序 |
| 模型资源 | 将旧 data 引用同步到新的 model 目录 |

```text
rqt_reconfigure 面板
    → led_strip_controller.py 发布左右组配置
    → LightStripCommand.msg
    → ROSLightController 缓存配置、累计仿真时间
    → 图形应用 ProcessInputs() 在渲染线程应用状态
    → Light::setLightProperties()
    → OpenGLLight / OpenGLSpotLight
    → 阴影烘焙、光源 UBO 上传和灯珠绘制
```

ROS 回调只缓存参数，物理回调只累计时间，图形对象由渲染线程更新。场景解析失败或销毁时先清理灯珠引用，避免访问已删除的对象。

保留现有八灯的位置、半径、初始颜色和每灯 `illuminance=100.0`，未修改 PID、推力分配算法、质量或浮力。当前仅用于灯光效果展示，不包含可见光通信接收、识别与编码。

## ROS 工程分别增加和修改了什么

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

## Stonefish 引擎增加和修改了什么

### ParseColor 接口访问修复

`ROSScenarioParser::ParseLight()` 调用了 `ScenarioParser::ParseColor()`，但官方头文件把该方法放在 private，派生类无权访问。这是上次 ROS 接入中的接口访问错误，不是 PID、OBJ 或灯光配置引起的。本次将 ParseColor 声明移至 protected，原解析实现不变，继续支持 rgb、hsv、temperature、gray。

报错读取的是 **/usr/local/include/Stonefish/core/ScenarioParser.h**，因此仅修改仓库源码不会替换它；必须先构建并安装引擎，再重新构建 ROS。

### 动态灯光与渲染改动

- 先用真实引擎头文件复现 private 访问错误；新增编译回归检查。
- ScenarioParser.h：ParseColor 从 private 移至 protected。
- Light.h/.cpp：新增 `setLightProperties(const Color&, Scalar luminousPower, bool enabled)`，与现有 ROS 编译期检测接口一致。校验有限值，RGB 约束在 0～1，负发光量归零，使用绝对光通量。
- Light::InitGraphics：从单位光通量构造结果保存固定换算系数，再应用实际光通量，兼容点光源及聚光灯；亮度为零后能再次恢复。
- Light::Switch：保存开启状态，初始化后恢复；光通量为零时不激活光源。
- OpenGLLight.h/.cpp：新增 CPU 颜色/强度更新接口和 `getActiveIndex()`，不重建网格或 GPU 光源。
- OpenGLContent.cpp：绘制灯珠时使用前面“开启且同类型”的光源数量作为 UBO 索引，修复关闭左组后右组下标错误。
- OpenGLSpotLight.h/.cpp：强度改变后更新阴影远平面，零/很低强度时仍保持远平面大于近平面。
- OpenGLPipeline.cpp：活动聚光灯重用原 FBO 重新绑定到压缩阴影层，先烘焙阴影再上传光源 UBO，避免独立闪烁错层和亮度变化使用上一帧矩阵。
- CMakeLists.txt：新增可选 `BUILD_LIGHT_CONTROL_TESTS`，包含无窗口运行测试及接口编译检查。
- 独立代码审查；两项聚光灯阴影问题已修正并复核。

ROS 回调仍只缓存指令，灯光修改仍从 ROS 图形应用的渲染线程执行；未更改灯珠坐标、半径、质量、浮力、PID 或推力分配。
新增原生接口如下，luminousPower 为绝对光通量（lm），由 ROS 层先用 SCN 初始光通量乘 brightness 后传入：

```cpp
void Light::setLightProperties(const Color& color,
                               Scalar luminousPower,
                               bool enabled);
```

当 brightness=0 时，开关后端也能灭灯；只有 appearance_supported=True 才表示本次编译检测到 RGB/非零亮度比例接口。该标志是接口检测结果，不替代图形效果验收。

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

## 编译安装与运行

根据本次错误日志，外层 catkin 工作空间是 `/home/yzw/work_khd/AquaStonefishSim`，代码仓库位于其 `src/AquaStonefishSim`。REPO 需要指向同时包含 `src/stonefish_ros` 与 `third_party/stonefish` 的代码仓库。

### 1. 构建并安装补丁版引擎

```bash
REPO=/home/yzw/work_khd/AquaStonefishSim/src/AquaStonefishSim
test -f "$REPO/third_party/stonefish/Library/include/actuators/Light.h"

cmake -S "$REPO/third_party/stonefish" \
      -B "$REPO/third_party/stonefish/build-led" \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DBUILD_TESTS=OFF \
      -DBUILD_LIGHT_CONTROL_TESTS=ON
cmake --build "$REPO/third_party/stonefish/build-led" -j2
(cd "$REPO/third_party/stonefish/build-led" && ctest --output-on-failure)
sudo cmake --install "$REPO/third_party/stonefish/build-led"
sudo ldconfig
```

若仓库位于另一位置，只修改 REPO。测试不创建窗口，但仍需要先安装引擎原有的 OpenGL、SDL2、GLM、Freetype 编译依赖。

核对已安装头文件：

```bash
grep -n -B 8 -A 8 'bool ParseColor' /usr/local/include/Stonefish/core/ScenarioParser.h
grep -n 'setLightProperties' /usr/local/include/Stonefish/actuators/Light.h
```

第一条应显示 ParseColor 在 private 标签之前，第二条应显示新增接口。新库增加了类成员和虚函数，必须同步安装头文件与库，并重编依赖，不能只拷贝一个头文件。

### 2. 重新构建 ROS 工程

```bash
source /opt/ros/noetic/setup.bash
cd /home/yzw/work_khd/AquaStonefishSim

catkin build --force-cmake --cmake-args \
  -DStonefish_DIR=/usr/local/lib/cmake/Stonefish

source devel/setup.bash
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
```

这里使用你当前的 `catkin build`，不需要删除整个 build/devel。若仍显示 private 报错，先核对报错中的实际头文件和上述安装文件是否一致。

仓库现有 `scripts/setup_stonefish_ros.sh` 仍会把旧的 `/home/yzw/work_khd/stonefish/install/lib` 放入 LD_LIBRARY_PATH，并引用旧 catkin_ws 工作空间。本轮未改这个环境脚本；本次请使用上面明确的 setup.bash 路径，并在其他环境脚本执行后再将 /usr/local/lib 放到动态库搜索路径最前面。不要混用旧头文件、旧库与新 ROS 构建。

在外层工作空间中检查运行时库：

```bash
find devel -name parsed_simulator -type f -exec ldd {} \; | grep Stonefish
```

输出应指向补丁版安装库 /usr/local/lib。使用 catkin_tools 隔离 devel 时，可执行文件可能位于隐藏的 .private 子目录，find 会一并搜索。

### 3. 启动与验收

```bash
roslaunch aquaflow_stonefish tracking_urchin.launch \
  scene:=rock_seaurchin vehicle_model:=bricsbot vehicle_name:=bricsbot \
  enable:=true show_led_panel:=true
```

在 rqt_reconfigure 中选择 `/led_strip_controller`，设置左右 mode（0 灭、1 常亮、2 闪烁）、RGB、brightness、blink_hz 和 duty_cycle。每个灯珠原始光通量 100 时，brightness=0.5 请求 50，不会因反复拖动而累计衰减。

```bash
rostopic echo -n 1 /bricsbot/lights/left/cmd/appearance_supported
rostopic echo -n 1 /bricsbot/lights/right/cmd/appearance_supported
```

两项应为 true。依次确认：左绿右蓝初始状态；单独左灭右亮；红绿蓝切换；亮度 1→0.5→0→1；左右不同闪烁频率；暂停冻结相位、恢复继续。本轮不包括可见光通信接收、编码或识别。
### 构建与运行补充

通常直接重新构建即可，不必每次清理。`--force-cmake` 只强制重新配置，不等于强制重新编译所有源文件。需要排除旧编译产物时，在 catkin 工作空间根目录执行：

```bash
catkin clean --dependents stonefish_ros -y
catkin build --force-cmake --cmake-args \
  -DStonefish_DIR=/usr/local/lib/cmake/Stonefish
source devel/setup.bash
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
```

源码中的引擎与系统安装的引擎分开维护：Git 更新源码不会自动更新安装库，catkin 的 find_package 也不会自动构建 third_party/stonefish。先安装引擎，再构建 ROS 包。

build-led 只是本次选用的编译目录名，更换时同步修改后续构建和安装路径。ldconfig 更新系统动态库缓存，不改变 LD_LIBRARY_PATH 的优先级。

若要独立启动控制节点，主启动命令先加 `start_led_controller:=false`，再运行：

```bash
roslaunch aquaflow_stonefish led_strips.launch \
  vehicle_name:=bricsbot show_panel:=true
```

这样同一机器人只有一个锁存配置发布节点。仅需要再开一个面板时，运行 `rosrun rqt_reconfigure rqt_reconfigure` 即可。

## 验证记录与验收

以下检查结果来自原功能实施阶段；本次合并仅整理文档，没有重新执行 Linux 构建或图形验收。

### ROS 与资源检查

本地独立测试命令：

```bash
python -B -m unittest discover -s src/aquaflow_stonefish/test -p 'test_*.py'
g++ -std=c++17 -Wall -Wextra -I src/stonefish_ros/include \
  src/stonefish_ros/test/light_strip_state_test.cpp -o /tmp/light_strip_state_test
/tmp/light_strip_state_test
```

独立测试在代码仓库根目录执行。使用 catkin_tools 构建后，在 catkin 工作空间根目录运行下面的测试命令（[官方说明](https://catkin-tools.readthedocs.io/en/latest/verbs/catkin_test.html)）：

```bash
catkin test aquaflow_stonefish
(cd build/stonefish_ros && ctest -R light_strip_state_test --output-on-failure)
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

### 引擎检查记录

- 修复前，真实 ScenarioParser.h 的派生访问检查复现 private 编译错误；灯光测试因缺少新接口而编译失败。
- 修复后，`LightParserAccessTest.cpp` 与实际 `Light.cpp`、`OpenGLLight.cpp`、`OpenGLSpotLight.cpp`、`OpenGLContent.cpp`、`OpenGLPipeline.cpp` 均成功生成目标文件。
- CPU 运行检查通过：直接从修改后的 OpenGLLight.cpp 提取实际 CPU 方法定义，与回归测试一起编译运行，验证颜色/强度更新及活动索引。未执行 GPU 初始化方法。该检查不等于完整库链接测试。
- 阴影调度检查：提取实际旧/新渲染 pass 代码，与无 GPU 的边界替身一起执行。旧版在活动阴影层和矩阵上传时序两项均失败，修正版两项通过。它验证调度逻辑，不代替 GPU 图像验收。
- 临时验证使用 Zig C++17、GLM 0.9.9.8 和 SDL2 2.30.11 头文件。针对上游 Windows 宏冲突和平台分支使用了仅在临时目录中的兼容头，没有写入仓库。

本地 Windows 没有 ROS/catkin，也没有完整 Linux 引擎运行环境；完整 OpenGLLight.cpp 单独链接尝试因缺少整套图形/物理库符号未通过，因此改用上述实际 CPU 方法检查。Linux 的完整引擎链接、CTest、catkin build 和画面验收需要按前述步骤执行，不能声称本地已经完成。
上述验证记录来自功能实施阶段，本次文档合并没有重新运行 Linux 构建或 GPU 验收。用户已反馈目标机可以启动仿真；颜色、连续调光、左右独立闪烁及阴影效果仍按清单逐项确认。

Stonefish 是独立 Git 子模块。通过 Git 分发引擎改动时，先提交并推送子模块，再更新主仓库引用；仅提交主仓库不会包含子模块内未提交的源码。

## 引擎接口核对来源

引擎补丁以目标机的实际源码为准。接口说明参考官方 [Light](https://github.com/patrykcieslak/stonefish/blob/master/Library/include/actuators/Light.h)、[Light.cpp](https://github.com/patrykcieslak/stonefish/blob/master/Library/src/actuators/Light.cpp)、[GraphicalSimulationApp](https://github.com/patrykcieslak/stonefish/blob/master/Library/include/core/GraphicalSimulationApp.h) 和 [OpenGLContent.cpp](https://github.com/patrykcieslak/stonefish/blob/master/Library/src/graphics/OpenGLContent.cpp)。这些链接的 master 可能随上游更新，不能替代目标机版本核对。
