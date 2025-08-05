# 🗣️ Realtime Caption v2.0

> 当前版本：v2.0

> 🎙️ 一款基于 [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) 的本地实时字幕系统，支持高质量双流音频架构、语音识别、实时翻译与字幕浮窗显示，适用于会议记录、实时翻译、直播字幕等场景。

---

## 🆕 v2.0 更新内容

### 🎵 双流音频架构
- **🔥 全新双流架构**：ASR流(16kHz) + 录音流(48kHz)，解决音质问题
- **📡 智能流分离**：实时字幕使用16kHz，录音保存使用原始高采样率
- **🎧 消除降采样噪音**：系统音频不再强制降到16kHz，避免电流声
- **🔄 完全兼容**：保持原有单流架构，用户可自由选择

### � 记录功能
- **💾 导出完整录音**：支持WAV格式音频导出，保留原始音质
- **📝 字幕导出**：支持带时间戳的TXT格式字幕文件
- **🎞️ 记录管理**：统一的字幕和音频文件管理界面
- **📂 智能归档**：录音与字幕文件自动匹配与归档

### �🛠️ 交互优化
- **⚡ 立即响应**：录音结束立即显示导出对话框
- **📁 智能按钮**：双流架构显示"打开文件夹"，单流显示"导出音频"
- **✅ 准确提示**：修复误报"没有收到音频数据"的问题
- **🎯 正确路径**：打开录音文件夹功能指向正确的`python/recordings`目录

### 🧹 项目清理
- **📂 结构简化**：清理开发过程文件，保留核心功能
- **🔧 模块精简**：仅保留原始单流和增强双流两个架构
- **📖 启动器**：统一的服务选择和启动界面

---

## 🔧 项目简介

**Realtime Caption** 是一个运行于 Windows 平台的本地实时字幕工具，支持从系统音频中实时提取语音内容，通过大模型进行自动语音识别（ASR），并将字幕以悬浮窗形式实时呈现。

### 🏗️ 双流架构优势
- **ASR流**：16kHz单声道，专门优化实时字幕识别性能
- **录音流**：48kHz立体声，保持原始音质，支持24-bit高保真
- **智能重采样**：支持scipy、librosa、numpy多种算法
- **零延迟**：双流并行处理，不影响实时字幕响应速度

---

## ✨ 功能亮点

* ✅ **双流音频架构**：ASR和录音分离处理，兼顾实时性和音质
* 🎤 **系统音频捕获**：基于 WASAPI Loopback 捕捉系统播放的声音
* 🧠 **语音识别模型**：集成 SenseVoice 本地大模型，支持普通话识别
* 🌐 **WebSocket 通讯**：实时音频传输与识别结果回传
* 🌍 **实时翻译**：支持 nllb200 多语言模型，实时字幕翻译
* 🪟 **字幕悬浮窗**：Electron 实现简洁字幕窗口
* 📁 **录音管理**：支持高质量录音导出和文件夹管理
* 🔒 **本地运行**：全流程本地执行，保障数据隐私

---

## 📁 项目结构

```
realtime-caption-mvp/
├── python/                    # 音频服务核心模块
│   ├── audio_capture_websocket.py      # 原始单流架构（稳定版）
│   ├── enhanced_dual_audio_service.py  # 增强双流架构（推荐版）
│   ├── audio_service_launcher.py       # 服务启动器
│   ├── asr_server.py                   # ASR识别服务
│   ├── websocket_server.py             # WebSocket通信服务
│   ├── backend_launcher.py             # 后端服务启动器
│   └── recordings/                     # 录音文件输出目录
├── a4s/                       # AI模型服务
│   ├── server_wss_split.py    # WebSocket服务器
│   ├── model.py              # 模型管理
│   └── config.py             # 配置管理
├── electron/                  # 前端界面
│   ├── main.js               # 主进程
│   ├── renderer.js           # 渲染进程
│   ├── index.html            # 界面文件
│   └── preload.js            # 预加载脚本
├── requirements.txt           # Python依赖
└── README.md
```

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/orangeburn/Realtime-Caption.git
cd realtime-caption-mvp

# 创建Python环境
conda create -n realtime-caption python=3.10
conda activate realtime-caption
conda install -c conda-forge ffmpeg

# 安装Python依赖
pip install -r requirements.txt

