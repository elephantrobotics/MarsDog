# MarsDog 2D ROS2 调试控制台

MarsDog 2D 是一个基于 Python、ROS2 和 Arcade 的室内行为调试界面，用于观察和手动驱动 MarsDog 的感知、内部需求、情绪、性格、行为树决策和动作执行链路。

项目使用 **uv 的 pip 兼容模式**管理 Python 环境和第三方依赖：

- `.python-version` 固定使用 Python 3.10，与 ROS2 Humble ABI 对齐。
- `uv venv` 创建项目内的 `.venv`。
- `uv pip install -r requirements.txt` 安装已导出的固定版本依赖。
- `uv pip freeze > requirements.txt` 记录当前可运行环境。
- `pyproject.toml` 保留项目元数据和 uv 镜像配置，但不是当前依赖安装基准。
- `rclpy`、`std_msgs` 和 MarsDog 接口包仍由 ROS2 环境提供，不从 PyPI 安装。

它不是 Gazebo，也不提供刚体物理、真实导航、碰撞检测或传感器仿真。项目的目标是在一张稳定的室内俯视场景中，把以下信息放到同一个调试工作流里：

- 手动注入感知事件、状态输出、语音指令和组合场景。
- 查看 ROS2 Topic 健康状态和消息频率。
- 查看行为树选择出的 behavior、ACT、阶段、目标和决策链路。
- 通过虚拟 `/execute_behavior` Action Server 演示动作执行与场景移动。
- 连接真实 `marsdog_action_executor` 时，仅作为动作与状态可视化器。
- 通过结构化事件流检查最近事件和原始 JSON Payload。

## 1. 界面概览

界面按调试流程从左到右组织：

```text
输入控制  ->  2D 室内场景  ->  系统状态与决策
                       |
                 事件流与日志
```

### 1.1 顶部 ROS 状态栏

顶部显示以下端点的摘要状态：

- `VIS`：视觉感知。
- `AUDIO`：声音和语音感知。
- `NEED`：内部需求状态与信号事件。
- `EMO`：情绪状态与信号事件。
- `EXEC`：行为 Action Goal、Feedback 和 Result。

状态分为 Live、Stale、Waiting 和 Error。悬浮可查看 Topic、接收数量和最近消息时间。

### 1.2 左侧输入控制

左侧包含四个页签：

- `事件`：注入声音、视觉或行为结果事件。
- `状态`：模拟需求、情绪或性格节点的输出。
- `指令`：注入语音命令，提供坐下、过来、握手、跟随、停止等快捷按钮。
- `场景`：批量执行预设测试场景。

左侧面板可以折叠；内容超出高度时可滚动，不会继续压缩中央场景。

### 1.3 中央 2D 室内场景

中央场景显示：

- 小金毛 MarsDog 当前姿态、位置和朝向。
- 用户、感知目标和手动放置对象。
- 食盆、休息垫、如厕垫、玩具、充电座和护理垫。
- 当前目标、目标连线、规划方向和移动轨迹。
- 可选视野扇形和感知范围。
- behavior、stage、ACT 和 target 状态牌。

点击狗狗、用户或场景物品可查看对象详情。

### 1.4 右侧系统状态

右侧依次显示：

- `当前行为`：behavior、ACT、阶段、进度、目标、执行状态和是否可中断。
- `决策链路`：触发事件、意图、behavior、等级、交互模式和最终 ACT。
- `需求状态`：需求值、等级、事件和主导需求。
- `情绪状态`：主导情绪、区间、信号事件和其他情绪值。
- `感知摘要`：人、动物、物体、活动目标、置信度和声源。

状态卡可以折叠，右侧区域支持滚动。点击当前行为卡可展开完整执行上下文。

### 1.5 底部事件流

事件流支持：

- 按 `VIS / AUD / NEED / EMO / BEH / EXEC / RESULT / SYS` 过滤。
- 搜索、暂停、清空和自动滚动。
- 折叠连续重复事件，例如 `visual_event: no_event x 43`。
- 点击事件查看和复制原始 Payload。
- 拖动顶部把手调整日志区域高度。

## 2. 系统架构

