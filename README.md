# WeLearn-DOM-Helper

<p align="center">
  <b>基于 Selenium + Fluent UI + DOM 原生答案优先解析 + LLM 辅助的外教社 WeLearn 平台自动化工具</b>
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-WeLearn%20(sflep.com)-blue">
  <img alt="Browser" src="https://img.shields.io/badge/Browser-Selenium%20(Edge%2FChrome)-43B02A">
  <img alt="GUI" src="https://img.shields.io/badge/GUI-PyQt%20Fluent%20Widgets-2FA572">
  <img alt="License" src="https://img.shields.io/badge/License-AGPLv3-blue.svg">
  <img alt="Tests" src="https://img.shields.io/badge/Tests-41%20Passed-brightgreen">
</p>

---

## 声明与开源许可证（AGPLv3）

本项目是基于开源项目 [**UnipusAI-Helper**](https://github.com/YSJohnson/UnipusAI-Helper)（原作者：**YSJohnson**，遵循 **GNU Affero General Public License v3.0 (AGPLv3)**）进行二次开发与架构深度适配的衍生项目。

- **衍生协议**：依据 AGPLv3 第 5 条与第 13 条之规定，本项目完全遵循 **GNU AGPLv3** 开源协议发布，完整保留原项目许可证文件 `LICENSE`。
- **版权归属**：基础框架、Fluent UI 交互架构与上下文管理器等核心代码版权归原作者 **YSJohnson** 所有；针对外教社 WeLearn 平台（`welearn.sflep.com`）前端 DOM 特性解析、SCORM 原生提交流程及密钥链安全存储的改造由本项目贡献者完成。
- **免责声明**：本项目仅供软件工程、浏览器 DOM 自动化技术及自动化测试学术研究交流使用，严禁用于任何商业牟利、考试作弊或违反平台用户协议的用途。使用本项目所产生的一切后果由使用者自行承担。

---

## 为什么开发本项目？（开发缘由）

此前社区中已有诸如 [jhl337/Auto_WeLearn](https://github.com/jhl337/Auto_WeLearn) 与 [YZBRH/Welearn_helper](https://github.com/YZBRH/Welearn_helper) 等优秀的开源辅助脚本。然而，这类早期项目普遍采用了**直接抓包、模拟请求或利用后端未授权漏洞**的方式（例如直接向 `/Ajax/SCO.aspx` 发送伪造完成状态包，或向后台发送伪造的学习时长心跳包）。

**现状与痛点：**
1. **协议层漏洞已被平台精准检测封堵**：WeLearn 平台现已上线了严格的服务端请求特征审计、时钟流速校验与动态 Token 对账机制。使用纯发包工具极易触发行为风控，导致学时次日被清零、甚至账号被限制。
2. **纯发包无法应对前端富交互**：新版教材大量引入了动态渲染的富文本填空、选词填空与交互式题型，无界面的 HTTP 脚本已无法稳定解析其真实答案。

**本项目的核心理念：不利用任何后端漏洞，完全基于真实浏览器 DOM 仿真。**
本项目全程通过 Selenium 驱动真实的 Edge/Chrome 浏览器，模拟真人的点击、聚焦、滑动和输入事件，通过读取课件页面前端自带的 DOM 数据节点提取答案，并严格走平台标准的 SCORM 2004 学习周期，彻底规避纯协议脚本的被风控风险。

---

## 已知问题与平台限制说明

由于 WeLearn 平台的架构特性及客观环境限制，请在使用前充分了解以下已知问题与边界：

### 1. 单页面会话互斥限制（放弃并发刷时长，仅支持单网页串联）
- **实际情况**：在开发初期，我们曾尝试编写过多标签页并发刷时长与错峰流水线调度算法，试图通过同时开启多个浏览器 Tab 加速挂满学时。
- **限制原因**：但在实测中发现，WeLearn 平台具有严密的服务端单点会话令牌（`studyTicket`）校验与前端课件外壳 `StudyCourse.aspx` 心跳互踢机制。多开标签页时始终无法绕过“后开的标签页踢掉先开的、或多标签心跳相互覆盖导致时长丢失”的问题。
- **处理方案**：由于开发与期末考核时间紧迫，在无法稳定绕过平台互踢机制的情况下，为了避免引发账号异常风控，**本项目已彻底放弃并发刷时长功能，并强制使用最稳妥的单标签页串联顺序执行**。

### 2. 网页版语音题/录音无法自动录入与上传
- **实际情况**：经测试验证，在 WeLearn 当前的网页端环境下，由于平台音频控件对现代浏览器 Web Audio 录音权限与专有插件的兼容性问题，**即便是人工在网页端进行真实的手动录音作答，也常常无法正常完成录制或提交打分**。
- **处理方案**：考虑到网页端本身的录音交互极其脆弱，且由于开发时间有限，**本项目没有去逆向适配 WeLearn 的录音控件交互与语音评分/提交流程**。程序遇到录音题仅做跳过处理，建议有硬性口语打分要求的课件在手机 App 端手动补做。

### 3. 时间窗口有限（“赶鸭子上架”与测试覆盖率受限）
- **实际情况**：大学各学期各单元的课件开放时间极其短暂且分散，本项目是“赶鸭子上架”抢跑开发出来的。
- **影响**：可用测试账号有限，未能完全覆盖全国不同高校所有系列的外教社教材（如某些小众课本、视听说听力变种排版、主观题互评模块）。若遇到报错或未作答题目，非常欢迎提交 Issue 并附带题目截图与页面 HTML，或直接提交 PR！

### 4. 初次登录与人机验证需人工介入
- 若 WeLearn 平台弹出滑块验证码或短信验证，浏览器自动化程序不会也不应破解验证码，需在弹出的浏览器窗口中**手动滑动通过**。

---

## 详细安装与运行教程（Windows & macOS）

注：由于开发设备限制，本项目未在windows平台测试

本教程专为新手编写，包含每一步应该在什么软件中操作、需要在终端中 `cd` 到什么路径。

### 准备工作（两平台通用）
1. **安装浏览器**：确保电脑中已安装 **Microsoft Edge**（推荐）或 **Google Chrome** 浏览器。
2. **安装 Python**：确保安装了 **Python 3.10、3.11 或 3.12**（建议安装时勾选 `Add Python to PATH`）。

---

### Windows 系统部署教程

#### 第一步：下载并解压项目
1. 在 GitHub 页面点击绿色的 **`Code` $\to$ `Download ZIP`**，将压缩包下载到电脑中。
2. 将其解压到一个**没有中文、没有空格**的路径，例如解压到：
   `D:\Projects\WeLearn-DOM-Helper`

#### 第二步：在项目目录打开 PowerShell
1. 打开解压后的文件夹（例如 `D:\Projects\WeLearn-DOM-Helper`），确认里面能看到 `requirements.txt` 和 `WeLearn_Helper.py`。
2. 在该文件夹的空白处按住键盘 **`Shift` 键并点击鼠标右键**，选择 **【在此处打开 PowerShell 窗口】**（或【在终端中打开】）。
   *(如果是在开始菜单打开的普通终端，请手动输入命令切换目录：)*
   ```powershell
   cd D:\Projects\WeLearn-DOM-Helper
   ```

#### 第三步：创建并激活虚拟环境
在打开的终端窗口中依次输入以下命令：

```powershell
# 1. 确保当前路径处于项目根目录下
# 2. 创建独立虚拟环境 .venv
python -m venv .venv

# 3. 激活虚拟环境
.\.venv\Scripts\Activate.ps1
```
> **若提示脚本执行策略受限 (Restricted)**：在 PowerShell 中执行一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，输入 `Y` 确认后重新执行激活命令。激活成功后，命令行前端会出现 `(.venv)` 标志。

#### 第四步：安装所需依赖
在同一终端窗口中，确保有 `(.venv)` 前缀，运行：

```powershell
pip install -r requirements.txt
```

#### 第五步：运行配置与启动主程序
- **方式 A（双击快捷启动，推荐）**：
  直接在文件夹中**双击 `config.bat`** 即可打开配置器图形界面；配置完成后，**双击 `start.bat`** 即可启动主程序。
- **方式 B（终端命令启动）**：
  在保持激活状态的 PowerShell 中运行：
  ```powershell
  python config_editor.py   # 启动配置界面
  python WeLearn_Helper.py  # 启动自动化主程序
  ```

---

### macOS 系统部署教程

#### 第一步：克隆或下载项目
1. 打开 macOS 的 **【终端】(Terminal)** 应用。
2. 切换到你想存放项目的目录（例如个人工作目录）：
   ```bash
   cd ~/Documents
   ```
3. 克隆或解压项目到本地，并 `cd` 进入项目根目录：
   ```bash
   git clone https://github.com/YourUsername/WeLearn-DOM-Helper.git
   cd WeLearn-DOM-Helper
   ```
   *(请务必确保终端前缀已进入 `WeLearn-DOM-Helper` 目录)*

#### 第二步：创建并激活虚拟环境
在项目根目录下执行：

```bash
# 1. 创建虚拟环境
python3 -m venv .venv

# 2. 激活虚拟环境
source .venv/bin/activate
```
*(激活成功后，终端前缀会显示 `(.venv)`)*

#### 第三步：安装依赖库
在已激活的环境下执行：

```bash
pip install -r requirements.txt
```

#### 第四步：运行与配置
- **方式 A（Finder 双击启动，推荐）**：
  在 macOS 访达 (Finder) 中打开项目文件夹：
  1. 双击 **`config.command`** 打开配置编辑器。（*若系统提示安全拦截，请在文件上右键 $\to$ 选择【打开】即可*）
  2. 双击 **`start.command`** 启动主程序。
- **方式 B（终端命令启动）**：
  在项目根目录下直接运行：
  ```bash
  python3 config_editor.py   # 打开配置编辑器
  python3 WeLearn_Helper.py  # 启动主程序
  ```

---

## 快速使用操作指南

1. **配置参数**：
   - 首次使用建议通过图形界面设置；如果不使用大模型，保持默认的“零 Token 模板模式”即可。
   - 可设置**单节保底停留时间**（如 60~90 秒）或**目标总时长**（如 3600 秒），系统将自动平摊。
2. **启动主程序**：
   - 启动后系统会自动唤起浏览器打开 WeLearn 官网；
   - 若未在配置中保存密码，请直接在弹出的浏览器中**手动输入密码登录，并滑动完成人机验证**；
3. **加载课程任务**：
   - 登录成功并进入课程主页后，回到 Helper 软件界面，点击 **【扫描任务列表】**；
   - 软件将自动读取所有单元与小节，并在多层任务树中以清晰的状态标记（已完成 / 未完成）；
4. **一键串联运行**：
   - 勾选你需要做的小节（支持单元全选或一键勾选所有未完成项）；
   - 点击 **【处理选中任务】**，程序将单标签页逐节进入、提取 DOM 原生正解填入、按预算停留、并自动提交；
   - 过程中可随时点击 **【停止】**，已做完的小节数据均已即时保存上报。

---

## 核心设计与作答策略

### 1. 优先读取 DOM 原生答案（零 Token 消耗）
通过对 WeLearn 课件层前端 DOM 的逆向解析，绝大部分客观题均已在前端节点内直接注入了标准答案数据：
- **选择题 (`div[data-controltype="choice"]`)**：正确选项 `<li>` 节点直接携带 `data-solution` 属性，程序自动定位该节点并通过 `WebDriverHelper.safe_click` 进行真实模拟点击，完全零 Token 消耗。
- **选词填空题 (`div[data-controltype="choosebox"]`)**：深度解析 WeLearn 复杂的选词填空组件，自动关联待选词库与空白插槽，自动同步底部 `AnswerSheet` 状态，原生匹配正解。
- **客观短填空 (`div[data-controltype="filling"]`)**：输入框自动读取同级 `data-solution` 或 `div[data-itemtype="result"]`，支持以 `/` 分隔的多解自动拆分与选取，支持快速 DOM 绑定与真实按键模拟两种模式。

### 2. LLM 智能兜底主观题（可选）
- **开放简答与长填空 (`div[data-controltype="fillinglong"]`)**：针对无原生标准答案的主观写作与开放思考题，自动向上回溯提取所在题目说明 `.direction` 及课文背景材料，调用 OpenAI 兼容接口（如 `gpt-4o-mini` / `deepseek-chat` / `qwen` 等）生成高质量规范英语回答。
- **零 Token 免费模式**：默认自带优选学术范句模板，不配置 API Key 亦可顺畅运行。

### 3. 严格单标签页串联拟真 + 智能学时分摊（防封策略）
- **杜绝并发多开风险**：强制采用单标签页串联顺序处理（单节作答 $\to$ 拟真停留 $\to$ SCORM 原生提交），彻底解决多标签页互踢与学时覆盖问题。
- **目标总时长智能分摊 (`DurationPlanner`)**：支持设定课程/选中范围的「目标总时长 (`target_total_seconds`)」，系统自动读取并扣除各小节已有学时，将净差额以非均匀随机权重（$\pm 35\%$ 抖动）合理分摊至各选中小节；同时支持配置「单小节保底停留秒数 (`min_dwell_seconds`)」。
- **SCORM 2004 原生提交流程**：小节完成时主动触发 `KeepLearnTimeAndCheckToken()` 与 `EndSCO(false)` 进行服务端会话同步，确保学时即时到账。

### 4. 操作系统原生密钥链安全存储（Keyring）
- 拒绝在明文配置文件 `config.json` 中保存密码与 API Key！
- 平台账号密码与大模型 API 凭据自动托管至系统的加密密钥链（macOS Keychain / Windows 凭据管理器 / Linux SecretService），杜绝个人隐私在 Git 提交中意外泄露。

---

## 架构概览

```
WeLearn-DOM-Helper/
├── WeLearn_Helper.py       # 主程序入口：日志、生命周期与自动化调度
├── config_editor.py        # 基于 Fluent UI 的现代化配置编辑器图形界面
├── fluent_ui.py            # 主工作台界面：单元/小节多层折叠任务树、实时日志终端
├── ui_common.py            # macOS 原生红绿灯标题栏与统一 Fluent 暗色视觉主题
├── secret_store.py         # 操作系统密钥链（Keyring）安全存储适配器
├── version.py              # 项目版本号与元数据
├── welearn_bot.py          # 自动化机器人：浏览器驱动调度、登录检测、串联任务控制
├── question_solver.py      # 核心解题策略：选择/填空/ChooseBox DOM 抽取与 LLM 兜底
├── welearn_player.py       # 学习外壳页与 contentFrame 跨层上下文管理器
├── welearn_api.py          # WeLearn 课程、单元与小节目录解析
├── webdriver_helper.py     # 模拟击键 (simulate_typing)、安全点击与防检测
├── ai_client.py            # OpenAI 兼容接口客户端与 Prompt 构造器
├── tts_engine.py           # 语音合成引擎（支持 edge-tts / macOS say / Windows SAPI）
├── AudioRecognizer.py      # 本地 Whisper 音频转录（按需延迟加载）
├── welearn_config.py       # 配置数据模型与校验
├── config.example.json     # 配置文件范式
├── requirements.txt        # 依赖清单
├── LICENSE                 # GNU AGPLv3 许可证全文
├── config.sh / config.command / config.bat # 独立配置编辑器启动脚本 (Linux/macOS/Windows)
├── start.sh / start.command / start.bat    # 主程序启动脚本 (Linux/macOS/Windows)
└── tests/                  # 单元与集成测试套件（已包含 41 个用例）
```

---

## 自动化测试验证

本项目拥有完善的单元与自动化测试，包含 DOM 解析、学时分配计算、配置编辑器与现代 UI 状态机验证：

```bash
# 激活环境后在项目根目录下运行
pytest -v
```

---

## 致谢

- [UnipusAI-Helper](https://github.com/YSJohnson/UnipusAI-Helper) by YSJohnson（优秀的架构启发与开源先驱）
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) by zhiyiYo（优雅精致的 Fluent UI 库）
- [Selenium](https://www.selenium.dev/)