# 安装Node.js依赖
cd electron
npm install
cd ..
```

### 2. 启动方式

#### 🎯 推荐方式（双流架构）

```bash
# 1. 启动后端服务
python python/backend_launcher.py

# 2. 启动音频服务（推荐双流架构）
python python/audio_service_launcher.py

# 3. 启动前端界面
cd electron && npm start
```

#### 🔄 传统方式（单流架构）

```bash
# 1. 启动后端
python a4s/server_wss_split.py

# 2. 启动音频采集
python python/audio_capture_websocket.py

# 3. 启动前端
cd electron && npm start
```

### 3. 使用音频服务启动器

```bash
# 交互式选择
python python/audio_service_launcher.py

# 直接启动双流架构
python python/audio_service_launcher.py --enhanced

# 直接启动单流架构
python python/audio_service_launcher.py --legacy
```

---

## 🎵 音频架构选择

### 🆕 增强双流架构（推荐）
- **适用场景**：需要高质量录音、消除系统音频噪音
- **优势**：
  - 48kHz立体声高质量录音
  - 消除16kHz降采样电流噪声
  - 双流并行，不影响实时字幕性能
- **文件输出**：同时生成标准质量和高质量两个录音文件

### 🔄 原始单流架构（稳定）
- **适用场景**：生产环境、对录音质量要求不高
- **优势**：
  - 经过充分测试，稳定可靠
  - 资源占用小，延迟低
  - 兼容性好

### 📊 架构对比

| 特性 | 单流架构 | 双流架构 |
|------|---------|---------|
| 实时性能 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 录音质量 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 系统音频噪音 | 有电流声 | 无噪音 |
| 资源占用 | 低 | 中等 |
| 稳定性 | 很高 | 高 |
| 生产就绪 | ✅ | ✅ |

---

## 🎛️ 功能说明

### 录音模式
1. **开始录音**：点击录音按钮开始录制
2. **实时字幕**：录音过程中显示实时识别的字幕
3. **结束录音**：停止后立即显示导出选项
4. **文件管理**：
   - **单流架构**：生成16kHz WAV文件
   - **双流架构**：生成标准(16kHz)和高质量(48kHz)两个文件

### 导出功能
- **📝 导出字幕**：导出带时间戳的TXT格式字幕文件
- **🎵 导出音频**：
  - 单流：下载音频文件到本地
  - 双流：打开录音文件夹查看所有文件
- **📁 打开文件夹**：直接访问录音文件保存目录

### 设备管理
- **🔍 自动检测**：智能识别可用音频设备
- **🎯 优先选择**：优先使用系统音频设备（立体声混音）
- **🔄 动态切换**：运行时可切换不同音频输入设备
- **🎤 设备类型**：支持麦克风、系统输出等多种设备

---

## 📦 模型自动管理

**模型文件统一自动管理，无需手动下载！**

- ✅ **ASR模型**：SenseVoice语音识别模型自动下载
- ✅ **翻译模型**：nllb200翻译模型自动下载  
- ✅ **模型热更新**：支持运行时动态更新
- 🔧 **推理优化**：使用CTranslate2高性能推理引擎

---

## 🛠️ 开发说明

### 核心文件说明

#### Python服务
- `audio_capture_websocket.py`: 单流音频采集，16kHz统一处理
- `enhanced_dual_audio_service.py`: 双流音频采集，ASR+录音分离
- `audio_service_launcher.py`: 服务选择和启动管理
- `asr_server.py`: SenseVoice ASR识别服务
- `websocket_server.py`: 前后端WebSocket通信

#### 前端界面
- `main.js`: Electron主进程，窗口管理
- `renderer.js`: 渲染进程，界面逻辑和WebSocket通信
- `index.html`: 字幕显示界面

### 音频处理流程

#### 单流架构
```
音频输入 → 16kHz重采样 → ASR识别 + 录音保存
```

#### 双流架构  
```
音频输入 ┬→ 16kHz单声道 → ASR识别 → 实时字幕
         └→ 48kHz立体声 → 高质量录音 → 本地保存
```

---

## 🧩 依赖管理

### Python依赖
```bash
# 核心依赖
sounddevice>=0.4.6    # 音频采集
websockets>=11.0      # WebSocket通信
numpy>=1.24.0         # 数值计算
scipy>=1.11.0         # 信号处理（重采样）
librosa>=0.10.0       # 音频处理（可选）

