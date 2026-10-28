# AquaStonefishSim

AquaStonefishSim 是基于 **Stonefish 仿真引擎**和 **ROS1** 的水下机器人仿真实验工程，主要用于 BricsBot 的场景仿真、运动控制、RGB-D 数据采集及灯带效果验证，同时包含 BlueROV2 模型和水下目标导航相关代码。

当前主要使用 BricsBot，在岩石与海胆场景中运行控制节点，并通过参数面板调整机器人左右两侧灯带的开关、闪烁、颜色和亮度。

## 常用启动指令

在已完成引擎安装及 ROS 工程编译的工作空间根目录执行：

```bash
source /opt/ros/noetic/setup.bash
source devel/setup.bash
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"

roslaunch aquaflow_stonefish tracking_urchin.launch \
  scene:=rock_seaurchin \
  vehicle_model:=bricsbot \
  vehicle_name:=bricsbot \
  enable:=true \
  show_led_panel:=true
```

这是当前主要使用的启动方式，会启动 Stonefish 场景、RViz、机器人控制相关节点、数据采集节点和灯带调参面板。结束运行时，在启动终端按 `Ctrl+C`。

| 参数 | 作用 |
|---|---|
| `scene:=rock_seaurchin` | 加载岩石与海胆场景；当前对应 Rock_SeaUrchin2.scn |
| `vehicle_model:=bricsbot` | 选择 BricsBot 对应的六推进器推力分配 |
| `vehicle_name:=bricsbot` | 控制及数据话题使用的机器人名称，需要与 SCN 中的实际名称一致 |
| `enable:=true` | 启用推进器分配节点的输出 |
| `show_led_panel:=true` | 打开灯带 dynamic_reconfigure 参数面板 |

当前场景中的 BricsBot 名称为 `bricsbot`。修改 `vehicle_name` 参数不会自动重命名 SCN 内的机器人。

## 仿真引擎与工程关系

