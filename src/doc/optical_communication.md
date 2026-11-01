# 可见光通信：架构、协议、运行与维护记录

本文件是可见光通信功能的持续维护入口；后续相关代码、协议、配置、运行方法和验证结果统一更新这里。首次实施日期：2026-10-30。

## 已确认的第一版范围

- 代码包位于 `src/algorithm/optical_comm`，每台机器人运行相同组件，通过配置区分角色和地址。
- 三台静止 BricsBot：Leader ID=1，Follower ID=2、3；汇合、运动及业务语义由上层负责。
- Leader 唯一发起通信，半双工；Follower 有数据也等待 Leader 请求。
- 可见机器人都能接收寻址帧，只有目标应答；会话期间锁定目标，多次读写后 END，再切换机器人。
- 业务输入输出是长度可变的 bit 串，典型约 10 bit，不把 20 bit 写成上限。
- 蓝/绿各两档亮度，00 蓝高、01 蓝低、10 绿高、11 绿低。映射可以替换。
- 颜色映射和周期 T 提前配置，同步头恢复相对节拍，不要求全局时钟一致，不发送颜色标定序列。
- RGB 接收只判断颜色/亮度变化，不使用机器人/灯带目标检测器，不读取对方的灯控话题或发送数据。
- CRC、有限重试、去重、成功/失败事件；业务解释和执行均在上层。
- OPEN、ACK、READ、WRITE、DATA、END 和 ERROR 都通过灯光与相机，ROS 只作各机器人内部接口。

## 新增架构

以下均为本轮新增，原跟踪模型、PID 和 Stonefish 引擎源码不变。

```text
AquaStonefishSim/
├── src/algorithm/optical_comm/
│   ├── CMakeLists.txt / package.xml / setup.py
│   ├── msg/CommRequest.msg
│   ├── msg/CommEvent.msg
│   ├── config/
│   │   ├── robots.yaml / symbols.yaml
│   │   └── timing.yaml / protocol.yaml / vision.yaml
│   ├── scripts/
│   │   ├── optical_comm_node.py
│   │   └── communication_demo.py
│   ├── launch/
│   │   ├── robot_comm.launch
│   │   └── three_robot_comm.launch
│   ├── src/optical_comm/
│   │   ├── codecs/base.py
│   │   ├── protocol/frame.py
│   │   ├── protocol/state_machine.py
│   │   ├── physical/link.py
│   │   ├── vision/color_brightness.py
│   │   ├── drivers/stonefish_led.py
│   │   ├── drivers/clock.py
│   │   ├── runtime_config.py
│   │   └── ros_bridge.py
│   └── test/
│       ├── test_codec.py / test_protocol.py
│       ├── test_physical.py / test_vision.py
│       ├── test_runtime_contract.py / test_stack.py / test_resources.py
│       └── test_review_regressions.py
├── src/aquaflow_stonefish/scenarios/
│   ├── bricsbot_optical_reference.scn
│   └── three_robot_optical_comm.scn
└── src/doc/optical_communication.md
```

| 部分 | 输入 → 输出 | 职责 |
|---|---|---|
| codecs | bit ↔ 符号 ID | 四状态 2bit 编码；同时提供蓝色两档 1bit 编码，协议不变 |
| protocol/frame | 帧 ↔ bit | 紧凑头、有效 bit 长度、寻址、CRC |
| protocol/state_machine | 请求与已校验帧 → 待发帧/事件 | 主从会话、ACK、重试、去重和 END |
| physical/link | 帧 → 定时灯光；观测符号 → 帧 | 同步头、发送节拍、相对时间窗口、多帧投票 |
| vision | 本机 BGR 图像 → 符号/置信度/亮度 | 全图颜色和亮度变化筛选，无固定 ROI |
| drivers | 符号 → 本机灯控命令 | 同步驱动左右灯带，接收能力检查 |
| ros_bridge | ROS ↔ 上述模块 | 本机相机、业务请求、结果和状态连接 |
| communication_demo | 示例上层业务 | 发起会话、提供示例回传内容；不属于通信协议 |

## 帧格式 V1

按顺序传输，不按字节对齐：