# AI模型依赖
transformers>=4.30.0  # SenseVoice模型
ctranslate2>=3.0.0    # 翻译推理引擎
```

### Node.js依赖
```bash
cd electron
npm install  # 安装Electron和相关依赖
```

### 系统要求
- **操作系统**：Windows 10/11
- **Python**：3.8-3.11
- **Node.js**：16.0+
- **内存**：建议8GB+
- **存储**：模型文件约2GB

---

## 📝 使用技巧

### 音频设备选择
1. **系统音频录制**：选择"立体声混音"或"您听到的声音"
2. **麦克风录制**：选择具体的麦克风设备
3. **设备故障排除**：使用启动器的"查看音频设备列表"功能

### 录音质量优化
- **双流架构**：自动使用设备最佳采样率
- **重采样算法**：优先使用scipy > librosa > numpy
- **立体声录音**：保持系统音频的原始声道信息

### 实时性能调整
- **块大小**：默认0.5秒音频块，平衡实时性和准确性
- **采样率匹配**：ASR固定16kHz，录音保持原始采样率
- **设备兼容性**：自动检测和适配不同音频设备

---

## 🙏 鸣谢

* [SenseVoice (by 阿里达摩院)](https://github.com/FunAudioLLM/SenseVoice) — 自动语音识别核心模型
* [api4sensevoice](https://github.com/0x5446/api4sensevoice) — 基于 SenseVoice 的轻量化服务实现
* [CTranslate2](https://github.com/OpenNMT/CTranslate2) — 高性能推理引擎
* [nllb-200](https://github.com/facebookresearch/fairseq/tree/nllb) — 多语言翻译模型

---

## 📜 许可证

本项目采用 [MIT License](./LICENSE) 开源。

---

## 🚦 更新日志

### v2.0.0 (2025-01-05)
- ✨ 全新双流音频架构，解决系统音频降采样噪音问题
- 🎯 优化录音完成交互，立即显示导出选项
- 📁 修复录音文件夹路径，正确指向python/recordings
- 🧹 项目结构清理，移除冗余文件和模块
- 🔧 统一服务启动器，支持架构选择
- 💡 智能按钮显示，根据架构类型调整界面

### v1.5.0 (2024-12-20)
- 🔄 前端交互优化
- 🤖 ASR模型与翻译模型纳入统一管理
- 🔥 支持模型热更新
- 🎛️ 优化音频采集设备过滤逻辑

---

## 🗺️ Roadmap

### ✅ 已完成功能
- [x] 音频采集python模块
- [x] 实时翻译模型nllb200-ct2接入
- [x] 搭建前端界面
- [x] 采集模块、前端与后端断线重连
- [x] 翻译字幕目标语言切换
- [x] 立体声音频采集/麦克风采集切换
- [x] 离线运行错误修复
- [x] 前端交互优化
- [x] ASR模型与翻译模型纳入统一管理，首次运行后端时自动下载模型文件
- [x] 支持模型热更新
- [x] 优化音频采集设备过滤逻辑
- [x] **双流音频架构** - ASR流和录音流分离处理
- [x] **高质量录音** - 48kHz立体声录音，消除降采样噪音
- [x] **录音文件导出** - 支持本地文件保存和文件夹管理
- [x] **字幕导出** - TXT格式带时间戳字幕文件
- [x] **交互优化** - 录音完成立即显示导出选项
- [x] **项目结构清理** - 移除冗余文件，保留核心功能

### 💡 待研究功能
- [ ] 实时语音情感分析
- [ ] 多语言混合识别
- [ ] 会议纪要自动生成
- [ ] 实时语音翻译（语音输出）

---

## 🤝 贡献指南

欢迎任何形式的贡献：

1. **Bug反馈**：提交Issue描述问题
2. **功能建议**：讨论新功能需求
3. **代码贡献**：Fork项目，提交Pull Request
4. **文档完善**：改进文档和使用说明
5. **测试支持**：在不同环境下测试功能

### 开发环境设置
```bash
# 开发模式启动
npm run dev      # 前端开发模式
python -m pytest # 运行测试（如果有）
```

---

**🎉 享受高质量的本地实时字幕体验！**