本工程使用 [Stonefish](https://github.com/patrykcieslak/stonefish) 进行水下机器人动力学、环境及图形仿真，通过 `stonefish_ros` 与 ROS 通信。

- 本仓库负责机器人资源、SCN 场景、ROS 启动文件、控制节点、灯带控制及实验代码。
- `third_party/stonefish` 是引擎 Git 子模块，来源为 [indixi/stonefish](https://github.com/indixi/stonefish)。
- 当前引擎包含动态灯光颜色、光通量控制及相关绘制修正，灯带改色和连续调光需要安装这份补丁版引擎。

**同步 Git 仓库只会更新源码，不会自动更新系统中安装的 Stonefish。** 引擎源码与 ROS 包分别构建；修改引擎后，需要先安装引擎，再重新编译受影响的 ROS 包。

## 目录结构

```text
AquaStonefishSim/
├── README.md
├── scripts/                         # 环境脚本
├── src/
│   ├── aquaflow_stonefish/           # 场景、模型、启动文件和灯带控制
│   │   ├── launch/
│   │   ├── scenarios/
│   │   ├── model/robot/              # 机器人模型、纹理和 URDF
│   │   ├── model/scn/                # 场景网格资源
│   │   ├── cfg/                     # 灯带动态参数
│   │   └── scripts/
│   ├── stonefish_ros/               # Stonefish ROS 接口
│   ├── robot_control/               # 参考指令、级联 PID 和动作执行
│   ├── algorithm/objectnav/         # 数据采集、专家策略和目标导航
│   └── doc/                         # 工程改动、构建和使用记录
└── third_party/
    └── stonefish/                   # Stonefish 引擎子模块
        └── usr_doc/khd/             # 引擎源码改动说明
```

## 获取与构建

当前运行流程使用 Linux、ROS1 Noetic 和 catkin_tools。图形环境与引擎依赖要求参见 Stonefish 的说明。以下以 `~/aquastonefish_ws` 为 catkin 工作空间示例；已有工作空间可替换对应路径。

### 1. 获取主仓库和引擎子模块

下面使用 SSH，需要先配置 GitHub SSH 访问：

```bash
mkdir -p ~/aquastonefish_ws/src
cd ~/aquastonefish_ws/src
git clone --recurse-submodules git@github.com:indixi/AquaStonefishSim.git
```

已有仓库可在主仓库目录补齐子模块：

```bash
git submodule update --init --recursive
```

### 2. 编译安装 Stonefish

```bash
cd ~/aquastonefish_ws/src/AquaStonefishSim

cmake -S third_party/stonefish \
      -B third_party/stonefish/build-led \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DBUILD_TESTS=OFF

cmake --build third_party/stonefish/build-led -j2
sudo cmake --install third_party/stonefish/build-led
sudo ldconfig
```

`build-led` 是编译目录名，可以更换；更换后，构建和安装命令要使用相同目录。`/usr/local` 是这里选择的安装前缀。

### 3. 安装 ROS 依赖并构建

在 ROS、rosdep 和 catkin_tools 已安装并配置好的环境中执行：

```bash
source /opt/ros/noetic/setup.bash
cd ~/aquastonefish_ws

rosdep install --from-paths src --ignore-src -r -y
catkin build --force-cmake --cmake-args \
  -DStonefish_DIR=/usr/local/lib/cmake/Stonefish

source devel/setup.bash
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
```

一般直接重新构建即可，不需要每次清理。若更新引擎后仍运行旧编译结果，可参考下方排查说明。

## 灯带控制

启动后，在参数面板中选择 `/led_strip_controller`。

左右灯带分别使用 `left_`、`right_` 参数前缀：

| 参数后缀 | 含义 |
|---|---|
| `mode` | 0 关闭、1 常亮、2 闪烁 |
| `r / g / b` | RGB 通道，范围分别为 0～1 |
| `brightness` | 相对 SCN 初始光通量的比例，范围 0～1 |
| `blink_hz` | 每仿真秒的完整闪烁周期数 |
| `duty_cycle` | 每个闪烁周期亮灯的比例，范围 0～1 |

例如设置左侧纯红色：`left_mode=1`、`left_brightness=1`、`left_r=1`、`left_g=0`、`left_b=0`。

闪烁按仿真时间推进；暂停仿真后相位停止推进。当前功能用于展示灯光效果，不包含可见光通信接收与编码。

检查动态颜色/亮度接口是否已接入：

```bash
rostopic echo -n 1 /bricsbot/lights/left/cmd/appearance_supported
rostopic echo -n 1 /bricsbot/lights/right/cmd/appearance_supported
```

补丁版引擎与 ROS 包匹配构建后，预期为 `data: True`。

## 其他基本指令

只启动岩石与海胆场景：

```bash
roslaunch aquaflow_stonefish rock_seaurchin.launch \
  scene:=rock_seaurchin vehicle_model:=bricsbot
```

主程序启动时不显示灯带面板：

```bash
roslaunch aquaflow_stonefish tracking_urchin.launch \
  scene:=rock_seaurchin vehicle_model:=bricsbot \
  vehicle_name:=bricsbot enable:=true show_led_panel:=false
```

在控制节点已经运行时，另开参数面板：

```bash
rosrun rqt_reconfigure rqt_reconfigure
```

查看灯带当前指令及机器人图像话题：

```bash
rostopic echo -n 1 /bricsbot/lights/left/cmd
rostopic list
rqt_image_view
```

BricsBot RGB 图像话题为 `/bricsbot/rgb/image_color`。主启动文件同时运行数据采集节点，采集操作参见下方数据采集文档。

## 常见问题

### 能关闭和闪烁，但不能改色

如果 `appearance_supported` 为 False，当前运行的 ROS 构建没有检测到新增的 `Light::setLightProperties()` 接口。确认已安装仓库中的补丁版引擎，再构建 ROS 包。

需要排除旧编译产物时，在 catkin 工作空间根目录执行：

```bash
catkin clean --dependents stonefish_ros -y
catkin build --force-cmake --cmake-args \
  -DStonefish_DIR=/usr/local/lib/cmake/Stonefish
source devel/setup.bash
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
```

这一步清理指定包及其依赖者的生成文件，不修改源码。

### 源码已更新，但使用的仍是旧版本

- 核对 CMake 找到的 Stonefish 安装位置，而不只检查 `third_party/stonefish`。
- 新终端需要加载当前工作空间的 `devel/setup.bash`。
- 若使用其他安装前缀，修改上述 `Stonefish_DIR` 和动态库路径。
- 现有 `scripts/setup_stonefish_ros.sh` 包含特定电脑的旧库路径和旧工作空间路径，使用前应按实际环境核对；当前 README 的命令显式加载所选工作空间。

### 主仓库与子模块如何同步

更新时，在主仓库目录执行：

```bash
git pull
git submodule update --init --recursive
```

引擎是独立 Git 子模块。修改引擎后，需要先在子模块中提交并推送，再在主仓库更新子模块引用。只修改主仓库 README 时，只需提交主仓库文档。

## 详细文档

- [灯带整体架构、ROS/引擎源码改动与运行指南](src/doc/2026-10-28-led-strip-control.md)
- [数据采集](src/algorithm/objectnav/data_generate/README.md)
- [规则专家策略](src/algorithm/objectnav/expert_data_rule/README.md)
- [目标导航与训练入口](src/algorithm/objectnav/ObjectNav/README.md)
- [Stonefish ROS 接口](src/stonefish_ros/README.md)

## 引擎来源

本工程的仿真能力建立在 Stonefish 及 stonefish_ros 之上。上游项目由 Patryk Cieslak 等贡献者维护；使用和引用引擎时请遵循其许可证与引用说明。