| 字段 | bit 数 | 含义 |
|---|---:|---|
| kind | 3 | OPEN=1、ACK=2、WRITE=3、READ=4、DATA=5、END=6、ERROR=7 |
| session | 8 | 1～255，Leader 为每个新会话递增 |
| seq | 8 | OPEN/END 为 0，业务操作 1～255 |
| payload_length | 12 | 原始有效载荷 bit 数，不包括颜色编码补零 |
| source / target | 各 4 | 仅 OPEN 携带，地址 1～15 |
| payload | 可变 | 业务 bit；OPEN 为本次 Leader 进程的 32bit 随机启动标识；ACK 为被确认类型 3bit；ERROR 为 8bit 错误码 |
| CRC | 8 | poly=0x07、初始 0、MSB-first，对前面所有实际 bit 计算 |

普通帧利用会话上下文，不重复发送地址。OPEN 的启动标识用于区分进程重启与同一 OPEN 重传；Follower 仍保留旧会话时，对新启动标识回复忙，不错误确认成新会话。控制载荷长度不受业务长度上限限制。业务帧最大载荷默认 256 bit，可配置到 4095 bit；第一版不分片，超过配置上限明确拒绝。奇数 bit 或非字节长度可以原样恢复，物理映射的末尾补零不交给上层。

序号在同一会话内不回绕：耗尽后先 END 再重新建立会话。错误码 1=忙，2=序号内容冲突，3=本机上层提供数据超时。

## 会话与可靠性

```text
Leader                         被寻址的 Follower
  ├── OPEN(源/目标地址) ────────────►│
  │◄── ACK(OPEN) ──────────────────┤
  ├── WRITE(业务 bits) ────────────►│
  │◄── ACK(WRITE) ─────────────────┤
  ├── READ(请求 bits，可空) ────────►│
  │◄── ACK(READ) ──────────────────┤
  │                   通知本机上层 DATA_REQUEST
  │                   上层用 PROVIDE 提供回复 bits
  │◄── DATA(回复 bits) ─────────────┤
  ├── ACK(DATA) ──────────────────►│
  │       可继续多次 WRITE/READ      │
  ├── END ────────────────────────►│
  │◄── ACK(END) ───────────────────┤
  └── 随后才可 OPEN 另一个 Follower
```

- 非目标 Follower 不发 ACK；Follower 不允许主动 OPEN/WRITE/READ。
- 等待超时从本机完整发送结束后开始，发送时间不计入等待 ACK 的预算。
- CRC 或符号窗口失败时，不交付业务数据，由 Leader 超时重发请求。Follower 的 DATA 只在 READ 授权下发送，等待 ACK 超时后保留缓存并发布 REPLY_UNCONFIRMED，不自行发光重传；Leader 重复 READ 时重发缓存回复，避免与 Leader 重发发生半双工冲突。
- 重复 WRITE 再次 ACK，不再次交付；重复 READ 不重复调用上层；重复 DATA 再次 ACK，不重复交付。
- END 使 Follower 清理会话，并在有限时间内缓存结束确认，处理 ACK 丢失后的重复 END。
- END 失败时 Leader 报告失败并保留当前会话，允许上层重试结束，不直接切换其他机器人。
- 硬件失联、空闲会话超时会异常终止并报告。数据提供超时发送 ERROR，不构造虚假业务数据。
- 去重是进程内、会话内机制，第一版不承诺进程崩溃重启后的持久化“恰好一次”。

## 同步、发送和视觉

默认 T=0.4 秒。每帧为：

```text
灭灯保护间隔 2T
→ [蓝高 T、灭灯 T] 重复三次
→ 数据符号，每符号 T
→ 灭灯保护间隔 2T
```

正文按固定时间窗口读取，连续相同符号也分别采样。例如 0000 是两个蓝高符号，不能仅通过颜色变化计数。

接收以本地到帧时间建立参考点，使用各符号中间 60% 时间窗口投票，默认至少 2 帧、65% 一致。发送调度错过期限会中止该帧并进入有限重试，避免跳过状态后仍假装发送成功。收完帧后再等待转向间隔，覆盖对方尾部保护时间，再回复。

本机发送期间忽略本机相机；接收期间本机灯灭。底层复用 LightStripCommand 的常亮/关闭状态，由通信调度器换符号，不使用原生 BLINK 模式传数据。一个机器人只由本通信节点控制左右灯带。

视觉用 NumPy，对 RGB 通道的背景变化取绝对值，因此较暗彩灯替代较亮的灭灯网格时也能识别；无需 OpenCV 目标检测：启动后先灭灯等待 3 秒，再采集 8 帧静态背景，按蓝/绿通道优势、亮度变化和像素数量判断。它只是本地灭灯背景估计，不改变预定码表，也不在握手里发送颜色标定。图像不确定时输出 UNKNOWN，不硬猜 bit。

