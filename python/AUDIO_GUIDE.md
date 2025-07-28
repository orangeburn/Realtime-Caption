# 音频采集系统使用指南

## 🎯 核心功能

实时字幕项目支持两种核心音频采集能力：

### 1. 🎤 麦克风录音
- **用途**: 捕获用户语音输入
- **场景**: 会议记录、语音输入、口述转文字
- **设备**: 内置麦克风、外接麦克风、麦克风阵列

### 2. 🔊 系统音频捕获
- **用途**: 捕获本地系统播放的音频
- **场景**: 视频字幕、音乐识别、游戏音频转文字
- **设备**: 立体声混音、Loopback设备、虚拟音频线缆

## 🚀 快速启动

### 交互式启动器 (推荐)
```bash
cd python
python audio_launcher.py
```

### 命令行启动

#### 麦克风模式
```bash
python unified_audio_capture.py --mode microphone
```

#### 系统音频模式  
```bash
python unified_audio_capture.py --mode system_audio
```

#### 自动模式 (优先系统音频)
```bash
python unified_audio_capture.py --mode auto
```

#### 指定设备
```bash
python unified_audio_capture.py --device 11 --mode system_audio
```

#### 查看可用设备
```bash
python unified_audio_capture.py --list
```

## 📋 设备配置

### Windows 系统音频设置

#### 启用立体声混音
1. 右键任务栏音量图标 → "声音"
2. 切换到 "录制" 标签
3. 右键空白处 → "显示禁用的设备"
4. 找到 "立体声混音" → 右键 → "启用"
5. 右键 "立体声混音" → "设为默认设备"

#### 检查隐私设置
1. Windows设置 → 隐私和安全性 → 麦克风
2. 确保 "允许应用访问麦克风" 已开启
3. 确保 "允许桌面应用访问麦克风" 已开启

### 虚拟音频线缆 (备选方案)

如果立体声混音不可用，可安装虚拟音频设备：

#### VB-Audio Virtual Cable (免费)
- 下载: https://vb-audio.com/Cable/
- 安装后出现 'CABLE Input' 和 'CABLE Output'
- 设置: 系统音频输出 → CABLE Input
- 采集: 选择 CABLE Output 作为录制设备

#### VoiceMeeter (免费，功能强大)
- 下载: https://vb-audio.com/Voicemeeter/
- 提供虚拟混音台功能
- 可同时处理多个音频源

## 🔧 技术特性

### 音频处理能力
- **采样率**: 自动重采样到16kHz (后端要求)
- **声道**: 自动转换为单声道
- **格式**: 16-bit PCM
- **延迟**: 500ms块大小，低延迟处理

### 设备兼容性
- **自动检测**: 智能识别麦克风和系统音频设备
- **动态配置**: 自适应采样率和声道数
- **错误处理**: 自动跳过不可用设备
- **重连机制**: WebSocket断线自动重连

### 支持的设备类型
- 内置麦克风
- 外接USB麦克风
- 麦克风阵列
- 立体声混音 (Stereo Mix)
- Loopback设备
- 虚拟音频线缆
- 专业音频接口

## 🛠 故障排除

### 常见问题

#### 找不到系统音频设备
```bash
# 运行诊断工具
python fix_system_audio.py
```

#### 设备列表为空
```bash
# 检查设备
python list_devices.py
```

#### 音频质量测试
```bash
# 验证音频参数
python validate_audio_params.py
```

#### 设备采样率测试
```bash
# 测试所有设备配置
python test_device_rates.py
```

### 错误代码

- `Invalid number of channels`: 设备无输入通道
- `Invalid sample rate`: 设备不支持所需采样率
- `WebSocket closed`: 后端服务器连接问题
- `No recordable devices`: 没有可用的音频设备

## 📊 性能建议

### 最佳实践
1. **系统音频捕获**: 优先使用立体声混音
2. **麦克风录音**: 选择质量较好的麦克风设备
3. **网络**: 确保WebSocket服务器稳定运行
4. **权限**: 确保应用有音频设备访问权限

### 资源占用
- **CPU**: 重采样和格式转换 (轻量级)
- **内存**: 音频缓冲区 (小于10MB)
- **网络**: 约64kbps (16kHz 单声道 16-bit)

## 🔗 相关文件

- `unified_audio_capture.py` - 统一音频采集核心
- `audio_launcher.py` - 交互式启动器
- `audio_capture_websocket.py` - 原始通用采集器
- `system_audio_capture.py` - 专用系统音频采集器
- `fix_system_audio.py` - 系统音频诊断工具