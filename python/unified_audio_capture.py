#!/usr/bin/env python3
"""
统一音频采集模块
支持两种核心音频采集能力：
1. 本地系统输出音频捕获（播放的音乐、视频等）
2. 麦克风录音捕获（用户语音输入）
"""

import asyncio
import websockets
import sounddevice as sd
import numpy as np
import json
import sys
import argparse
import time
from enum import Enum

# 引入现有模块的功能
from audio_capture_websocket import (
    resample_audio, convert_to_mono, find_supported_samplerate,
    detect_device_optimal_channels, is_recordable_device, 
    validate_audio_format, AudioStreamer
)
from system_audio_capture import list_system_audio_devices, find_best_system_audio_device

SAMPLE_RATE = 16000  # 后端固定要求16kHz
CHANNELS = 1         # 后端要求单声道
BIT_DEPTH = 16       # 后端要求16-bit
CHUNK_DURATION = 0.5 # 0.5秒块大小

class AudioCaptureMode(Enum):
    """音频采集模式"""
    MICROPHONE = "microphone"      # 麦克风录音
    SYSTEM_AUDIO = "system_audio"  # 系统音频输出
    AUTO = "auto"                  # 自动选择最佳设备

class UnifiedAudioCapture:
    """统一音频采集器"""
    
    def __init__(self, mode=AudioCaptureMode.AUTO, device_index=None):
        self.mode = mode
        self.device_index = device_index
        self.ws = None
        self.running = True
        self.audio_queue = None
        self.loop = None
        self.ws_connected = False
        self.current_samplerate = SAMPLE_RATE
        self.target_samplerate = SAMPLE_RATE
        self.device_channels = 1
        
    def list_available_devices(self):
        """列出所有可用的音频设备，按类型分组"""
        devices = sd.query_devices()
        microphone_devices = []
        system_audio_devices = []
        
        print("\n🎵 统一音频设备列表")
        print("=" * 50)
        
        for i, dev in enumerate(devices):
            if not is_recordable_device(i):
                continue
                
            device_name = dev['name'].strip()
            max_input = dev['max_input_channels']
            
            # 检查设备类型
            name_lower = device_name.lower()
            system_keywords = [
                "stereo mix", "立体声混音", "what u hear", "您听到的声音",
                "loopback", "wave out mix", "混音", "录制混音"
            ]
            
            is_system_device = any(keyword in name_lower for keyword in system_keywords)
            
            device_info = {
                "index": i,
                "name": device_name,
                "max_input_channels": max_input,
                "default_samplerate": dev['default_samplerate']
            }
            
            if is_system_device:
                system_audio_devices.append(device_info)
                print(f"🔊 [{i}] {device_name} (系统音频)")
            else:
                microphone_devices.append(device_info)
                print(f"🎤 [{i}] {device_name} (麦克风)")
        
        print(f"\n📊 设备统计:")
        print(f"  麦克风设备: {len(microphone_devices)} 个")
        print(f"  系统音频设备: {len(system_audio_devices)} 个")
        
        return microphone_devices, system_audio_devices
    
    def select_device_by_mode(self):
        """根据模式选择最佳设备"""
        microphone_devices, system_audio_devices = self.list_available_devices()
        
        if self.device_index is not None:
            # 用户指定了设备
            if is_recordable_device(self.device_index):
                print(f"✅ 使用指定设备: [{self.device_index}]")
                return self.device_index
            else:
                print(f"❌ 指定设备[{self.device_index}]不可用")
                sys.exit(1)
        
        if self.mode == AudioCaptureMode.MICROPHONE:
            # 麦克风模式：优先选择麦克风设备
            if microphone_devices:
                selected = microphone_devices[0]
                print(f"🎤 麦克风模式 - 选择设备: [{selected['index']}] {selected['name']}")
                return selected['index']
            else:
                print("❌ 未找到可用的麦克风设备")
                sys.exit(1)
                
        elif self.mode == AudioCaptureMode.SYSTEM_AUDIO:
            # 系统音频模式：优先选择系统音频设备
            if system_audio_devices:
                selected = system_audio_devices[0]
                print(f"🔊 系统音频模式 - 选择设备: [{selected['index']}] {selected['name']}")
                return selected['index']
            else:
                print("❌ 未找到可用的系统音频设备")
                print("💡 请启用立体声混音或安装虚拟音频线缆")
                sys.exit(1)
                
        else:  # AUTO模式
            # 自动模式：优先系统音频，备选麦克风
            if system_audio_devices:
                selected = system_audio_devices[0]
                print(f"🔊 自动模式 - 选择系统音频设备: [{selected['index']}] {selected['name']}")
                return selected['index']
            elif microphone_devices:
                selected = microphone_devices[0]
                print(f"🎤 自动模式 - 选择麦克风设备: [{selected['index']}] {selected['name']}")
                return selected['index']
            else:
                print("❌ 未找到任何可用的音频设备")
                sys.exit(1)
    
    def audio_callback(self, indata, frames, time_info, status):
        """统一音频回调处理"""
        if status:
            print(f"⚠️ 音频状态: {status}")
        
        try:
            # 显示采集信息
            max_amplitude = np.max(np.abs(indata))
            mode_icon = "🔊" if self.mode == AudioCaptureMode.SYSTEM_AUDIO else "🎤"
            print(f"{mode_icon} 音频: shape={indata.shape}, max_amp={max_amplitude:.4f}", end=" ")
            
            # 第1步：转换为单声道
            audio_mono = convert_to_mono(indata)
            
            # 第2步：重采样到16kHz（如果需要）
            if self.current_samplerate != self.target_samplerate:
                audio_resampled = resample_audio(audio_mono, self.current_samplerate, self.target_samplerate)
                print(f"重采样: {self.current_samplerate}Hz→{self.target_samplerate}Hz", end=" ")
            else:
                audio_resampled = audio_mono
            
            # 第3步：验证最终格式
            is_valid, msg = validate_audio_format(audio_resampled, self.target_samplerate)
            if not is_valid:
                print(f"❌ 音频格式验证失败: {msg}")
                return
            
            # 第4步：转换为int16 PCM格式
            audio_normalized = np.clip(audio_resampled, -1.0, 1.0)
            pcm_int16 = (audio_normalized * 32767).astype(np.int16)
            pcm_bytes = pcm_int16.tobytes()
            
            final_amplitude = np.max(np.abs(audio_normalized))
            print(f"最终: {len(pcm_bytes)}bytes, amp={final_amplitude:.4f}")
            
            # 第5步：发送到队列
            try:
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pcm_bytes)
            except RuntimeError as e:
                print(f"❌ 无法放入音频数据队列: {e}")
                
        except Exception as e:
            print(f"❌ 音频处理异常: {e}")
            import traceback
            traceback.print_exc()
    
    async def send_audio(self):
        """发送音频数据到WebSocket"""
        mode_name = "系统音频" if self.mode == AudioCaptureMode.SYSTEM_AUDIO else "麦克风"
        print(f"🚀 {mode_name}发送协程启动")
        
        try:
            while self.running:
                if not self.ws or self.ws.state != websockets.protocol.State.OPEN:
                    await asyncio.sleep(0.2)
                    continue
                    
                try:
                    pcm_data = await self.audio_queue.get()
                    await self.ws.send(pcm_data)
                    print(f"📤 {mode_name}数据: {len(pcm_data)} bytes")
                except websockets.ConnectionClosed:
                    print(f"❌ {mode_name} WebSocket连接断开")
                    self.ws_connected = False
                    raise
                except Exception as e:
                    print(f"⚠️ 发送{mode_name}异常: {e}")
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            print(f"{mode_name}发送任务已取消")
    
    async def recv_msgs(self):
        """接收WebSocket消息"""
        try:
            async for message in self.ws:
                try:
                    if message.startswith('{'):
                        data = json.loads(message)
                        if 'text' in data:
                            print(f"💬 识别结果: {data['text']}")
                        elif 'switch_mode' in data:
                            # 支持动态切换模式
                            new_mode = data['switch_mode']
                            print(f"🔄 切换音频模式: {new_mode}")
                            # 这里可以添加模式切换逻辑
                except Exception as e:
                    print(f"⚠️ 消息解析失败: {e}")
        except websockets.ConnectionClosed:
            print("❌ 接收消息连接断开")
            self.ws_connected = False
            raise
    
    async def run(self, ws_url):
        """主运行循环"""
        # 选择设备
        self.device_index = self.select_device_by_mode()
        
        mode_name = "系统音频" if self.mode == AudioCaptureMode.SYSTEM_AUDIO else "麦克风"
        print(f"🎵 {mode_name}采集器启动")
        
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
                    
                    # 配置音频采集
                    try:
                        # 检测设备最佳配置
                        self.device_channels = detect_device_optimal_channels(self.device_index)
                        if self.device_channels is None:
                            raise Exception("设备无输入通道")
                        
                        supported_rate = find_supported_samplerate(self.device_index, SAMPLE_RATE)
                        if supported_rate:
                            self.current_samplerate = supported_rate
                        else:
                            raise Exception("设备不支持任何采样率")
                        
                        print(f"🔧 音频配置:")
                        print(f"   模式: {mode_name}")
                        print(f"   设备: [{self.device_index}]")
                        print(f"   采样率: {self.current_samplerate}Hz → {self.target_samplerate}Hz")
                        print(f"   声道: {self.device_channels}")
                        
                        # 启动音频流
                        actual_chunk_size = int(self.current_samplerate * CHUNK_DURATION)
                        
                        with sd.InputStream(
                            samplerate=self.current_samplerate,
                            channels=self.device_channels,
                            dtype='float32',
                            blocksize=actual_chunk_size,
                            callback=self.audio_callback,
                            device=self.device_index):
                            
                            print(f"🎤 开始{mode_name}采集")
                            
                            # 保持运行
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
    parser = argparse.ArgumentParser(description="统一音频采集与实时字幕")
    parser.add_argument('--uri', type=str, 
                      default="ws://127.0.0.1:27000/ws/upload", 
                      help='WebSocket服务器地址')
    parser.add_argument('--mode', type=str, 
                      choices=['microphone', 'system_audio', 'auto'],
                      default='auto',
                      help='音频采集模式: microphone(麦克风), system_audio(系统音频), auto(自动)')
    parser.add_argument('--device', type=int, 
                      help='指定音频设备索引')
    parser.add_argument('--list', action='store_true',
                      help='列出可用设备并退出')
    
    args = parser.parse_args()
    
    # 转换模式
    mode_map = {
        'microphone': AudioCaptureMode.MICROPHONE,
        'system_audio': AudioCaptureMode.SYSTEM_AUDIO,
        'auto': AudioCaptureMode.AUTO
    }
    mode = mode_map[args.mode]
    
    # 创建采集器
    capturer = UnifiedAudioCapture(mode=mode, device_index=args.device)
    
    if args.list:
        capturer.list_available_devices()
        return
    
    print(f"🎯 启动模式: {args.mode}")
    
    try:
        asyncio.run(capturer.run(args.uri))
    except KeyboardInterrupt:
        print("\n🚦 正在停止...")
        capturer.stop()
        time.sleep(1)
        print("✅ 程序已退出")

if __name__ == "__main__":
    main()