发射亮度默认高=1.0、低=0.05，蓝绿 RGB 见 symbols.yaml。接收阈值是相机图像像素值，不等于发射功率：vision.yaml 的 high_threshold 默认 170，附近保留 UNKNOWN 区间，真实窗口运行时需观察亮度诊断后调整。HDR、曝光和水体条件下默认阈值尚未在本地 Windows 图形环境验证。

## 三机器人场景

- leader：(-0.5,0,1.5)，面向 +X；follower_1、follower_2：(0.5,-0.25,1.5)、(0.5,0.25,1.5)，面向 -X。2026-11-02 缩短通信距离：Leader 到每台 Follower 的中心距离约 1.03 米（原约 2.28 米），两个 Follower 中心间距 0.50 米。
- 模板 fixed=true，不启动运动控制。仅保留本轮需要的 RGB 和灯带，复用现有网格。
- 通信场景的八颗灯珠与单机器人 `bricsbot_reference.scn` 使用相同坐标：x=-0.12、-0.04、0.04、0.12，左右 y=±0.02，z=-0.04，半径 0.012。2026-11-02 按用户要求恢复左右两排布局，取消此前机头前方的布局。是否被机体遮挡，必须从接收机器人的 RGB 图像确认。
- 三台共 24 个原生点光源，各自独立名称与外观名称，避免重复注册。
- 每机 RGB 为 /<vehicle_name>/rgb/image_color；LED 为 /<vehicle_name>/lights/{left,right}/cmd。
## 构建与运行

前提：补丁版 Stonefish 已安装，原灯带 appearance_supported 为 True。引擎安装方式见 [灯带与引擎说明](2026-10-28-led-strip-control.md)。

在 catkin 工作空间根目录执行（代码仓库位于其 src/AquaStonefishSim）：

```bash
source /opt/ros/noetic/setup.bash
rosdep install --from-paths src --ignore-src -r -y
catkin build optical_comm --force-cmake --cmake-args \
  -DStonefish_DIR=/usr/local/lib/cmake/Stonefish
source devel/setup.bash
export LD_LIBRARY_PATH="/usr/local/lib:${LD_LIBRARY_PATH:-}"
```

先启动三个静止机器人和通信组件：

```bash
roslaunch optical_comm three_robot_comm.launch
```

默认会启动两个 Follower 的示例上层数据提供器：分别回传 1010101010 和 0011001100。这些固定内容只在 communication_demo 中，不在通信组件中。接实际业务时使用 `start_demo_providers:=false`，由自己的上层响应 DATA_REQUEST。

另开终端加载同一工作空间后，运行 Leader 示例：

```bash
rosrun optical_comm communication_demo.py \
  --role leader --vehicle leader --peers 2,3 --payload 00011011
```

示例依次与 2、3 建联，每次写入 payload、请求回传、确认并 END 后切换。一次光学完整会话包含同步头和协议开销，耗时会明显多于 8bit 业务本身；日志和事件用于观察进度。示例默认从组件 state 的 operation_wait_bound 推导最坏重试等待预算，也可通过 --timeout 显式调整。出现失败时停止，不跨过未结束的会话强行切换。默认 T=0.4 时，示例单个目标的无重试波形合计约 134 秒，另有转向和处理时间；两个目标需要数分钟，不能按 8bit 业务净长度估算完整握手耗时。

可以降低图形质量：

```bash
roslaunch optical_comm three_robot_comm.launch graphics_quality:=low
```

本入口独立加载通信场景，不需要同时启动 tracking_urchin.launch 或手动灯带发布器。

### 本机 ROS 业务接口

每台机器人都有独立命名空间，例如：

```text
/leader/optical_comm/request        optical_comm/CommRequest
/leader/optical_comm/event          optical_comm/CommEvent
/leader/optical_comm/state          std_msgs/String，JSON，锁存
/leader/optical_comm/observation    std_msgs/String，JSON
```

Follower 路径分别替换为 follower_1、follower_2。

CommRequest：

| 字段 | 含义 |
|---|---|
| operation | OPEN=1、WRITE=2、READ=3、END=4、PROVIDE=5 |
| peer_id | Leader 要连接/操作的目标；会话内可为 0 表示当前目标 |
| bits | 业务 bit 或 READ 请求 bit；OPEN/END 必须空 |
| request_id | 上层关联 ID；PROVIDE 必须填写 DATA_REQUEST 事件中的 token |

