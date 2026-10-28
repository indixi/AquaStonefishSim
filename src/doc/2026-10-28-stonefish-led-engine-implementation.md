# Stonefish 灯带引擎补丁与 ParseColor 编译修复

## 范围与根因

本轮按用户授权修改外层 `AquaStonefishSim/third_party/stonefish`，内层重复工程未修改。引擎基于子模块提交 `b21eb8e`（Stonefish 1.6.0）。未提交或推送。Stonefish 是独立 Git 子模块；本轮改动位于子模块工作区，父仓库仅显示子模块已修改。以后若通过 Git 分发，需要先提交子模块实现和测试，再更新父仓库引用，不能只提交父仓库。

`ROSScenarioParser::ParseLight()` 调用了 `ScenarioParser::ParseColor()`，但官方头文件把该方法放在 private，派生类无权访问。这是上次 ROS 接入中的接口访问错误，不是 PID、OBJ 或灯光配置引起的。本次将 ParseColor 声明移至 protected，原解析实现不变，继续支持 rgb、hsv、temperature、gray。

报错读取的是 **/usr/local/include/Stonefish/core/ScenarioParser.h**，因此仅修改仓库源码不会替换它；必须先构建并安装引擎，再重新构建 ROS。

## 已实施

- [x] 先用真实引擎头文件复现 private 访问错误；新增编译回归检查。
- [x] ScenarioParser.h：ParseColor 从 private 移至 protected。
- [x] Light.h/.cpp：新增 `setLightProperties(const Color&, Scalar luminousPower, bool enabled)`，与现有 ROS 编译期检测接口一致。校验有限值，RGB 约束在 0～1，负发光量归零，使用绝对光通量。
- [x] Light::InitGraphics：从单位光通量构造结果保存固定换算系数，再应用实际光通量，兼容点光源及聚光灯；亮度为零后能再次恢复。
- [x] Light::Switch：保存开启状态，初始化后恢复；光通量为零时不激活光源。
- [x] OpenGLLight.h/.cpp：新增 CPU 颜色/强度更新接口和 `getActiveIndex()`，不重建网格或 GPU 光源。
- [x] OpenGLContent.cpp：绘制灯珠时使用前面“开启且同类型”的光源数量作为 UBO 索引，修复关闭左组后右组下标错误。
- [x] OpenGLSpotLight.h/.cpp：强度改变后更新阴影远平面，零/很低强度时仍保持远平面大于近平面。
- [x] OpenGLPipeline.cpp：活动聚光灯重用原 FBO 重新绑定到压缩阴影层，先烘焙阴影再上传光源 UBO，避免独立闪烁错层和亮度变化使用上一帧矩阵。
- [x] CMakeLists.txt：新增可选 `BUILD_LIGHT_CONTROL_TESTS`，包含无窗口运行测试及接口编译检查。
- [x] 独立代码审查；两项聚光灯阴影问题已修正并复核。
- [ ] 目标 Linux 完整引擎构建、catkin build 和画面验收。

ROS 回调仍只缓存指令，灯光修改仍从 ROS 图形应用的渲染线程执行；未更改灯珠坐标、半径、质量、浮力、PID 或推力分配。

## 修改文件

引擎中修改十个文件：

1. `Library/include/core/ScenarioParser.h`
2. `Library/include/actuators/Light.h`
3. `Library/src/actuators/Light.cpp`
4. `Library/include/graphics/OpenGLLight.h`
5. `Library/src/graphics/OpenGLLight.cpp`
6. `Library/include/graphics/OpenGLSpotLight.h`
7. `Library/src/graphics/OpenGLSpotLight.cpp`
8. `Library/src/graphics/OpenGLContent.cpp`
9. `Library/src/graphics/OpenGLPipeline.cpp`
10. `CMakeLists.txt`

新增 `Tests/LightParserAccessTest.cpp` 和 `Tests/LightControlTest.cpp`。前者在编译时验证派生类访问权限和 Light setter 签名；后者检查颜色、绝对强度、零强度恢复、无效输入拒绝及混合类型光源的压缩索引。

## 在你的 Linux 电脑上构建安装

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

## 本地验证记录与边界

- 修复前，真实 ScenarioParser.h 的派生访问检查复现 private 编译错误；灯光测试因缺少新接口而编译失败。
- 修复后，`LightParserAccessTest.cpp` 与实际 `Light.cpp`、`OpenGLLight.cpp`、`OpenGLSpotLight.cpp`、`OpenGLContent.cpp`、`OpenGLPipeline.cpp` 均成功生成目标文件。
- CPU 运行检查通过：直接从修改后的 OpenGLLight.cpp 提取实际 CPU 方法定义，与回归测试一起编译运行，验证颜色/强度更新及活动索引。未执行 GPU 初始化方法。该检查不等于完整库链接测试。
- 阴影调度检查：提取实际旧/新渲染 pass 代码，与无 GPU 的边界替身一起执行。旧版在活动阴影层和矩阵上传时序两项均失败，修正版两项通过。它验证调度逻辑，不代替 GPU 图像验收。
- 现有 Python unittest：5 项通过。
- 现有 ROS 灯带独立 C++ 状态/后端测试通过。
- 引擎与主仓库 diff 检查通过。
- 临时验证使用 Zig C++17、GLM 0.9.9.8 和 SDL2 2.30.11 头文件。针对上游 Windows 宏冲突和平台分支使用了仅在临时目录中的兼容头，没有写入仓库。

本地 Windows 没有 ROS/catkin，也没有完整 Linux 引擎运行环境；完整 OpenGLLight.cpp 单独链接尝试因缺少整套图形/物理库符号未通过，因此改用上述实际 CPU 方法检查。Linux 的完整引擎链接、CTest、catkin build 和画面验收需要按前述步骤执行，不能声称本地已经完成。