```text
Perception / Need / Emotion / Personality
                  |
                  | std_msgs/String(JSON)
                  v
             RosBridge (rclpy)
                  |
                  | queue.Queue
                  v
          SimState (Arcade 主线程)
             |             |
             v             v
        WorldRenderer   StatusWidgets

Behavior Tree
      |
      | /execute_behavior Action
      v
VirtualActionServer 或真实 Action Executor
      |
      | /debug/execute_behavior/*
      v
    调试界面
```

Arcade 窗口和所有绘制都运行在主线程。ROS2 使用后台 `MultiThreadedExecutor`，回调只负责解析消息并写入线程安全队列，避免 ROS 高频消息直接阻塞 UI。

手动注入采用相反方向：

```text
UI 表单 -> InjectionCommand -> RosBridge Publisher -> ROS2 Topic -> 下游节点
```

## 3. 项目结构

```text
.
├── main.py                         # 源码目录启动入口
├── .python-version                 # uv 使用的 Python 3.10 版本约束
├── package.xml                     # ROS2 ament_python 包定义
├── pyproject.toml                  # uv 镜像、Python 版本和项目元数据
├── requirements.txt                # uv pip freeze 导出的固定依赖
├── uv.lock                         # uv 项目模式锁文件，当前安装流程不依赖它
├── setup.py                        # ROS2 安装和资源打包
├── marsdog_sim2d/
│   ├── arcade_viewer_node.py       # Arcade 窗口、交互和主入口
│   ├── config.py                   # 布局、颜色、Topic 和场景锚点
│   ├── drawing.py                  # 文本绘制辅助
│   ├── event_injector.py           # 手动注入、数值推导和场景模板
│   ├── parsers.py                  # ROS2 JSON 消息解析
│   ├── renderer.py                 # 室内场景和动态对象渲染
│   ├── ros_bridge.py               # ROS2 订阅、发布和线程桥接
│   ├── sim_state.py                # UI 线程状态与事件缓存
│   ├── virtual_executor.py         # 虚拟 Action Server 和动作脚本
│   ├── widgets.py                  # 左右面板、顶部状态和事件流
│   └── assets/
│       ├── backgrounds/            # 室内底图原图与运行时纹理
│       └── dog/                    # 六种透明背景小金毛姿态
└── tests/
    ├── test_state_output_mapping.py
    └── test_virtual_scene_alignment.py
```

## 4. 环境要求

- Linux 桌面环境或可用的 X11/Wayland Display。
- ROS2 Humble，或与当前 ROS2 工作区一致的 ROS2 发行版。
- Python 3.10 及以上；ROS2 Humble 通常使用 Python 3.10。
- `uv`，本项目默认的 Python 环境和依赖管理工具。
- `rclpy`、`std_msgs`。
- `arcade>=3.3.3`。
- 使用虚拟 Action Server 时，需要可导入的 `ExecuteBehavior` Action 类型，优先来自 `marsdog_interfaces`。

不要把 ROS2 Humble 的 Python 3.10 `rclpy` 二进制扩展与 Python 3.12 虚拟环境混用。出现 `ModuleNotFoundError: rclpy` 或二进制 ABI 错误时，应检查当前 Python 是否来自正确的 ROS2 环境。

## 5. uv pip 环境、安装与启动

### 5.1 安装 uv

Linux/macOS 可使用 uv 官方安装器：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

也可以通过隔离的 pipx 环境安装：

```bash
pipx install uv
```

确认安装结果：

```bash
uv --version
```

安装方式可参考 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。

### 5.2 uv pip 快速开始（推荐）

先 source ROS2 和 MarsDog 工作区，使虚拟环境中的 Python 能通过 `PYTHONPATH` 找到 `rclpy` 和接口包：

```bash
source /opt/ros/humble/setup.bash
source ~/marsdog_ws/install/setup.bash

cd /path/to/MarsDog2D
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt
python main.py
```

首次创建环境时，以上命令会：

- 根据 `.python-version` 选择 Python 3.10。
- 创建项目内的 `.venv`。
- 严格按照 `requirements.txt` 中的固定版本安装 Arcade 及其依赖。
- 保留 ROS2 source 写入的 `PYTHONPATH`，从系统 ROS2 环境加载 `rclpy`。