CommEvent：kind、node_id、peer_id、request_id、bits、detail 和本地 ROS 日志时间。常用事件为 SESSION_OPENED、WRITE_CONFIRMED、DATA_RECEIVED、DATA_REQUEST、READ_COMPLETED、REPLY_CONFIRMED、REPLY_UNCONFIRMED、SESSION_ENDED、RETRY、FAILED、REJECTED、SESSION_EXPIRED、SESSION_LOST。FRAME_SENT 只表示本机波形调度完成，不代表对端确认。

Follower 上层收到 DATA_REQUEST 后，通过它自己的 request 话题发送 PROVIDE。它不能直接向 Leader 发 ROS 数据；随后由通信组件把 bits 转成灯光回传。Leader 的 READ_COMPLETED 或 Follower 的 DATA_RECEIVED 才交付业务数据。

手工建立会话示例：

```bash
rostopic pub -1 /leader/optical_comm/request optical_comm/CommRequest \
  "{operation: 1, peer_id: 2, bits: '', request_id: 'open-2'}"
rostopic echo /leader/optical_comm/event
```

在看到对应 SESSION_OPENED 后再提交 WRITE/READ；忙时提交新操作会 REJECTED。END 需要独立请求 operation=4。

## 配置和排查

| 文件 | 主要参数 |
|---|---|
| robots.yaml | leader_id、允许目标 peers；各节点 node_id、role、vehicle_name 由 launch 注入 |
| symbols.yaml | codec，符号 RGB 与发射 brightness |
| timing.yaml | period、保护间隔、投票窗口、turnaround_symbols、tick_hz、启动等待 |
| protocol.yaml | ACK/READ 超时、上层响应超时、重试次数、空闲会话超时、载荷上限 |
| vision.yaml | 背景帧数、颜色通道比、变化阈值、明暗分界和不确定区间 |

ack_timeout/read_timeout 配置为 0 时由 runtime_config.py 根据当前 T、码表、最长帧及上层处理时间推导。END 缓存按实际配置的 ACK 超时和重试次数校验，不只按最小推导值校验。显式配置小于安全下限会拒绝启动。提高载荷上限或 T 时也要调整 session_timeout、closed_cache_time 和上层示例等待上限。

换为单色两档 1bit 编码：三个节点使用同一 codec=blue_level_1bit，其余协议逻辑不变；T 和视觉判定也须配置匹配。不支持一方独自切换码表。

```bash
rostopic echo /leader/optical_comm/state
rostopic echo /follower_1/optical_comm/state
rostopic echo /leader/optical_comm/observation
rostopic echo -n 1 /leader/lights/left/cmd/appearance_supported
```

- ready=false：先检查引擎能力、相机话题、启动等待和背景采集；缺少外观接口时不会降级为不可靠的通信。
- observation 一直 OFF：检查是否能从对应 RGB 图像看到前部灯珠、minimum_change 和 min_pixels。
- 高低档都变成 HIGH：查看 brightness 诊断，调整发射低档功率和接收 high_threshold，不能把发射 brightness 数字直接当成像素阈值。
- UNKNOWN 多：检查蓝绿竞争、阈值边界或每周期有效相机帧数；T 太短时增加周期。
- RX_REJECTED：查看置信度、调度迟到、CRC 或同步窗口信息；不会把失败帧交给上层。
- 当前时间适配是每机本地 monotonic 到帧时间。仿真暂停、相机停流或长时间卡顿会使等待超时，第一版不保证暂停后续传，恢复后按状态重新建立会话。

## 验证与维护记录

### 实施计划

- [x] 1. codecs、帧和 CRC：映射替换、奇数 bit、错误 CRC、超过 20bit 和超长输入。
- [x] 2. 协议状态机：非目标静默、丢 ACK 去重、READ 上层回调、END 重试和切换目标。
- [x] 3. 时间调度与 RGB 接收：相对时钟、重复符号、图像不确定拒绝、实际图像到帧恢复。
- [x] 4. ROS 适配、配置、三机器人场景和上层示例。
- [x] 5. 独立审查和最终验证记录；重要问题通过失败回归测试后修复。
- [ ] 目标 Linux catkin 构建及 Stonefish 窗口光学通信验收。

