# MarsDog 2D 开发指南

## 适用范围

- 本文件适用于仓库根目录及其全部子目录。
- 用户请求、上级指令和更深目录中的 `AGENTS.md` 优先于本文件。
- 修改应围绕当前任务，保留工作区中已有的用户改动，不做无关重构、批量格式化或依赖升级。
- 优先复用现有模块、标准库和已安装依赖；禁止为单次使用提前设计抽象层。

## 项目定位

本项目是面向 MarsDog ROS2 系统的 Arcade 二维调试控制台，不是物理仿真器。它负责：

- 可视化感知、内部需求、情绪、人格和行为执行状态；
- 通过 `std_msgs/msg/String` 承载 JSON 调试协议；
- 提供手动事件注入、场景控制和本地动画自测；
- 可选提供 `/execute_behavior` 虚拟 Action Server；
- 展示真实 Action Executor 发布到 `/debug/execute_behavior/*` 的执行链路。

不得在 UI 层代替行为树做业务决策，也不得把调试显示扩展成底盘、导航或真实设备控制。

## 技术栈与运行环境

- Python 3.10；与 ROS2 Humble 的 Python ABI 保持一致，不混用 Python 3.12 环境。
- ROS2 Humble：`rclpy`、`std_msgs`、`std_srvs`、`marsdog_interfaces`。
- Arcade 3.3.3 及其 Pyglet/OpenGL 运行时。
- 主要目标环境为带可用 X11/Wayland Display 的 Linux 桌面。

常用命令：

```bash
source /opt/ros/humble/setup.bash
# 如使用自定义接口，再 source 对应工作区的 install/setup.bash
source .venv/bin/activate
python main.py
```

ROS2 安装后的入口：

```bash
ros2 run marsdog_sim2d arcade_viewer_node
```

虚拟 Action Server 默认关闭，只有明确需要时才启用：

```bash
MARSDOG_SIM2D_ACTION_SERVER=1 python main.py
```

不得把本地 `.venv`、ROS 安装目录或 `site-packages` 中的临时补丁提交到仓库。图形驱动兼容处理必须是项目内可追踪、可关闭且有文档的实现。

## 架构不变量

### 线程边界

- Arcade 窗口、OpenGL 资源、绘制和 `SimState` 更新只能发生在主线程。
- ROS2 在后台 `MultiThreadedExecutor` 中运行。
- ROS 回调只做消息校验、解析、轻量协议转换和线程安全入队；禁止在回调中绘制或直接修改 UI 状态。
- ROS 到 UI 的数据必须通过 `Queue[SimEvent]`；UI 到 ROS 的注入必须通过 `Queue[InjectionCommand]`。
- 新增长耗时操作时不得阻塞 Arcade 事件循环或 ROS 回调线程。

### 状态与协议

- `SimState` 是 UI 主线程拥有的可变状态；跨线程共享状态必须放在专门的线程安全协调器中。
- ROS JSON 必须先经过 `parsers.py` 归一化为 `SimEvent`，不得在渲染模块中重复解析协议。
- 不得擅自修改既有 Topic、Action、Service 名称、JSON 字段或字段语义。
- 状态 Topic 是观测输出，不是 Setter；手动注入不能伪装成需求、情绪或人格节点的持久写接口。
- QoS 是协议的一部分。修改可靠性、深度或 durability 前必须检查发布端、订阅端和对应测试。
- 高频消息继续使用限量 drain、事件折叠和有界展示缓存，避免为每条消息创建永久 UI 状态。

### 行为执行

- `MARSDOG_SIM2D_ACTION_SERVER=0` 时只镜像真实执行器调试 Topic，不得隐式创建第二个 Action Server。
- 真实执行器支持的 behavior、ACT、取消和中断语义，以真实 catalog 与运行时 Feedback 为准。
- 本地快捷键和 `LocalVirtualRunner` 仅用于动画自测，不得冒充真实 ROS2 执行结果。
- Stop 可以立即终止本地展示；真实 Action cancel 仍由行为树或 Action Client 负责。
- 行为、动作单元和视觉姿态映射变更时，联合检查 `behavior_contract.py`、`action_visuals.py`、`virtual_executor.py`、`sim_state.py` 和相关测试，避免各层映射漂移。

### 喂食握手

- `FeedingCoordinator` 是 UI 与 ROS 桥接共享的线程安全真值来源。
- `/ui/feeding/state` 使用 `RELIABLE + TRANSIENT_LOCAL` 发布状态；`/ui/feeding/try_start_eating` 的本次服务响应是开始进食的最终依据。
- 空盆或等待放粮阶段不得报告进食成功，也不得通知内部需求模块减少饥饿值。
- 只有服务返回 `success=true` 且进食动作实际进入 `RUNNING/STARTED` 后，才能进入进食流程。
- 保留 `DOG_NOT_AT_BOWL`、`NO_FOOD`、`EATING_AUTHORIZED` 等既有原因语义；修改状态机时必须补充竞态和边界测试。

## 模块职责

