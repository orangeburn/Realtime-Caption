# 🗣️ Realtime Caption v2.0

*English | [中文](./README.md)*

> Current Version: v2.0

> 🎙️ A local real-time subtitle system based on [SenseVoice](https://github.com/FunAudioLLM/SenseVoice), supporting high-quality dual-stream audio architecture, speech recognition, real-time translation, and floating subtitle display. Suitable for meeting recordings, real-time translation, live streaming subtitles, and other scenarios.

---

## 🆕 v2.0 Updates

### 🎵 Dual-Stream Audio Architecture
- **🔥 Brand New Dual-Stream Architecture**: ASR Stream (16kHz) + Recording Stream (48kHz), solving audio quality issues
- **📡 Smart Stream Separation**: Real-time subtitles use 16kHz, recordings save with original high sample rate
- **🎧 Eliminate Downsampling Noise**: System audio no longer forced to 16kHz, avoiding electrical noise
- **🔄 Full Compatibility**: Maintains original single-stream architecture, users can choose freely

### 💾 Recording Features
- **💾 Export Complete Recordings**: Support WAV format audio export, preserving original audio quality
- **📝 Subtitle Export**: Support timestamped TXT format subtitle files
- **🎞️ Recording Management**: Unified subtitle and audio file management interface
- **📂 Smart Archiving**: Automatic matching and archiving of recording and subtitle files

### 🛠️ Interaction Optimization
- **⚡ Immediate Response**: Export dialog shows immediately after recording ends
- **📁 Smart Buttons**: Dual-stream architecture shows "Open Folder", single-stream shows "Export Audio"
- **✅ Accurate Prompts**: Fixed false "No audio data received" error messages
- **🎯 Correct Paths**: Open recording folder function points to correct `python/recordings` directory

### 🧹 Project Cleanup
- **📂 Simplified Structure**: Cleaned development process files, retained core functions
- **🔧 Streamlined Modules**: Only retain original single-stream and enhanced dual-stream architectures
- **📖 Unified Launcher**: Unified service selection and startup interface

---

## 🔧 Project Introduction

**Realtime Caption** is a local real-time subtitle tool running on Windows platform, supporting real-time extraction of speech content from system audio, automatic speech recognition (ASR) through large models, and real-time subtitle display in floating windows.

### 🏗️ Dual-Stream Architecture Advantages
- **ASR Stream**: 16kHz mono, specially optimized for real-time subtitle recognition performance
- **Recording Stream**: 48kHz stereo, maintains original audio quality, supports 24-bit high-fidelity
- **Smart Resampling**: Supports scipy, librosa, numpy multiple algorithms
- **Zero Latency**: Dual-stream parallel processing, doesn't affect real-time subtitle response speed

---

## ✨ Key Features

* ✅ **Dual-Stream Audio Architecture**: Separate ASR and recording processing, balancing real-time performance and audio quality
* 🎤 **System Audio Capture**: Based on WASAPI Loopback to capture system playback sounds
* 🧠 **Speech Recognition Model**: Integrated SenseVoice local large model, supports Mandarin recognition
* 🌐 **WebSocket Communication**: Real-time audio transmission and recognition result feedback
* 🌍 **Real-Time Translation**: Support nllb200 multilingual model, real-time subtitle translation
* 🪟 **Floating Subtitle Window**: Electron-based clean subtitle window
* 📁 **Recording Management**: Support high-quality recording export and folder management
* 🔒 **Local Execution**: Full local processing, ensuring data privacy

---

## 📁 Project Structure

```
realtime-caption-mvp/
├── python/                    # Audio Service Core Modules
│   ├── audio_capture_websocket.py      # Original single-stream architecture (stable)
│   ├── enhanced_dual_audio_service.py  # Enhanced dual-stream architecture (recommended)
│   ├── audio_service_launcher.py       # Service launcher
│   ├── asr_server.py                   # ASR recognition service
│   ├── websocket_server.py             # WebSocket communication service
│   ├── backend_launcher.py             # Backend service launcher
│   └── recordings/                     # Recording output directory
├── a4s/                       # AI Model Service
│   ├── server_wss_split.py    # WebSocket server
│   ├── model.py              # Model management
│   └── config.py             # Configuration management
├── electron/                  # Frontend Interface
│   ├── main.js               # Main process
│   ├── renderer.js           # Renderer process
│   ├── index.html            # Interface file
│   └── preload.js            # Preload script
├── requirements.txt           # Python dependencies
└── README.md
```

---

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Clone project
git clone https://github.com/orangeburn/Realtime-Caption.git
cd realtime-caption-mvp

# Create Python environment
conda create -n realtime-caption python=3.10
conda activate realtime-caption
conda install -c conda-forge ffmpeg

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
cd electron
npm install
cd ..
```

### 2. Launch Methods

#### 🎯 Recommended Method (Dual-Stream Architecture)

```bash
# 1. Start backend service
python python/backend_launcher.py

# 2. Start audio service (recommended dual-stream architecture)
python python/audio_service_launcher.py

# 3. Start frontend interface
cd electron && npm start
```

#### 🔄 Traditional Method (Single-Stream Architecture)

```bash
# 1. Start backend
python a4s/server_wss_split.py

# 2. Start audio capture
python python/audio_capture_websocket.py

# 3. Start frontend
cd electron && npm start
```

### 3. Using Audio Service Launcher

```bash
# Interactive selection
python python/audio_service_launcher.py

# Direct dual-stream architecture launch
python python/audio_service_launcher.py --enhanced

# Direct single-stream architecture launch
python python/audio_service_launcher.py --legacy
```

---

## 🎵 Audio Architecture Selection

### 🆕 Enhanced Dual-Stream Architecture (Recommended)
- **Use Cases**: Need high-quality recording, eliminate system audio noise
- **Advantages**:
  - 48kHz stereo high-quality recording
  - Eliminate 16kHz downsampling electrical noise
  - Dual-stream parallel, doesn't affect real-time subtitle performance
- **File Output**: Generate both standard quality and high-quality recording files

### 🔄 Original Single-Stream Architecture (Stable)
- **Use Cases**: Production environment, low recording quality requirements
- **Advantages**:
  - Fully tested, stable and reliable
  - Low resource usage, low latency
  - Good compatibility

### 📊 Architecture Comparison

| Feature | Single-Stream | Dual-Stream |
|---------|-------------|-------------|
| Real-time Performance | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Recording Quality | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| System Audio Noise | Has electrical noise | No noise |
| Resource Usage | Low | Medium |
| Stability | Very High | High |
| Production Ready | ✅ | ✅ |

---

## 🎛️ Feature Description

### Recording Mode
1. **Start Recording**: Click recording button to start recording
2. **Real-time Subtitles**: Display real-time recognized subtitles during recording
3. **End Recording**: Export options displayed immediately after stopping
4. **File Management**:
   - **Single-Stream**: Generate 16kHz WAV files
   - **Dual-Stream**: Generate both standard (16kHz) and high-quality (48kHz) files

### Export Functions
- **📝 Export Subtitles**: Export timestamped TXT format subtitle files
- **🎵 Export Audio**:
  - Single-stream: Download audio files to local
  - Dual-stream: Open recording folder to view all files
- **📁 Open Folder**: Direct access to recording file save directory

### Device Management
- **🔍 Auto Detection**: Smart recognition of available audio devices
- **🎯 Priority Selection**: Prioritize system audio devices (stereo mix)
- **🔄 Dynamic Switching**: Switch different audio input devices at runtime
- **🎤 Device Types**: Support microphone, system output, and other device types

---

## 📦 Automatic Model Management

**Model files are automatically managed, no manual download required!**

- ✅ **ASR Model**: SenseVoice speech recognition model auto-download
- ✅ **Translation Model**: nllb200 translation model auto-download  
- ✅ **Model Hot Updates**: Support runtime dynamic updates
- 🔧 **Inference Optimization**: Use CTranslate2 high-performance inference engine

---

## 🛠️ Development Notes

### Core File Descriptions

#### Python Services
- `audio_capture_websocket.py`: Single-stream audio capture, unified 16kHz processing
- `enhanced_dual_audio_service.py`: Dual-stream audio capture, ASR+recording separation
- `audio_service_launcher.py`: Service selection and startup management
- `asr_server.py`: SenseVoice ASR recognition service
- `websocket_server.py`: Frontend-backend WebSocket communication

#### Frontend Interface
- `main.js`: Electron main process, window management
- `renderer.js`: Renderer process, interface logic and WebSocket communication
- `index.html`: Subtitle display interface

### Audio Processing Flow

#### Single-Stream Architecture
```
Audio Input → 16kHz Resampling → ASR Recognition + Recording Save
```

#### Dual-Stream Architecture  
```
Audio Input ┬→ 16kHz Mono → ASR Recognition → Real-time Subtitles
            └→ 48kHz Stereo → High-quality Recording → Local Save
```

---

## 🧩 Dependency Management

### Python Dependencies
```bash
# Core dependencies
sounddevice>=0.4.6    # Audio capture
websockets>=11.0      # WebSocket communication
numpy>=1.24.0         # Numerical computation
scipy>=1.11.0         # Signal processing (resampling)
librosa>=0.10.0       # Audio processing (optional)

# AI model dependencies
transformers>=4.30.0  # SenseVoice model
ctranslate2>=3.0.0    # Translation inference engine
```

### Node.js Dependencies
```bash
cd electron
npm install  # Install Electron and related dependencies
```

### System Requirements
- **OS**: Windows 10/11
- **Python**: 3.8-3.11
- **Node.js**: 16.0+
- **Memory**: 8GB+ recommended
- **Storage**: ~2GB for model files

---

## 📝 Usage Tips

### Audio Device Selection
1. **System Audio Recording**: Select "Stereo Mix" or "What U Hear"
2. **Microphone Recording**: Select specific microphone device
3. **Device Troubleshooting**: Use launcher's "View Audio Device List" function

### Recording Quality Optimization
- **Dual-Stream Architecture**: Automatically use device's best sample rate
- **Resampling Algorithm**: Priority scipy > librosa > numpy
- **Stereo Recording**: Maintain original channel information of system audio

### Real-time Performance Tuning
- **Chunk Size**: Default 0.5-second audio chunks, balancing real-time and accuracy
- **Sample Rate Matching**: ASR fixed at 16kHz, recording maintains original sample rate
- **Device Compatibility**: Automatic detection and adaptation of different audio devices

---

## 🙏 Acknowledgments

* [SenseVoice (by Alibaba DAMO Academy)](https://github.com/FunAudioLLM/SenseVoice) — Core automatic speech recognition model
* [api4sensevoice](https://github.com/0x5446/api4sensevoice) — Lightweight service implementation based on SenseVoice
* [CTranslate2](https://github.com/OpenNMT/CTranslate2) — High-performance inference engine
* [nllb-200](https://github.com/facebookresearch/fairseq/tree/nllb) — Multilingual translation model

---

## 📜 License

This project is open-sourced under [MIT License](./LICENSE).

---

## 🚦 Changelog

### v2.0.0 (2025-01-05)
- ✨ Brand new dual-stream audio architecture, solving system audio downsampling noise issues
- 🎯 Optimized recording completion interaction, immediately show export options
- 📁 Fixed recording folder path, correctly pointing to python/recordings
- 🧹 Project structure cleanup, removed redundant files and modules
- 🔧 Unified service launcher, supporting architecture selection
- 💡 Smart button display, adjusting interface based on architecture type

### v1.5.0 (2024-12-20)
- 🔄 Frontend interaction optimization
- 🤖 ASR model and translation model unified management
- 🔥 Support model hot updates
- 🎛️ Optimized audio capture device filtering logic

---

## 🗺️ Roadmap

### ✅ Completed Features
- [x] Audio capture python module
- [x] Real-time translation model nllb200-ct2 integration
- [x] Frontend interface setup
- [x] Capture module, frontend and backend reconnection
- [x] Translation subtitle target language switching
- [x] Stereo audio capture/microphone capture switching
- [x] Offline operation error fixes
- [x] Frontend interaction optimization
- [x] ASR model and translation model unified management, auto-download on first backend run
- [x] Model hot update support
- [x] Optimized audio capture device filtering logic
- [x] **Dual-stream audio architecture** - ASR stream and recording stream separate processing
- [x] **High-quality recording** - 48kHz stereo recording, eliminate downsampling noise
- [x] **Recording file export** - Support local file save and folder management
- [x] **Subtitle export** - TXT format timestamped subtitle files
- [x] **Interaction optimization** - Immediately show export options after recording completion
- [x] **Project structure cleanup** - Remove redundant files, retain core functions

### 💡 Features Under Research
- [ ] Real-time speech emotion analysis
- [ ] Multi-language mixed recognition
- [ ] Automatic meeting summary generation
- [ ] Real-time speech translation (speech output)

---

## 🤝 Contributing

Welcome all forms of contributions:

1. **Bug Reports**: Submit Issues describing problems
2. **Feature Suggestions**: Discuss new feature requirements
3. **Code Contributions**: Fork project, submit Pull Requests
4. **Documentation Improvement**: Improve documentation and usage instructions
5. **Testing Support**: Test functionality in different environments

### Development Environment Setup
```bash
# Development mode startup
npm run dev      # Frontend development mode
python -m pytest # Run tests (if available)
```

---

**🎉 Enjoy high-quality local real-time subtitle experience!**