实现沿用用户指定工作区，未创建额外工作树，未提交或推送。功能分层已由用户确认；帧字段、周期默认值、背景估计和转向间隔是本轮实现决定，后续变更记在本文件。

### 本地测试

在代码仓库根目录执行：

```bash
PYTHONPATH=src/algorithm/optical_comm/src \
  python3 -B -m unittest discover -s src/algorithm/optical_comm/test -p 'test_*.py'
python3 -B -m unittest discover -s src/aquaflow_stonefish/test -p 'test_*.py'
```

当前 29 项通信测试、原有 5 项灯带测试通过。三节点端到端测试将发送波形转换为测试 BGR 图像，三个接收器通过同一个视觉、同步、采样、帧解析和协议流程恢复消息，并验证不同本地时钟、非目标静默、完整读写和 END 后切换；没有把发送帧直接传给接收协议。额外的全图像故障用例遮断首个 Follower DATA，验证由 Leader 再次 READ 授权回传后恢复，且全过程没有两个同时发光的发送者。测试图像仍是可控输入，不等同于真实 Stonefish 渲染图像。

Python、YAML、XML/launch 及场景资源解析检查通过。Windows 本地没有 ROS/catkin 和完整 Linux OpenGL 环境，因此未声称完成消息生成、ROS 启动或实际画面通信验收。目标机仍需逐项确认 ready、四态图像亮度、寻址静默、读写、丢帧重试、END 和目标切换。

### 独立审查及实现决定

审查发现并修复：长 DATA 独立重试会与 Leader READ 重试冲突；END 缓存校验忽略显式长 ACK 超时；Leader 单独重启可能误复用旧会话。对应回归测试均先复现失败，再修复通过。补充修复 DATA ACK 丢失后 Leader 继续新操作被旧 pending 阻塞，以及低亮度彩灯被误判 OFF。计数参数也已拒绝 NaN、非整数和布尔值，避免无界重试或采样阶段异常。

采用单独的 32bit Leader 启动标识后，单端重启不会将旧缓存业务误确认成新交付；第一版不自动接管旧会话。遇到忙会话请等待其超时或重启整组通信节点再建联，不承诺跨进程崩溃的持久化恰好一次。随机标识并非认证机制。

本轮实现决定：固定短帧格式和默认 256bit 上限、T=0.4、低档亮度 0.05、灭灯背景估计、每帧重新同步及转向保护时间。这些值均有配置或独立模块；若目标渲染下不适合，需要调配置并重新做画面验收，不能以软件测试代替实际接收效果。默认本地单调时钟在仿真暂停期间继续走时，因此暂停/卡顿按失联超时处理。

### 变更记录

- 2026-10-30：新增 optical_comm 包、静态三机器人场景、ROS 上层接口、示例与初版测试；建立本维护文档。

### 本轮最终检查（2026-10-30）

- `python -B -m pytest -q -p no:cacheprovider src/algorithm/optical_comm/test src/aquaflow_stonefish/test`：34 项通过（29 通信＋5 原灯带）。
- 新包 26 个 Python 文件 AST、5 个 XML/launch 文件、全部 YAML、README 和维护文档链接检查通过。
- ROS 适配模块可在未安装 ROS 的 Python 环境导入，未实例化 ROS 节点；不能据此声称实际 ROS 消息生成或节点运行通过。
- 默认波形时长计算：ACK 等待下限 14.6 秒、READ 等待预算 96.2 秒；单个示例会话波形合计 133.6 秒，不含转向和处理。
- 独立审查的三项重要问题及补充回归已完成修复，未留下需要忽略的重要问题；Git diff 格式检查通过。
- 未提交或推送。本地检查不替代目标 Linux、RGB 渲染和人工画面验收。

### 灯带布局与 OPEN 超时排查（2026-11-02）

本次仅调整通信演示的场景与启动配置，不改原单机器人跟踪场景、不改协议或 Stonefish 源码。

- `bricsbot_optical_reference.scn`：恢复原单机器人左右两排灯珠的坐标；功率上限由 include 参数 `led_illuminance` 传入。
- `three_robot_optical_comm.scn`：为三台机器人传入同一个功率上限，读取 ROS 参数 `/optical_comm/led_illuminance`。
- `three_robot_comm.launch`：新增启动参数 `led_illuminance`，默认 500.0，原默认为 100.0。灯珠半径与三台机器人的位姿不变。
- `symbols.yaml` 的亮度比例保持高档 1.0、低档 0.05，因此每颗灯在默认配置下，高档功率上限为 500，低档为 25，均为原来的 5 倍。这是引擎输入功率的比例，不代表图像像素亮度也线性增加 5 倍。

