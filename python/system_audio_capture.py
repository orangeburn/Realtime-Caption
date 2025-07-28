#!/usr/bin/env python3
"""
系统音频捕获模块 - 支持Windows WASAPI Loopback模式
用于捕获本地系统输出音频（如播放的音乐、视频等）
"""

import asyncio
import websockets
import sounddevice as sd
import numpy as np
import json
import sys
import argparse
import time

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("⚠️ PyAudio 未安装，将使用 sounddevice 替代")

SAMPLE_RATE = 16000  # 后端固定要求16kHz
CHANNELS = 1         # 后端要求单声道  
BIT_DEPTH = 16       # 后端要求16-bit
CHUNK_DURATION = 0.5 # 0.5秒块大小
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)  # 8000 samples

def resample_audio(audio_data, source_rate, target_rate):
    """高质量音频重采样"""
    if source_rate == target_rate:
        return audio_data
    
    try:
        # 优先使用scipy进行高质量重采样
        import scipy.signal
        target_length = int(len(audio_data) * target_rate / source_rate)
        resampled = scipy.signal.resample(audio_data, target_length, axis=0)
        return resampled.astype(np.float32)
    except ImportError:
        # 如果没有scipy，使用numpy插值
        try:
            original_indices = np.arange(len(audio_data))
            target_length = int(len(audio_data) * target_rate / source_rate)
            target_indices = np.linspace(0, len(audio_data) - 1, target_length)
            resampled = np.interp(target_indices, original_indices, audio_data.flatten())
            return resampled.astype(np.float32).reshape(-1, 1)
        except Exception as e:
            print(f"⚠️ 重采样失败，使用原始数据: {e}")
            return audio_data

def convert_to_mono(audio_data):
    """转换为单声道"""
    if len(audio_data.shape) == 1:
        return audio_data.reshape(-1, 1)
    elif audio_data.shape[1] == 1:
        return audio_data
    else:
        # 多声道转单声道：取平均值
        return np.mean(audio_data, axis=1, keepdims=True).astype(np.float32)

def list_system_audio_devices():
    """列出所有支持系统音频捕获的设备"""
    devices = sd.query_devices()
    device_list = []
    seen_names = set()
    
    print("\n🔊 系统音频捕获设备列表：")
    
    # 查找系统音频输出设备的loopback模式
    loopback_keywords = [
        "loopback", "stereo mix", "立体声混音", "what u hear", "您听到的声音",
        "wave out mix", "混音", "录制混音", "speaker", "扬声器"
    ]
    
    output_devices = []
    
    for i, dev in enumerate(devices):
        name = dev['name'].strip().lower()
        
        # 检查是否为系统音频输出loopback设备
        is_loopback = any(k in name for k in loopback_keywords)
        has_input = dev['max_input_channels'] > 0
        
        if is_loopback or (has_input and "mix" in name):
            display_name = dev['name'].strip()
            if display_name in seen_names or display_name == "":
                continue
            seen_names.add(display_name)
            
            try:
                # 测试设备是否可用
                sd.check_input_settings(device=i, samplerate=SAMPLE_RATE, channels=CHANNELS)
                print(f"  ✅ [{i}] {display_name}")
                device_list.append({
                    "index": i, 
                    "name": display_name,
                    "type": "系统音频"
                })
            except Exception as e:
                print(f"  ❌ [{i}] {display_name} (不可用: {e})")
        
        # 同时记录输出设备信息
        if dev['max_output_channels'] > 0:
            output_devices.append({"index": i, "name": dev['name'].strip()})
    
    if not device_list:
        print("❌ 未找到可用的系统音频捕获设备")
        print("\n💡 解决方案：")
        print("1. Windows: 启用「立体声混音」设备")
        print("   - 右键音量图标 → 声音 → 录制 → 启用立体声混音")
        print("2. 安装虚拟音频线缆 (VB-Audio Cable)")
        print("3. 使用专业音频接口")
        
        if output_devices:
            print(f"\n📋 检测到 {len(output_devices)} 个输出设备，但无法直接录制：")
            for dev in output_devices[:5]:  # 只显示前5个
                print(f"   🔊 [{dev['index']}] {dev['name']}")
    
    return device_list

def find_best_system_audio_device():
    """自动选择最佳的系统音频设备"""
    device_list = list_system_audio_devices()
    
    if not device_list:
        return None, None
    
    # 优先级：立体声混音 > loopback > 其他
    priority_keywords = [
        ["立体声混音", "stereo mix"],
        ["loopback"],
        ["what u hear", "您听到的声音"],
        ["wave out mix", "混音"]
    ]
    
    for keywords in priority_keywords:
        for device in device_list:
            name_lower = device['name'].lower()
            if any(k in name_lower for k in keywords):
                return device['index'], device['name']
    
    # 如果没有优先设备，返回第一个可用设备
    return device_list[0]['index'], device_list[0]['name']