已有 `.venv` 时不需要重复执行 `uv venv`，只需激活环境并根据 requirements 安装或检查依赖。

安装完成后可验证 ROS2 和图形依赖：

```bash
python -c "import arcade, rclpy; print(arcade.__version__); print(rclpy.__file__)"
```

本项目以源码应用方式运行，激活环境后使用 `python main.py`。不要使用 `uv run marsdog-sim2d`；当前 uv 配置不安装项目脚本入口，`marsdog-sim2d` 仅是预留的项目元数据。

如果主目录下的 uv 缓存不可写，可以临时指定缓存位置：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv pip install -r requirements.txt
python main.py
```

### 5.3 不激活虚拟环境的运行方式

也可以显式指定 `.venv` 解释器，并禁止 `uv run` 自动执行项目模式同步：

```bash
uv pip install --python .venv/bin/python -r requirements.txt
uv run --no-sync python main.py
```

这里的 `--no-sync` 很重要。普通 `uv run` 会根据 `pyproject.toml` 和 `uv.lock` 检查项目环境，而当前项目实际使用的是 `uv pip + requirements.txt`；自动同步可能删除 requirements 中存在、但没有直接写入 `pyproject.toml` 的包。

### 5.4 uv pip 依赖维护

常用命令：

```bash
# 激活项目环境
source .venv/bin/activate

# 从导出的依赖文件安装
uv pip install -r requirements.txt

# 将环境精确同步为 requirements.txt，删除未声明的额外包
uv pip sync requirements.txt

# 添加或升级包
uv pip install <package>

# 删除包
uv pip uninstall <package>

# 导出当前完整环境
uv pip freeze > requirements.txt

# 查看和检查当前环境
uv pip list
uv pip check

# 在项目环境中运行测试
python -m unittest discover -s tests -v
```

安装、升级或删除依赖后，应重新执行 `uv pip freeze > requirements.txt` 并提交更新后的文件。当前工作流以 `requirements.txt` 为准，不要求执行 `uv lock` 或 `uv sync`。

ROS2 Python 包是例外：`rclpy`、`std_msgs`、`marsdog_interfaces` 等来自 `/opt/ros/<distro>` 和已 source 的工作区，不应添加为普通 PyPI 依赖。当前 `.venv` 即使设置了 `include-system-site-packages=false`，也能通过 ROS2 设置的 `PYTHONPATH` 导入这些包。

### 5.5 ROS2 工作区安装

将项目放入 ROS2 工作区的 `src` 目录，然后执行：

```bash
source /opt/ros/humble/setup.bash
uv pip install --python /usr/bin/python3 -r requirements.txt

cd ~/marsdog_ws
colcon build --symlink-install --packages-select marsdog_sim2d
source install/setup.bash
ros2 run marsdog_sim2d arcade_viewer_node
```

修改源码后，通过 `ros2 run` 启动前需要重新构建并重新 `source install/setup.bash`。

`ros2 run` 使用 ament/colcon 安装的 Python 入口，不使用项目 `.venv`。因此这种部署方式仍需确保 ROS2 使用的 Python 环境能够导入 Arcade。日常开发建议使用上一节的 uv 源码运行方式。

将依赖写入 `/usr/bin/python3` 对应环境时可能需要系统权限；不希望修改系统 Python 时，直接使用 5.2 节的 `.venv` 源码运行方式。

### 5.6 源码目录开发运行

```bash
source /opt/ros/humble/setup.bash
source ~/marsdog_ws/install/setup.bash