重新启动仿真后生效；本次没有 C++ 或消息定义变化，源码工作空间中通常不需要重新编译，使用 install 空间时需要更新对应安装资源。

```bash
roslaunch optical_comm three_robot_comm.launch led_illuminance:=500.0
```

可以调小以避免高低档都过曝；也可以用更高值测试外观，但必须重新检查四种符号的接收结果。功率不能补偿灯珠被外壳遮挡的问题。恢复原左右两排布局是外观要求，不代表已经验证这些位置适合当前面对面的相机通信。

#### FRAME_SENT 后出现 RETRY 的含义

`FRAME_SENT ... OPEN` 表示 Leader 本地完成了 OPEN 波形调度，不证明相机看到了正确灯光。`RETRY ... OPEN` 表示在当前 ACK 等待期限内没有收到有效确认。两条日志不足以确定是正向 OPEN 未识别，还是反向 ACK 未识别，不能据此认定只是亮度不够或等待时间太短。

先只与机器人 2 测试，启动后先确认三台节点 ready，再执行：

```bash
rosrun optical_comm communication_demo.py --role leader --vehicle leader --peers 2 --payload 00011011
```

在不同终端观察：

```bash
rostopic echo /follower_1/optical_comm/state
rostopic echo /follower_1/optical_comm/observation
rostopic echo /follower_1/optical_comm/event
rostopic echo /leader/optical_comm/observation
```

用 `rqt_image_view` 选择 `/follower_1/rgb/image_color` 看实际接收画面；主仿真窗口看到灯亮，不代表这个相机也能看到。检查顺序如下：

1. Follower 的 ready 应为 true。灯光后端能力不支持、相机未采集背景等都会阻止正常应答。
2. Leader 发同步头时，Follower 的 observation 应出现 BLUE_HIGH 与 OFF 交替。一直 OFF 时先检查相机视野、机体遮挡和有效彩色像素数量；不要先盲目缩短超时或改变协议。
3. 发数据时，应能分别识别 BLUE_HIGH、BLUE_LOW、GREEN_HIGH、GREEN_LOW。若高低档都成 HIGH 或低档成 OFF，结合 brightness 数值调发送功率比例与 vision.yaml 的 high_threshold；固定阈值 170 尚未经本机真实渲染标定。
4. Follower 出现 SESSION_OPENED、随后 FRAME_SENT/ACK，说明已识别正向 OPEN；此时 Leader 仍重试，应检查 Leader 相机的反向 ACK 识别。
5. Follower 出现 RX_REJECTED 时，查看 detail；unreliable symbol window 表示符号采样不足或不稳定，CRC 错误则表示解码后的帧校验失败。也可用 `rostopic hz /follower_1/rgb/image_color` 检查相机实际帧率：T=0.4 秒的中央采样窗口只有 0.24 秒，需要至少两帧，标称 15 Hz 不等于实际始终达到 15 Hz。

本地只能检查配置、资源和软件测试；OPEN 超时是否解除，仍需目标 Linux 机器人的 RGB 图像与上述事件验证。

### 近距离通信场景调整（2026-11-02）

按用户要求先缩短距离排查 OPEN 无 ACK：仅修改 `three_robot_optical_comm.scn` 中三台机器人的位置，保留深度、朝向、固定状态、灯带布局和功率配置。Leader 到 Follower 的中心距离由约 2.28 米缩短到约 1.03 米。场景已配置每台机器人自己的 RGB 相机（640×480、15 Hz、水平视场 70°），通过模板分别发布 `/leader/rgb/image_color`、`/follower_1/rgb/image_color`、`/follower_2/rgb/image_color`；相机声明存在不代表目标机器上实际有图像，需要用 `rostopic hz /follower_1/rgb/image_color` 或 rqt_image_view 验证。

关闭旧仿真与 Leader 演示脚本，重新启动 `roslaunch optical_comm three_robot_comm.launch`，然后先用 `--peers 2` 测试。缩短距离有助于增加灯珠在画面中的像素数量，但不能证明无 ACK 的原因已经解决；若仍重试，继续按上节检查 Follower 的观察和事件以及相机中的遮挡。
