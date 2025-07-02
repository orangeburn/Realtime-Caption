# 🗣️ Realtime Caption

> 🎙️ 一款基于 [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) 的本地实时字幕系统，支持系统音频捕获、语音识别、实时翻译与字幕浮窗显示，适用于会议记录、实时翻译、直播字幕等场景。

---

## 🆕 更新内容

- 支持接入 nllb200 多语言模型，实现字幕实时翻译。
- 优化依赖管理，项目已排除 venv、node_modules 等依赖目录和大文件，远程仓库仅包含源码和配置。
- 增加大文件本地恢复说明，便于用户快速部署模型。

---

## 🔧 项目简介

**Realtime Caption** 是一个运行于 Windows 平台的本地实时字幕工具，支持从系统音频中实时提取语音内容，通过大模型进行自动语音识别（ASR），并将字幕以悬浮窗形式实时呈现。适用于想要本地部署、安全私有化使用实时语音识别的用户。

本项目基于开源语音模型 **SenseVoice**，结合 Python 后端和 Electron 前端构建完整工作流，无需依赖云服务。现已支持 nllb200 多语言模型，可实现实时字幕翻译。

---

## ✨ 功能亮点

* ✅ **系统音频捕获**：基于 WASAPI Loopback 捕捉系统播放的声音，无需麦克风输入。
* 🧠 **语音识别模型**：集成 SenseVoice 本地大模型，无需联网即可识别普通话。
* 🌐 **WebSocket 通讯**：后端采用 WebSocket 协议实现实时音频传输与识别结果回传。
* 🌍 **实时翻译**：支持 nllb200 多语言模型，自动将识别到的字幕实时翻译为目标语言，适用于多语种会议、跨国交流等场景。
* 🪟 **字幕悬浮窗**：Electron 实现简洁字幕窗口，适配不同桌面场景。
* 🔒 **本地运行**：全流程本地执行，无需上传任何音频，保障数据隐私。

---

## 📁 项目结构

```
Realtime-Caption/
├── a4s/                # 后端主服务（推荐使用此目录下的 server_wss_split.py）
├── backend/            # 其它后端实现（如有）
├── python/             # 系统音频捕获模块（WASAPI + Sounddevice）
├── electron/           # Electron前端（字幕显示界面）
├── nllb200_ct2/        # nllb200翻译模型文件（需另行下载）
├── requirements.txt    # Python依赖（如有）
└── README.md
```

> 说明：`api4sensevoice/`、`SenseVoice/` 目录已弃用，推荐仅使用 `a4s/` 及相关目录。

---

## 🚀 快速开始

1. 克隆项目：

```bash
git clone https://github.com/orangeburn/Realtime-Caption.git
cd Realtime-Caption
```

2. 安装 Python 依赖（推荐 conda 环境）：

```bash
conda create -n api4sensevoice python=3.10
conda activate api4sensevoice
conda install -c conda-forge ffmpeg
pip install -r requirements.txt
```

3. 安装 Node.js 依赖（用于 Electron GUI）：

```bash
cd electron
npm install
```

4. 启动后端 WebSocket 服务（推荐）：

```bash
python a4s/server_wss_split.py
```

5. 启动音频捕获模块：

```bash
python python/audio_capture_websocket.py
```

6. 启动前端字幕窗口：

```bash
cd electron
npm start
```

---

## 📦 大文件管理与模型恢复

本项目未在仓库中直接存储大模型文件（如 nllb200_ct2 下的 model.bin 等），请按如下方式获取和恢复：