- `main.py`：源码启动入口，不承载业务逻辑。
- `arcade_viewer_node.py`：窗口生命周期、输入事件、UI 协调和主入口。
- `ros_bridge.py`：ROS 订阅、发布、Service、QoS 和线程桥接。
- `sim_state.py`：主线程状态、事件应用、动画与展示状态机。
- `parsers.py`：外部 JSON 到 `SimEvent` 的协议解析。
- `event_injector.py`：手动注入字段、模板、场景和消息构造。
- `virtual_executor.py`：虚拟 Action Server、动作计划和本地执行器。
- `behavior_contract.py`：行为 Stage、候选动作和 YAML 合同加载。
- `action_visuals.py`：ACT 到视觉姿态、目标和表现的映射。
- `voice_commands.py`：语音命令归一化与映射。
- `feeding_interface.py`：线程安全喂食状态与服务决策。
- `renderer.py`：中央场景渲染与命中测试。
- `widgets.py`：面板、控件、日志和 UI 命中区域。
- `config.py`：Topic、Service、布局、颜色、字号、间距、场景锚点和运行参数。
- `drawing.py`：共享绘制辅助。
- `assets/config/*.yaml`：行为合同数据；资源必须通过 `setup.py` 一并打包。

模块之间通过公开函数、数据类和事件结构协作，禁止跨模块直接依赖对方的私有实现。

## Python 编码规范

### P0：强制禁止

- 禁止裸 `except:` 和无异常变量的 `except Exception:`。
- 能捕获具体异常时不得捕获宽泛异常；确需边界保护时使用 `except Exception as exc`，并记录异常或向调用方返回明确错误。
- 所有异常必须记录日志、重新抛出或返回可诊断的错误信息，禁止静默吞掉异常。
- 禁止使用 `print` 充当日志；项目代码使用 `logging` 或 ROS logger。
- 禁止无意义命名，如 `a`、`b`、`tmp`；数学局部坐标等极短作用域惯例除外，但应优先表达含义。

### P1：强制要求

- 遵循 PEP8：函数和变量使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_CASE`。
- 函数、类和模块名必须表达真实职责。
- 公共逻辑应复用或抽取，避免跨模块复制协议、映射和状态判断。
- 对外接口、ROS/设备控制、数据解析函数必须声明参数和返回值类型；其他函数和方法尽量添加类型注解。
- 使用卫语句减少嵌套；逻辑块之间保留空行。
- 文件、锁和其他资源优先使用上下文管理器。
- 关键注释解释“为什么”和系统约束，不复述代码动作。
- 不通过私有属性或私有函数绕过模块边界。

### P2：建议

- 模块、类和公共函数使用简洁的 Google 风格 docstring。
- 优先使用列表、字典、集合推导式或生成器，但不得牺牲可读性。
- 删除自己改动产生的无用导入、变量和死分支；不要顺手清理与任务无关的旧代码。
- 配置与行为数据优先集中在现有 `config.py` 或 YAML 合同中，不增加平行配置源。

## UI 与资源约束

- 布局、颜色、字号、间距和场景锚点集中在 `config.py`；不要在多个绘制函数中复制魔法数字。
- 逻辑场景坐标与响应式屏幕坐标必须分离，通过现有转换函数映射。
- 控件视觉区域与 `_hit` 命中区域必须保持一致；修改布局时检查折叠、滚动、缩放和最小窗口尺寸。
- 场景顶部控制组与场景标题间距小于 `SPACE_MD` 时使用仅图标紧凑模式，视觉区与命中区保持一致。
- OpenGL 对象只能在图形上下文创建后、主线程中创建或释放。
- 新增资源时更新 `setup.py` 的 `package_data`，并验证源码运行和 ROS 安装后运行都能找到资源。
- 保留底图或纹理加载失败时的程序化回退，不将硬件加速或特定 GPU 驱动视为必然存在。

## 测试与验证

非平凡逻辑变更必须留下最小、可运行的回归测试。优先使用现有 `unittest`，不为单个测试引入新框架。

运行全部测试：

```bash
uv run --no-sync python -m unittest discover -s tests -v
```

运行单个测试文件：

```bash
uv run --no-sync python -m unittest discover -s tests -p "test_feeding_interface.py" -v
```

编译检查：

```bash
uv run --no-sync python -m compileall -q marsdog_sim2d main.py
```

验证要求：

- 解析或协议变更：覆盖正常、缺字段、错误类型和无效 JSON。
- 阈值或状态机变更：覆盖边界值、相邻区间和非法转换。
- 行为/姿态变更：覆盖 behavior、ACT、目标对象、Stage 和最终场景位置。
- 线程共享状态变更：覆盖重复调用、竞态相关顺序和幂等性。
- UI 绘制变更：至少运行编译检查和相关状态测试；可用图形环境中再做窗口尺寸与点击区域人工验证。
- ROS 集成测试需要已 source 的 ROS2 与接口工作区；缺少 `rclpy` 时应明确报告环境限制，不把导入失败误报成业务断言失败。

## 依赖与发布

- Python 直接依赖在 `pyproject.toml`/`setup.py` 中维护；锁定环境同步到 `requirements.txt`。
- ROS 运行依赖在 `package.xml` 中维护。
- 新增依赖前先确认标准库或现有依赖不能完成任务，并说明其必要性。
- 不提交虚拟环境、IDE 私有目录、构建目录、日志或新生成的 `__pycache__`/`.pyc`。
- 修改入口、资源或 ROS 依赖后，同时验证源码启动和 ament 安装路径。

## 完成标准

提交结果前确认：

1. 改动只覆盖用户请求，未覆盖工作区中的既有修改。
2. 架构线程边界、ROS 协议和 UI/行为职责没有被破坏。
3. 相关定向测试通过；条件允许时全量测试和编译检查通过。
4. 新资源、依赖、Topic、Service、环境变量和行为合同已同步文档与打包配置。
5. 未运行的验证及其环境原因已明确说明。
