# WeLearn-DOM-Helper

<p align="center">
  <b>基于 Selenium + Fluent UI + DOM 原生答案优先解析 + LLM 辅助的外教社 WeLearn 平台自动化工具</b>
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-WeLearn%20(sflep.com)-blue">
  <img alt="Browser" src="https://img.shields.io/badge/Browser-Selenium%20(Edge%2FChrome)-43B02A">
  <img alt="GUI" src="https://img.shields.io/badge/GUI-PyQt%20Fluent%20Widgets-2FA572">
  <img alt="License" src="https://img.shields.io/badge/License-AGPLv3-blue.svg">
</p>

---

## 声明与开源许可证（AGPLv3）

本项目是基于开源项目 [**UnipusAI-Helper**](https://github.com/YSJohnson/UnipusAI-Helper)（原作者：**YSJohnson**，遵循 **GNU Affero General Public License v3.0 (AGPLv3)**）进行二次开发与架构适配的衍生项目。

- **衍生协议**：依据 AGPLv3 第 5 条与第 13 条之规定，本项目完全遵循 **GNU AGPLv3** 开源协议发布，完整保留原项目许可证文件 `LICENSE`。
- **版权归属**：基础框架、Fluent UI 交互架构与上下文管理器等核心代码版权归原作者 **YSJohnson** 所有；针对外教社 WeLearn 平台（`welearn.sflep.com`）协议、前端 DOM 特性解析与 SCORM 原生提交链条的改造由本项目贡献者完成。
- **免责声明**：本项目仅供软件工程、浏览器 DOM 自动化技术及自动化测试学术研究交流使用，严禁用于任何非法或违规用途。

---

## 核心设计与作答策略

### 1. 优先读取 DOM 原生答案（零 Token 消耗）
通过对 WeLearn 课件层前端 DOM 的逆向与调研，绝大部分客观题均在前端节点内直接注入了标准答案数据：
- **选择题 (`div[data-controltype="choice"]`)**：正确选项 `<li>` 节点直接携带 `data-solution` 属性，程序直接定位该节点并通过 `WebDriverHelper.safe_click` 进行真实点击，零 Token 消耗。
- **客观短填空 (`div[data-controltype="filling"]`)**：输入框 `input[data-itemtype="input"]` 自带 `data-solution="标准答案"` 属性（或通过同级 `div[data-itemtype="result"]` 呈现），支持以 `/` 分隔的多解自动拆分与选取，使用 `WebDriverHelper.simulate_typing` 模拟击键输入。

### 2. LLM 智能兜底主观题
- **开放简答与长填空 (`div[data-controltype="fillinglong"]`)**：针对无原生标准答案的主观写作与思考题，自动向上回溯提取所在 `.white_frame`、题目说明 `.direction` 及课文背景材料，调用 OpenAI 兼容接口（如 `gpt-4o-mini` / `deepseek-chat` / `kimi-k2-turbo-preview`）生成规范英语回答并填入。

### 3. SCORM 2004 原生提交流程与防风控并发架构
- **杜绝纯 HTTP 伪造包**：旧版脚本直接向 `/Ajax/SCO.aspx` 发送全量无上限协程并发或 `session_time: 0` 的静态数据包，极易触发平台时间流速审计与次日对账清零。
- **目标总时长智能分摊 (`DurationPlanner`)**：支持设定课程/选中范围的「目标总时长 (`target_total_seconds`)」，自动读取并扣除各小节已有 `learntime`，将净差额时长以非均匀随机权重（$\pm 35\%$ 抖动）分配至各个选中任务，既避免单单元时长畸高，又保证累计总时长精准达标。
- **三种可选执行与防封控并发模式 (`concurrency_mode`)**：
  1. **`serial`（串联顺序模式）**：单标签页按目录顺序逐个完成作答、停留与原生提交（基线模式）。
  2. **`decoupled`（答题/挂机解耦并发模式）**：阶段 1 在主标签页单线程按顺序快速完成题目作答与提交（确保服务端 `submit_time` 时间轴 100% 串行无重叠）；阶段 2 开启多标签页池并发打开小节纯挂原生心跳补齐时长，不重复点击提交按钮。
  3. **`pipeline`（错峰流水线并发模式）**：开启 $2 \sim 4$ 个真实浏览器标签页并行加载小节、DOM 作答并同时挂时长，配合 **「错峰发车 + 保序提交互斥锁（Submission Gate）」** 强制按目录顺序单调递增提交并保持安全间隔。

---

## 架构概览

```
WeLearn-DOM-Helper/
├── WeLearn_Helper.py       # 主程序入口：日志、生命周期与自动化调度
├── config_editor.py        # 基于 Fluent UI 的配置编辑器图形界面
├── fluent_ui.py            # 主工作台界面：单元/小节多层折叠任务树、实时日志终端
├── welearn_bot.py          # 自动化机器人：浏览器驱动调度、登录检测、批量任务控制
├── question_solver.py      # 核心解题策略：选择题/填空题 DOM 原生抽取、LLM 兜底、停留与提交
├── welearn_player.py       # 学习外壳页与 contentFrame 跨层上下文管理器
├── welearn_api.py          # WeLearn 课程、单元与小节目录解析
├── webdriver_helper.py     # 模拟击键 (simulate_typing)、安全点击与防检测
├── ai_client.py            # OpenAI 兼容接口客户端与英语题型 Prompt 生成器
├── tts_engine.py           # 语音合成引擎（支持 edge-tts / macOS say / Windows SAPI）
├── AudioRecognizer.py      # 本地 Whisper 音频转录（按需延迟加载）
├── welearn_config.py       # 配置数据模型与校验
├── config.example.json     # 配置文件范式
├── requirements.txt        # 依赖清单
├── LICENSE                 # GNU AGPLv3 许可证全文
├── config.sh / config.command / config.bat # 独立配置编辑器启动脚本 (Linux/macOS/Windows)
├── start.sh / start.command / start.bat    # 主程序启动脚本 (Linux/macOS/Windows)
└── tests/                  # 单元与集成测试套件
```

---

## 安装与快速上手

### 1. 准备环境

推荐使用 Python 3.10 ~ 3.12：

```bash
# 克隆仓库
git clone https://github.com/YourUsername/WeLearn-DOM-Helper.git
cd WeLearn-DOM-Helper

# 创建虚拟环境（推荐使用 uv 或 python venv）
uv venv --python 3.12 .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
uv pip install -r requirements.txt  # 或 pip install -r requirements.txt
```

### 2. 配置参数

可以运行配置编辑器图形界面，或从范式复制配置文件：

```bash
# 启动独立配置编辑器 GUI
./config.sh         # Linux / macOS 终端
# 或在 macOS Finder 中直接双击运行 config.command
# 或在 Windows 文件资源管理器中直接双击运行 config.bat
python config_editor.py
```

或手动编辑 `config.json`：

```json
{
  "username": "",
  "password": "",
  "url": "https://welearn.sflep.com/2019/student/index.aspx",
  "api_key": "sk-your-openai-key",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "temperature": 0.3,
  "max_tokens": 4096,
  "min_dwell_seconds": 5,
  "browser": "edge",
  "headless": false,
  "debug_mode": false,
  "tts_engine": "auto"
}
```

> **注意**：`.gitignore` 已默认忽略 `config.json`，切勿将包含账号密码或 API Key 的文件推送到代码仓库。

### 3. 运行程序

```bash
./start.sh  # macOS / Linux
# 或双击 start.command / start.bat
# 或执行:
python WeLearn_Helper.py
```

1. 程序启动后会自动打开浏览器并导航至 WeLearn 登录页；
2. 如果未在配置中指定账号密码，请在浏览器中手动完成登录与人机验证；
3. 登录完成后，点击主界面的 **【扫描任务列表】**，系统将自动读取已加入的课程、单元与小节目录；
4. 勾选需要完成的小节，点击 **【处理选中任务】** 即可开始全自动运行；
5. 支持随时点击 **【停止】**，已完成的任务会自动取消勾选并记录状态。

---

## 测试

本项目配备了完整的自动化测试套件：

```bash
pytest -v
```

---

##  致谢

- [UnipusAI-Helper](https://github.com/YSJohnson/UnipusAI-Helper) by YSJohnson
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) by zhiyiYo
- [Selenium](https://www.selenium.dev/)