cd /path/to/MarsDog2D
source .venv/bin/activate
uv pip install -r requirements.txt
python main.py
```

`uv` 环境仍然必须能够导入当前 ROS2 的 `rclpy` 和接口包。

## 6. 运行模式

### 6.1 模式 A：虚拟 Action Server

这是默认模式。界面注册 `/execute_behavior` Action Server，把行为树 Goal 转换为轻量级室内动作脚本。

```bash
uv run --no-sync python main.py
```

适用于：

- 没有真实运动控制器时调试行为树。
- 检查 behavior、ACT、stage、target 和反馈链路。
- 演示进食、睡眠、如厕、互动、探索、护理和充电行为。

同一 ROS Domain 中只能有一个 `/execute_behavior` Server。启用本模式时，不要同时启动真实 `marsdog_action_executor`。

### 6.2 模式 B：仅可视化真实执行器

连接真实 `marsdog_action_executor` 时，关闭本项目的 Action Server：

```bash
MARSDOG_SIM2D_ACTION_SERVER=0 \
uv run --no-sync python main.py
```

界面仍会订阅 `/debug/execute_behavior/*` 和兼容调试 Topic，并用真实反馈驱动状态面板和动画。

### 6.3 模式 C：本地动画自测

窗口内快捷键可绕过行为树和 ROS Action，直接启动 `LocalVirtualRunner`：

| 按键 | 行为 |
|---|---|
| `T` | `exploreRoom` |
| `F` | `seekFood` |
| `S` | `sleepNow` |
| `C` | `seekInteraction` |
| `W` | `wagTailFast` |
| `P` | `spinInCircle` |
| `G` | `cleanSelf` |
| `E` | `defecate` |
| `R` | `recharge` |
| `H` | `hideAway` |

本地动画自测只验证渲染和房间移动，不代表行为树、Action Client 或取消链路正常。当前 `LocalVirtualRunner` 没有连接 UI `CMD_STOP` 的取消接口。

## 7. ROS2 接口

### 7.1 Topic

所有 Topic 都使用 `std_msgs/msg/String`，`data` 必须是 JSON Object。

| Topic | UI 方向 | QoS | 用途 |
|---|---|---|---|
| `/perception/visual_event` | 订阅、可注入 | BEST_EFFORT, depth 5 | 人、手、动物、物体和视觉事件 |
| `/perception/audio_event` | 订阅、可注入 | RELIABLE, depth 10 | 唤醒、声纹、ASR 和语音命令 |
| `/internal_need/state` | 订阅、可模拟输出 | RELIABLE, depth 10 | 七类需求快照和睡眠状态 |
| `/internal_need/signal_event` | 订阅、可注入 | RELIABLE, depth 10 | 需求等级变化事件 |
| `/emotion/state` | 订阅、可模拟输出 | RELIABLE, depth 10 | 六类情绪、主导情绪和区间 |
| `/emotion/signal_event` | 订阅、可注入 | RELIABLE, depth 10 | 情绪区间变化事件 |
| `/behavior/result_event` | 订阅、可注入 | RELIABLE, depth 10 | 行为结果及需求/情绪结算输入 |
| `/personality/state` | 订阅、可模拟输出 | RELIABLE, TRANSIENT_LOCAL, depth 1 | 性格 Profile、A/O/E/C 和系数 |

### 7.2 Action

| Action | 方向 | 用途 |
|---|---|---|
| `/execute_behavior` | 行为树 Client -> 虚拟或真实 Server | 执行 behavior 并返回 Feedback/Result |

手动测试示例：

```bash
ros2 action send_goal \
  /execute_behavior \
  marsdog_interfaces/action/ExecuteBehavior \
  "{goal_id: 'sim_test_001', behavior_name: 'seekFood', priority_level: 4, params_json: '{}', timeout_sec: 4.0}" \
  --feedback
```

常见 behavior 包括：

- `eatNormally`、`eatExcitedly`、`seekFood`。
- `defecate`、`sleepNow`、`cleanSelf`、`recharge`。
- `exploreRoom`、`inspectObject`。
- `seekHumanInteraction`、`expressJoy`。
- `CMD_SIT`、`CMD_HAND`、`CMD_FOLLOW` 等命令行为。

旧名称通过可视化别名映射兼容，但真实执行器是否接受某个名称，应以其 behavior catalog 为准。

### 7.3 Action 调试 Topic

当前调试前缀：

- `/debug/execute_behavior/goal`
- `/debug/execute_behavior/feedback`
- `/debug/execute_behavior/result`

界面也会订阅兼容 Topic：

- `/execute_behavior/goal`
- `/execute_behavior/feedback`
- `/execute_behavior/result`

重复消息会自动过滤。虚拟 Server 默认只发布当前 `/debug/execute_behavior/*` Topic。如需同时发布旧兼容 Topic：

```bash
MARSDOG_LEGACY_DEBUG_TOPICS=1 uv run --no-sync python main.py
```

兼容环境变量 `MARSDOG_COMPAT_DEBUG_TOPICS=1` 也会开启相同行为。

## 8. 手动输入与事件注入

### 8.1 事件页签

事件来源包括：

- `声音`：配置事件类型、ASR 文本、命令 ID、说话人、置信度和声源角度。
- `视觉`：配置视觉事件、身份、姿态和物体标签。
- `行为结果`：配置 `ACTION_*`、需求类型、结果类型和 metadata。

表单会显示发布 Topic 和 JSON Payload 预览。发送前可确认实际字段，不会修改 Topic 名称或消息结构。

视觉目标可以先选择“在场景中放置”，再点击地图。声音事件可以点击地图确定声源位置，界面会根据狗狗朝向推导 `wake_angle`。发送前对象以虚线和半透明预览显示，发送后才成为正式目标。

### 8.2 状态页签

#### Need

用户只输入需求类型和 `0-100` 数值，等级与信号事件按文档阈值自动推导，不能手动制造“数值与等级冲突”。

| Demand | TRIGGERED | OVERFLOW |
|---|---|---|
| Hunger | `value > 70` | `value > 90` |
| Bladder | `value > 75` | `value > 90` |
| Sleepiness | `value > 65` | `value > 90` |
| Cleanliness | `value > 70` | `value > 90` |
| Energy | `value < 20` | `value < 10` |
| Social | `value > 60` | `value > 90` |
| Exploration | `value > 60` | `value > 90` |

Need 注入会发布：

- `/internal_need/state`
- `/internal_need/signal_event`

#### Emotion

| Emotion | NONE | LOW/NORMAL | MID | HIGH |
|---|---|---|---|---|
| Calm | - | `NORMAL 0-60` | - | `61-100` |
| Joy | `0-29` | `LOW 30-60` | `61-85` | `86-100` |
| Excite | `0-39` | `LOW 40-70` | - | `71-100` |
| Anxiety | `0-24` | `LOW 25-50` | - | `51-100` |
| Fear | `0-29` | `LOW 30-60` | - | `61-100` |
| Curious | `0-19` | `LOW 20-50` | - | `51-100` |

Emotion 始终发布 `/emotion/state` 快照。只有数值处于文档定义区间时才发布 `/emotion/signal_event`；NONE 区间不会伪造不存在的 `EMO_*_NONE` 事件。

#### Personality

Personality 注入发布 `/personality/state` 快照，可编辑：

- Profile：Custom、GentleCompanion、SunnyExplorer、LoyalGuardian、ProudIndependent。
- 维度：A、O、E、C，范围 `0-100`。

它不会通过参数服务持久修改真实 `personality_node`。

### 8.3 指令页签

支持的 UI 命令选项：

- `CMD_SIT`
- `CMD_COME_HERE`
- `CMD_HAND`
- `CMD_FOLLOW`
- `CMD_STOP`
- `CMD_LIE_DOWN`
- `CMD_SPIN`
- `CMD_FETCH`

指令页签发布的是 `/perception/audio_event`，其中包含 `EVT_VOICE_COMMAND_KNOWN`、`command_id`、ASR 文本、说话人和置信度。

重要：点击 `CMD_STOP` 只表示“向行为树注入停止语音事件”，它不会由 UI 直接取消当前 `/execute_behavior` Goal。完整停止链路应由行为树保存当前 Goal Handle，并调用 Action cancel；发送新的 `CMD_STOP` Goal 也不等于取消旧 Goal。

### 8.4 场景页签

| 场景 | 注入内容 |
|---|---|
| 高饥饿 | Hunger=94，触发觅食 |
| 低能量 | Energy=7，触发充电 |
| 主人呼叫 | 主人视觉目标 + 呼名声音事件 |
| 快乐互动 | 主人视觉目标 + Joy=88 |
| 恐惧反应 | 陌生人视觉目标 + Fear=86 |
| 探索玩具 | 玩具视觉目标 + Exploration=78 |

高风险或满溢类注入需要二次确认。

### 8.5 输入操作

- 点击字段后直接输入文本。
- `Backspace` 删除一个字符。
- `Delete` 清空当前字段。
- `Tab` 切换到下一个字段。
- `Enter` 发送当前表单。
- `Esc` 关闭选择面板或取消确认。

## 9. 状态注入边界

`/internal_need/state`、`/emotion/state` 和 `/personality/state` 是计算节点的输出 Topic，不是 Setter API。

因此：

- 手动状态快照可以被行为树等订阅者消费。
- 它不会直接修改需求、情绪或性格节点的内部变量。
- 真实节点下一次周期输出可能立即覆盖手动快照。
- 真正影响事件驱动行为树的通常是对应 `signal_event`。
- 持久修改性格应使用 personality 节点提供的参数或服务接口。

为了避免调试面板被自己的输出污染，界面不会把自身发布的 Need/Emotion state echo 当作真实引擎状态更新仪表；signal event 仍会正常进入 ROS2 链路。

## 10. 虚拟动作与场景表现

### 10.1 动作阶段

虚拟执行器把 behavior 转换为位置、朝向、目标和 ACT。Feedback 以 10 Hz 更新。

若真实 Feedback 提供 `stage_index`、`stage_total` 和 `stage_label`，界面直接使用真实值；缺少这些字段时，界面会估算三阶段：

1. approach
2. interaction/action
3. settle

`safe_to_interrupt` 是执行器反馈出的当前可中断状态。界面只负责显示，不会因为字段变为 `true` 自动发起 cancel。

### 10.2 狗狗姿态

场景包含六种透明背景小金毛素材：

- stand
- walk
- sit
- lie
- play bow
- raised paw

渲染器根据当前 ACT 选择姿态。例如睡眠使用 lie，握手使用 raised paw，邀玩使用 play bow。素材位于 `marsdog_sim2d/assets/dog/`。

### 10.3 室内底图与锚点

- 原始室内图：`marsdog_sim2d/assets/backgrounds/apartment_floorplan_source.png`
- Arcade 运行时纹理：`marsdog_sim2d/assets/backgrounds/apartment_floorplan_runtime.png`

运行时使用较小纹理兼容软件 OpenGL/llvmpipe。加载失败时，渲染器回退到程序化室内布局。

场景对象坐标集中定义在 `config.DEFAULT_ROOM_OBJECTS`。食盆、狗窝、玩具、厕所、护理和充电行为使用同一组逻辑锚点，避免 UI 位置与虚拟执行器落点不一致。

用户是稳定场景锚点：移动的视觉检测框只作为观察标记，不会让用户角色漂移。只有手动放置并发送新的 Human Vision 目标时，才会有意更新用户锚点。

## 11. Stop 与行为中断

执行中的睡眠、进食或其他行为应通过 ROS2 Action cancel 中断：

```text
CMD_STOP
  -> Behavior Tree 识别停止命令
  -> cancel 当前 /execute_behavior Goal
  -> Action Server 返回 CANCELED
  -> Behavior Tree 发布 /behavior/result_event
     ACTION_SLEEP + INTERRUPTED/CANCELLED
  -> internal_need.sleep.isSleeping = false
```

排查原则：

- 收到 `CMD_STOP` 但没有 Action `CANCELED`：行为树没有调用 cancel。
- Action 已 `CANCELED`，但没有 `ACTION_SLEEP + INTERRUPTED/CANCELLED`：行为树缺少结果回传。
- 两者都有，但 `sleep.isSleeping` 仍为 true：内部需求节点没有退出睡眠状态。
- 使用键盘 `S` 启动的是本地动画自测，不经过行为树，当前不会被 UI Stop 取消。

虚拟 Action Server 的 cancel callback 会接受取消请求，并在执行循环中返回 canceled；是否发起该请求属于 Action Client/行为树职责。

## 12. 诊断命令

### 12.1 确认状态 Topic

```bash
ros2 topic echo /emotion/state --once
ros2 topic echo /internal_need/state --once
ros2 topic echo /perception/audio_event --once
ros2 topic echo /perception/visual_event --once
```

### 12.2 确认 Action Server

```bash
ros2 action list
ros2 action info /execute_behavior
```

### 12.3 查看执行链路

```bash
ros2 topic echo /debug/execute_behavior/goal
ros2 topic echo /debug/execute_behavior/feedback
ros2 topic echo /debug/execute_behavior/result
ros2 topic echo /behavior/result_event
```

### 12.4 Stop 未打断睡眠

依次确认：

```bash
ros2 topic echo /perception/audio_event
ros2 topic echo /debug/execute_behavior/result
ros2 topic echo /behavior/result_event
ros2 topic echo /internal_need/state
```

预期依次看到 `CMD_STOP`、睡眠 Goal 的 `CANCELED`、`ACTION_SLEEP` 的 `INTERRUPTED/CANCELLED`，最后 `sleep.isSleeping=false`。

## 13. 常见问题

### 窗口启动但没有数据

确认界面和其他节点处于同一个 ROS Domain，并已 source 相同工作区：

```bash
echo $ROS_DOMAIN_ID
ros2 node list
ros2 topic list
```

### 感知变化但狗狗不移动

感知事件只会成为行为树输入，不会直接移动狗狗。检查行为树是否下发 `/execute_behavior` Goal，以及 Action Server 是否存在。

### 出现两个 Action Server

真实执行器和本项目虚拟执行器不能同时注册 `/execute_behavior`。使用真实执行器时设置：

```bash
MARSDOG_SIM2D_ACTION_SERVER=0
```

### `rclpy` 导入失败

先 source ROS2，再确认 Python 版本：

```bash
source /opt/ros/humble/setup.bash
python3 -c "import sys, rclpy; print(sys.version); print(rclpy.__file__)"
```

### 中文显示为方框

安装可用的 CJK 字体，例如 Noto Sans CJK。项目会依次尝试 `Noto Sans CJK SC`、`Droid Sans Fallback` 和 `Arial`。

### 软件 OpenGL 下图片不显示

项目已使用优化底图和独立狗狗纹理图集兼容 llvmpipe。仍有问题时检查 OpenGL 和 Display：

```bash
echo $DISPLAY
glxinfo -B
```

## 14. 测试

运行全部单元测试：

```bash
uv run --no-sync python -m unittest discover -s tests -v
```

运行编译检查：

```bash
uv run --no-sync python -m compileall -q marsdog_sim2d main.py
```

当前测试覆盖：

- Need 阈值、比较运算符和边界值。
- Emotion 区间与 signal event 推导。
- 数值与 level 不冲突。
- 用户锚点不随视觉检测框漂移。
- Follow、Hand、Play Bow 等互动距离。
- 食盆、厕所和安全区的场景落点。
- SimState 与 VirtualRoom 的默认物品坐标一致性。

## 15. 当前限制

- 不是物理仿真器，没有碰撞、动力学和真实导航规划。
- 虚拟移动是面向调试的视觉脚本，不替代机器人底盘控制。
- 尚未调用 `/perception/perception_task` Service。
- 手动状态发布不是需求、情绪或性格计算节点的持久写入接口。
- UI `CMD_STOP` 不会直接调用 Action cancel；取消职责属于行为树/Action Client。
- 本地快捷键动作不经过 ROS2 行为树，也不支持 UI Stop 中断。
- 真实执行器支持的 behavior、ACT 和中断规则应以其 catalog 与运行时 Feedback 为准。

## 16. 开发约束

本项目的 UI 调整遵循以下边界：

- 不修改既有 ROS2 Topic 名称。
- 不修改既有 JSON 字段和消息语义。
- 不把状态输出 Topic 伪装成 Setter。
- 不在 UI 层代替行为树做决策。
- 高频消息通过队列、限量 drain 和日志折叠降低重绘压力。
- 布局、颜色、字号、间距和场景锚点集中在 `config.py`。

## 17. License

Apache-2.0。具体包信息见 `package.xml`。