1. 访问 [JustFrederik/nllb-200-distilled-600M-ct2-int8](https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8) 下载所需模型文件。
2. 将下载的模型文件（如 model.bin、sentencepiece.bpe.model、tokenizer.json）放入 `nllb200_ct2/` 目录下。
3.  **注意：** 模型大文件已被 `.gitignore` 排除，需单独下载到本地。
4. **nllb200_ct2 依赖 [CTranslate2](https://github.com/OpenNMT/CTranslate2) 推理引擎，已在 requirements.txt 中声明。请确保已正确安装。**

---

## 🧩 依赖管理说明

- **Python 依赖**：请使用根目录下的 `requirements.txt` 安装，虚拟环境（如 venv、torch-env）不会纳入版本控制。
- **CTranslate2 依赖**：nllb200_ct2 翻译模型依赖 [CTranslate2](https://github.com/OpenNMT/CTranslate2) 推理引擎，已在 requirements.txt 中声明。若遇到安装问题，可手动执行：

  ```bash
  pip install ctranslate2
  ```
  
  CTranslate2 用于高效加载和推理 nllb200_ct2 目录下的多语种翻译模型。
- **Node.js 依赖**：请在 `electron/` 目录下运行 `npm install`，`node_modules` 目录不会纳入版本控制。
- **模型文件**：需手动下载或本地恢复，避免仓库存储大文件。

---

## 🙏 鸣谢

* [SenseVoice (by 阿里达摩院)](https://github.com/FunAudioLLM/SenseVoice) — 自动语音识别核心模型
* [api4sensevoice](https://github.com/0x5446/api4sensevoice) — 基于 SenseVoice 的轻量化服务实现

---

## 📜 许可证

本项目采用 [MIT License](./LICENSE) 开源。

---

# Realtime-Caption: Real-time Streaming Speech Recognition with Speaker Verification

本项目后端基于 [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) 及多模型融合，支持：
- **VAD 检测**
- **实时流式识别**
- **说话人验证**
- 多语种字幕、WebSocket/HTTP API、设备/语言动态切换等

---

## 更新日志

#### 2024-09-30
1. 优化说话人验证，累积音频提升识别准确率。
2. 识别结果增加 `logprob` 字段，便于上层应用判断置信度。

---

## 安装与依赖

### 克隆仓库

```bash
git clone https://github.com/orangeburn/Realtime-Caption.git
cd Realtime-Caption
```

### Python 环境与依赖

```bash
conda create -n api4sensevoice python=3.10
conda activate api4sensevoice
conda install -c conda-forge ffmpeg
pip install -r a4s/requirements.txt
```

### 依赖的外部模型/项目
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)
- [ModelScope: speech_campplus_sv_zh_en_16k-common_advanced](https://modelscope.cn/models/iic/speech_campplus_sv_zh_en_16k-common_advanced)
- [ModelScope: speech_fsmn_vad_zh-cn-16k-common-pytorch](https://modelscope.cn/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch)

---

## 后端运行方式

### 单句识别 API 服务

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI app with a specified port.")
    parser.add_argument('--port', type=int, default=7000, help='Port number to run the FastAPI app on.')
    parser.add_argument('--certfile', type=str, default='path_to_your_certfile', help='SSL certificate file')
    parser.add_argument('--keyfile', type=str, default='path_to_your_keyfile', help='SSL key file')
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, ssl_certfile=args.certfile, ssl_keyfile=args.keyfile)
```

可通过命令行参数指定端口、证书等，直接运行：

```bash
python a4s/server.py --port 8888 --certfile path_to_your_certfile --keyfile path_to_your_key
```

#### API 说明
- 路径：`/transcribe`  
- 方法：`POST`  
- 请求体：`multipart/form-data`，参数 `file`（音频文件）
- 响应：`application/json`，字段：`code`、`info`、`data`

请求示例：
```bash
curl -X 'POST'  'http://yourapiaddress/transcribe'  -H 'accept: application/json'  -H 'Content-Type: multipart/form-data'  -F 'file=@path_to_your_audio_file'
```

响应示例：
```json
{
  "code": 0,
  "msg": "Success",
  "data": {
    // 识别结果
  }
}
```

---

### 流式实时识别 WebSocket 服务

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the FastAPI app with a specified port.")
    parser.add_argument('--port', type=int, default=27000, help='Port number to run the FastAPI app on.')
    parser.add_argument('--certfile', type=str, default='path_to_your_certfile', help='SSL certificate file')
    parser.add_argument('--keyfile', type=str, default='path_to_your_keyfile', help='SSL key file')
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port, ssl_certfile=args.certfile, ssl_keyfile=args.keyfile)
```

可通过命令行参数指定端口、证书等，直接运行：

```bash
python a4s/server_wss_split.py --port 8888 --certfile path_to_your_certfile --keyfile path_to_your_key
```

#### 说话人验证配置
1. 准备待验证说话人的音频（16000采样率、单通道、16bit、WAV），放入 `a4s/speaker/` 目录。
2. 修改 `server_wss_split.py` 中 `reg_spks_files` 列表为你的音频路径。

```python
reg_spks_files = [
    "speaker/speaker1_a_cn_16k.wav"
]
```

#### WebSocket 参数
- 端点：`/ws/subscribe`（字幕订阅） `/ws/upload`（音频上传）
- 查询参数：`sv`（是否启用说话人验证，默认0）
- 上行数据：PCM 二进制（单通道、16k采样、16bit）
- 下行数据：JSON 字符串，字段：`code`、`info`、`data`

#### 客户端测试页面
- `a4s/client_wss.html`，修改 `wsUrl` 为你的 WebSocket 地址

```javascript
ws = new WebSocket(`wss://your_wss_server_address/ws/subscribe`);
```

---

## Roadmap
- [x] 音频采集python
- [x] 实时翻译模型nllb200-ct2接入
- [x] 搭建前端
- [x] 采集模块、前端与后端断线重连
- [x] 翻译字幕目标语言切换
- [x] 立体声音频采集/麦克风采集 切换
- [ ] 离线运行时报错
- [ ] 前端交互优化

## Contribution
欢迎任何形式的贡献，包括但不限于：
- Bug 反馈
- 功能建议
- 代码提交
- 文档完善

## License
MIT License，详见 LICENSE 文件。