class SystemAudioStreamer:
    """系统音频流处理器"""
    
    def __init__(self, device_index=None):
        self.device_index = device_index
        self.ws = None
        self.running = True
        self.audio_queue = None
        self.loop = None
        self.input_stream = None
        self.ws_connected = False
        self.current_samplerate = SAMPLE_RATE  # 当前使用的采样率
        self.target_samplerate = SAMPLE_RATE   # 目标采样率（固定16kHz）
        
    def audio_callback(self, indata, frames, time_info, status):
        """音频回调函数 - 确保输出严格符合后端要求"""
        if status:
            print(f"⚠️ 音频状态: {status}")
            
        try:
            # 第1步：转换为单声道
            audio_mono = convert_to_mono(indata)
            
            # 第2步：重采样到16kHz（如果需要）
            if self.current_samplerate != self.target_samplerate:
                audio_resampled = resample_audio(audio_mono, self.current_samplerate, self.target_samplerate)
                print(f"🔄 系统音频重采样: {self.current_samplerate}Hz → {self.target_samplerate}Hz")
            else:
                audio_resampled = audio_mono
            
            # 第3步：确保数据在[-1, 1]范围内并转换为int16 PCM
            audio_normalized = np.clip(audio_resampled, -1.0, 1.0)
            pcm_int16 = (audio_normalized * 32767).astype(np.int16)
            pcm_data = pcm_int16.tobytes()
            
            print(f"🔊 系统音频: {indata.shape}@{self.current_samplerate}Hz → {audio_resampled.shape}@{self.target_samplerate}Hz")
            print(f"📦 PCM数据: {len(pcm_data)} bytes")
            
            try:
                if self.loop and self.audio_queue:
                    self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pcm_data)
            except Exception as e:
                print(f"❌ 系统音频队列错误: {e}")
                
        except Exception as e:
            print(f"❌ 系统音频处理异常: {e}")
            import traceback
            traceback.print_exc()
    
    async def send_audio(self):
        """发送音频数据到WebSocket"""
        print("🚀 系统音频发送协程启动")
        
        try:
            while self.running:
                if not self.ws or self.ws.state != websockets.protocol.State.OPEN:
                    await asyncio.sleep(0.2)
                    continue
                    
                try:
                    pcm_data = await self.audio_queue.get()
                    await self.ws.send(pcm_data)
                    print(f"📤 系统音频数据: {len(pcm_data)} bytes")
                except websockets.ConnectionClosed:
                    print("❌ WebSocket连接断开")
                    self.ws_connected = False
                    raise
                except Exception as e:
                    print(f"⚠️ 发送音频异常: {e}")
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            print("系统音频发送任务已取消")
    
    async def recv_msgs(self):
        """接收WebSocket消息"""
        try:
            async for message in self.ws:
                try:
                    if message.startswith('{'):
                        data = json.loads(message)
                        if 'text' in data:
                            print(f"💬 识别结果: {data['text']}")
                except Exception as e:
                    print(f"⚠️ 消息解析失败: {e}")
        except websockets.ConnectionClosed:
            print("❌ 接收消息连接断开")
            self.ws_connected = False
            raise
    
    async def run(self, ws_url):
        """主运行循环"""
        print("🎵 系统音频捕获器启动")
        self.loop = asyncio.get_running_loop()
        self.audio_queue = asyncio.Queue()
        
        while self.running:
            try:
                print(f"🔗 连接到: {ws_url}")
                async with websockets.connect(ws_url) as websocket:
                    self.ws = websocket
                    self.ws_connected = True
                    print("✅ WebSocket已连接")
                    
                    # 启动任务
                    recv_task = asyncio.create_task(self.recv_msgs())
                    send_task = asyncio.create_task(self.send_audio())
                    
                    # 启动音频捕获
                    try:
                        with sd.InputStream(
                            samplerate=SAMPLE_RATE,
                            channels=2,  # 立体声输入
                            dtype='float32',
                            blocksize=CHUNK_SIZE,
                            callback=self.audio_callback,
                            device=self.device_index):
                            
                            print(f"🎤 开始捕获系统音频 (设备: {self.device_index})")
                            
                            # 保持运行直到连接断开
                            while self.ws_connected:
                                await asyncio.sleep(0.1)
                                
                    except Exception as e:
                        print(f"❗ 音频流异常: {e}")
                        
                    # 清理任务
                    for task in [recv_task, send_task]:
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                            
            except Exception as e:
                print(f"❗ 连接异常: {e}")
                print("🔁 3秒后重连...")
                await asyncio.sleep(3)
    
    def stop(self):
        """停止运行"""
        self.running = False

def main():
    parser = argparse.ArgumentParser(description="系统音频捕获与实时字幕")
    parser.add_argument('--uri', type=str, 
                      default="ws://127.0.0.1:27000/ws/upload", 
                      help='WebSocket服务器地址')
    parser.add_argument('--device', type=int, 
                      help='指定音频设备索引')
    parser.add_argument('--list', action='store_true',
                      help='列出可用设备并退出')
    
    args = parser.parse_args()
    
    if args.list:
        list_system_audio_devices()
        return
    
    # 选择音频设备
    if args.device is not None:
        device_index = args.device
        print(f"✅ 使用指定设备: {device_index}")
        # 验证指定设备是否可用
        try:
            sd.check_input_settings(device=device_index, samplerate=SAMPLE_RATE, channels=1)
        except Exception as e:
            print(f"❌ 指定设备[{device_index}]不可用: {e}")
            sys.exit(1)
    else:
        device_index, device_name = find_best_system_audio_device()
        if device_index is None:
            print("❌ 未找到可用的系统音频设备，程序退出")
            sys.exit(1)
        print(f"✅ 自动选择设备: [{device_index}] {device_name}")
    
    # 启动音频流
    streamer = SystemAudioStreamer(device_index)
    
    try:
        asyncio.run(streamer.run(args.uri))
    except KeyboardInterrupt:
        print("\n🚦 正在停止...")
        streamer.stop()
        time.sleep(1)
        print("✅ 程序已退出")

if __name__ == "__main__":
    main()