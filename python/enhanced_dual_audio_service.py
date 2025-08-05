#!/usr/bin/env python3
"""
集成双音频流服务 - 基于原有架构增强
在保持原有 audio_capture_websocket.py 所有功能的基础上，增加高质量录音流
"""

import asyncio
import websockets
import sounddevice as sd
import numpy as np
import json
import sys
import argparse
import time
import wave
import os
from datetime import datetime
from pathlib import Path

# 原有ASR配置 - 保持不变，确保兼容性
SAMPLE_RATE = 16000  # 后端固定要求16kHz
CHANNELS = 1         # 后端要求单声道
BIT_DEPTH = 16       # 后端要求16-bit
CHUNK_DURATION = 0.5 # 0.5秒块大小
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)  # 8000 samples

# 高质量录音配置 - 新增双流功能
RECORD_SAMPLE_RATE = 48000  # 高质量录音采样率
RECORD_CHANNELS = 2         # 立体声录音
RECORD_BIT_DEPTH = 24       # 24-bit深度

# 从原有文件导入所有函数，保持100%兼容性
def resample_audio(audio_data, source_rate, target_rate):
    """高质量音频重采样 - 支持任意采样率转换"""
    if source_rate == target_rate:
        return audio_data
    
    # 方法1: 使用scipy的高质量重采样（推荐）
    try:
        import scipy.signal
        target_length = int(len(audio_data) * target_rate / source_rate)
        if target_length > 0:
            resampled = scipy.signal.resample(audio_data, target_length, axis=0)
            return resampled.astype(np.float32)
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️ scipy重采样失败: {e}")
    
    # 方法2: 使用librosa的高质量重采样
    try:
        import librosa
        if len(audio_data.shape) > 1:
            # 多声道处理
            resampled = np.array([
                librosa.resample(audio_data[:, i], orig_sr=source_rate, target_sr=target_rate)
                for i in range(audio_data.shape[1])
            ]).T
        else:
            # 单声道处理
            resampled = librosa.resample(audio_data.flatten(), orig_sr=source_rate, target_sr=target_rate)
            resampled = resampled.reshape(-1, 1)
        
        return resampled.astype(np.float32)
        
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️ librosa重采样失败: {e}")
    
    # 方法3: 使用numpy线性插值（备用方案）
    try:
        target_length = int(len(audio_data) * target_rate / source_rate)
        
        if target_length <= 0:
            return audio_data
        
        # 为每个声道进行插值
        if len(audio_data.shape) > 1 and audio_data.shape[1] > 1:
            # 多声道
            resampled_channels = []
            for ch in range(audio_data.shape[1]):
                original_indices = np.arange(len(audio_data))
                target_indices = np.linspace(0, len(audio_data) - 1, target_length)
                resampled_ch = np.interp(target_indices, original_indices, audio_data[:, ch])
                resampled_channels.append(resampled_ch)
            resampled = np.column_stack(resampled_channels)
        else:
            # 单声道
            original_indices = np.arange(len(audio_data))
            target_indices = np.linspace(0, len(audio_data) - 1, target_length)
            resampled = np.interp(target_indices, original_indices, audio_data.flatten())
            resampled = resampled.reshape(-1, 1)
        
        return resampled.astype(np.float32)
        
    except Exception as e:
        print(f"   ❌ numpy重采样失败: {e}")
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

# 继承原有的所有设备检测和管理函数
def detect_device_optimal_channels(device_index):
    """检测设备的最佳声道配置"""
    try:
        device_info = sd.query_devices(device_index)
        max_channels = device_info['max_input_channels']
        device_name_lower = device_info['name'].lower()
        
        if max_channels == 0:
            return None
        
        system_keywords = [
            "stereo mix", "立体声混音", "what u hear", "您听到的声音",
            "loopback", "wave out mix", "混音", "speaker", "扬声器"
        ]
        
        is_system_device = any(keyword in device_name_lower for keyword in system_keywords)
        
        if is_system_device and max_channels >= 2:
            return 2
        else:
            return min(1, max_channels)
            
    except Exception as e:
        print(f"❌ 声道检测异常: {e}")
        return None

def is_recordable_device(device_index):
    """检查设备是否可以录制音频或捕获系统音频"""
    try:
        device_info = sd.query_devices(device_index)
        max_channels = device_info['max_input_channels']
        device_name_lower = device_info['name'].lower()
        
        system_audio_keywords = [
            "stereo mix", "立体声混音", "what u hear", "您听到的声音",
            "loopback", "wave out mix", "混音", "录制混音"
        ]
        
        is_system_audio = any(keyword in device_name_lower for keyword in system_audio_keywords)
        
        if is_system_audio:
            return True
        
        if max_channels == 0:
            return False
        
        pure_output_keywords = [
            "headphone", "耳机", "speakers (", "扬声器 (", 
            "hdmi", "displayport", "bluetooth", "蓝牙音箱"
        ]
        
        is_pure_output = any(keyword in device_name_lower for keyword in pure_output_keywords)
        if is_pure_output:
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 检查设备[{device_index}]时出错: {e}")
        return False

def find_supported_samplerate(device_index, preferred_rate=16000):
    """查找设备支持的采样率，自动检测最佳声道配置"""
    try:
        device_info = sd.query_devices(device_index)
        max_channels = device_info['max_input_channels']
        default_rate = int(device_info['default_samplerate'])
        device_name_lower = device_info['name'].lower()
        
        system_audio_keywords = [
            "stereo mix", "立体声混音", "what u hear", "您听到的声音",
            "loopback", "wave out mix", "混音", "录制混音"
        ]
        is_system_audio = any(keyword in device_name_lower for keyword in system_audio_keywords)
        
        if is_system_audio:
            return default_rate
            
    except Exception as e:
        max_channels = 2
        default_rate = 44100
    
    test_rates = [
        default_rate, preferred_rate, 44100, 48000,
        22050, 32000, 8000, 11025, 96000, 88200, 24000, 16000
    ]
    
    seen = set()
    unique_rates = []
    for rate in test_rates:
        if rate not in seen:
            seen.add(rate)
            unique_rates.append(rate)
    test_rates = unique_rates
    
    possible_channels = [1, 2]
    
    for rate in test_rates:
        for channels in possible_channels:
            if channels > max_channels:
                continue
                
            try:
                sd.check_input_settings(
                    device=device_index, 
                    samplerate=rate, 
                    channels=channels
                )
                return rate
            except Exception:
                continue
    
    try:
        device_info = sd.query_devices(device_index)
        final_rate = int(device_info['default_samplerate'])
        return final_rate
    except Exception:
        return 44100

def list_audio_devices():
    devices = sd.query_devices()
    device_list = []
    seen_names = set()
    print("\n可用音频设备列表：")
    exclude_keywords = [
        "映射器", "mapper", "主声音捕获", "主声音", "主音频", "主驱动", "driver",
        "input ()", "声音捕获驱动程序"
    ]
    
    loopback_keywords = [
        "loopback", "stereo mix", "立体声混音", "what u hear", "您听到的声音",
        "wave out mix", "混音", "录制混音", "speaker", "扬声器", "monitor"
    ]
    
    for i, dev in enumerate(devices):
        if not is_recordable_device(i):
            continue
            
        has_input = dev['max_input_channels'] > 0
        is_loopback = any(k in dev['name'].lower() for k in loopback_keywords)
        
        if has_input or is_loopback:
            name = dev['name'].strip()
            name_lower = name.lower()
            if any(k in name_lower for k in exclude_keywords) or name == "":
                continue
            if name in seen_names:
                continue
            seen_names.add(name)
            try:
                if is_loopback:
                    supported_rate = find_supported_samplerate(i, SAMPLE_RATE)
                    if supported_rate:
                        print(f"✅ Loopback设备[{i}] {name} 支持采样率: {supported_rate}Hz")
                    else:
                        print(f"⚠️ Loopback设备[{i}] {name} 采样率检测失败，但仍保留")
                else:
                    sd.check_input_settings(device=i, samplerate=SAMPLE_RATE, channels=CHANNELS)
            except Exception:
                if not is_loopback:
                    continue
            
            device_type = "🎤 输入" if has_input and not is_loopback else "🔊 系统输出"
            print(f"  [{i}] {name} ({device_type})")
            device_list.append({"index": i, "name": name, "type": device_type})
    return devices, device_list

def auto_select_audio_device():
    """智能音频设备选择 - 保持与原始版本一致的选择逻辑"""
    devices, device_list = list_audio_devices()
    
    # 系统音频设备关键词（优先选择，适合录制系统输出）
    system_keywords = [
        "loopback", "stereo mix", "立体声混音", "what u hear", "您听到的声音",
        "wave out mix", "混音", "录制混音", "speaker", "扬声器", "monitor"
    ]
    
    # 第一优先级：寻找系统音频设备（与原始版本保持一致）
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        if any(k in name for k in system_keywords):
            if is_recordable_device(i):
                supported_rate = find_supported_samplerate(i, SAMPLE_RATE)
                if supported_rate:
                    print(f"\n自动选用推荐设备: [{i}]，采样率: {supported_rate}Hz")
                    return i
    
    # 第二优先级：使用第一个可用的录音设备
    if device_list:
        for device in device_list:
            if is_recordable_device(device['index']):
                try:
                    supported_rate = find_supported_samplerate(device['index'], SAMPLE_RATE)
                    if supported_rate:
                        print(f"\n自动选用第一个可用设备: [{device['index']}] {device['name']}，采样率: {supported_rate}Hz")
                        return device['index']
                except Exception as e:
                    continue
    
    print("❌ 未检测到可用音频输入设备！")
    sys.exit(1)

class HighQualityRecorder:
    """高质量录音器 - 新增功能"""
    def __init__(self, output_dir="recordings"):
        self.recording = False
        self.audio_data = []
        self.start_time = None
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    def start_recording(self):
        if self.recording:
            return
        self.recording = True
        self.audio_data = []
        self.start_time = datetime.now()
        print(f"🔴 开始高质量录音: {RECORD_SAMPLE_RATE}Hz, {RECORD_CHANNELS}声道")
        
    def stop_recording(self):
        if not self.recording:
            return None
        
        self.recording = False
        
        if not self.audio_data:
            print("⚠️ 没有录音数据")
            return None
        
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"hq_recording_{timestamp}.wav"
        
        # 合并音频数据
        audio_array = np.concatenate(self.audio_data, axis=0)
        
        try:
            # 保存为24位WAV文件
            audio_int24 = (audio_array * (2**23 - 1)).astype(np.int32)
            
            with wave.open(str(filename), 'wb') as wav_file:
                wav_file.setnchannels(RECORD_CHANNELS)
                wav_file.setsampwidth(3)  # 24-bit = 3 bytes
                wav_file.setframerate(RECORD_SAMPLE_RATE)
                
                # 转换为24位字节
                audio_bytes = b''
                for sample in audio_int24.flatten():
                    sample_bytes = sample.to_bytes(4, byteorder='little', signed=True)[:3]
                    audio_bytes += sample_bytes
                
                wav_file.writeframes(audio_bytes)
            
            duration = len(audio_array) / RECORD_SAMPLE_RATE
            file_size = filename.stat().st_size / (1024*1024)
            print(f"✅ 高质量录音已保存: {filename}")
            print(f"   时长: {duration:.1f}秒, 文件大小: {file_size:.1f}MB")
            print(f"   格式: {RECORD_CHANNELS}声道, {RECORD_BIT_DEPTH}位, {RECORD_SAMPLE_RATE}Hz")
            return str(filename)
            
        except Exception as e:
            print(f"❌ 保存录音失败: {e}")
            return None
    
    def add_audio_data(self, audio_data):
        if self.recording:
            self.audio_data.append(audio_data.copy())

class DualStreamAudioStreamer:
    """双流音频采集器 - 基于原有架构的完全兼容增强版本"""
    
    def __init__(self, device_index, output_dir="recordings"):
        # 完全保持原有架构的所有变量和初始化
        self.device_index = device_index
        self.output_dir = output_dir
        self.ws = None
        self.running = True
        self.audio_queue = None
        self.loop = None
        self.input_stream = None
        self.switch_device_event = asyncio.Event()
        self.new_device_index = device_index
        self.device_list = []
        self.ws_connected = False
        self.current_samplerate = SAMPLE_RATE
        self.target_samplerate = SAMPLE_RATE
        self.device_channels = 1
        
        # 原有的录音相关功能（保持兼容）
        self.recording = False
        self.recording_paused = False
        self.record_data = []
        self.record_file = None
        self.record_start_time = None
        self.record_pause_start_time = None
        self.record_total_paused_time = 0
        self.record_audio_duration = 0
        self.record_samplerate = SAMPLE_RATE  # 原有录音使用16kHz
        self.record_channels = CHANNELS
        
        # 新增：高质量录音器（双流的第二个流）
        self.hq_recorder = HighQualityRecorder(output_dir)
        
        Path(self.output_dir).mkdir(exist_ok=True)
        
        print(f"🎵 双流音频采集器初始化")
        print(f"   📡 主流(ASR): {SAMPLE_RATE}Hz单声道 → 实时字幕识别")
        print(f"   🔴 高质量流: {RECORD_SAMPLE_RATE}Hz立体声 → 高品质录音")
        print(f"   🔄 完全兼容原有架构的所有功能")

    def audio_callback(self, indata, frames, time_info, status):
        """音频回调函数 - 双流处理，完全兼容原有功能"""
        if status:
            print("⚠️ 音频状态警告:", status)
        
        try:
            # 🎯 主流处理：完全保持原有逻辑，确保实时字幕功能
            max_amplitude = np.max(np.abs(indata))
            
            # 原有录音功能：16kHz标准录音（保持兼容）
            if self.recording and not self.recording_paused:
                self.record_data.append(indata.copy())
                chunk_duration = len(indata) / self.current_samplerate
                self.record_audio_duration += chunk_duration
            
            # ASR处理：转换为单声道并重采样到16kHz
            audio_mono = convert_to_mono(indata)
            
            if self.current_samplerate != self.target_samplerate:
                audio_resampled = resample_audio(audio_mono, self.current_samplerate, self.target_samplerate)
            else:
                audio_resampled = audio_mono
            
            # 转换为int16 PCM格式
            audio_normalized = np.clip(audio_resampled, -1.0, 1.0)
            pcm_int16 = (audio_normalized * 32767).astype(np.int16)
            pcm_bytes = pcm_int16.tobytes()
            
            # 发送到ASR队列
            try:
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pcm_bytes)
            except RuntimeError as e:
                print(f"❌ 无法放入音频数据队列: {e}")
            
            # 🆕 高质量流处理：新增的双流功能
            if self.hq_recorder.recording:
                # 确保立体声格式
                if len(indata.shape) == 1:
                    stereo_data = np.column_stack([indata, indata])
                elif indata.shape[1] == 1:
                    stereo_data = np.column_stack([indata.flatten(), indata.flatten()])
                elif indata.shape[1] >= 2:
                    stereo_data = indata[:, :2]
                else:
                    stereo_data = indata
                
                # 重采样到高质量采样率
                if self.current_samplerate != RECORD_SAMPLE_RATE:
                    hq_audio = resample_audio(stereo_data, self.current_samplerate, RECORD_SAMPLE_RATE)
                else:
                    hq_audio = stereo_data
                
                # 添加到高质量录音器
                self.hq_recorder.add_audio_data(hq_audio)
                
        except Exception as e:
            print(f"❌ 音频处理异常: {e}")
            import traceback
            traceback.print_exc()

    # 完全保持原有的所有方法，确保100%兼容性
    def _find_alternative_device(self):
        """查找替代的可用音频设备"""
        try:
            devices, device_list = list_audio_devices()
            for device in device_list:
                if device['index'] != self.device_index:
                    try:
                        supported_rate = find_supported_samplerate(device['index'], SAMPLE_RATE)
                        if supported_rate:
                            return device['index']
                    except Exception:
                        continue
            return None
        except Exception:
            return None

    def get_current_audio_duration(self):
        """获取当前录音的精确音频时长（秒）"""
        return self.record_audio_duration if self.recording else 0
    
    def start_recording(self, filename=None):
        """开始录音 - 同时启动两个流"""
        if self.recording:
            return False, "已在录音中"
        
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"recording_{timestamp}.wav"
            
            # 启动原有16kHz录音（保持兼容）
            self.record_file = os.path.join(self.output_dir, filename)
            self.record_data = []
            self.record_start_time = time.time()
            self.record_audio_duration = 0
            self.record_total_paused_time = 0
            self.record_pause_start_time = None
            self.recording_paused = False
            self.recording = True
            
            # 🆕 同时启动高质量录音
            self.hq_recorder.start_recording()
            
            print(f"🔴 双流录音已开始:")
            print(f"   📡 标准流: {filename} ({SAMPLE_RATE}Hz)")
            print(f"   🔴 高质量流: 高品质录音 ({RECORD_SAMPLE_RATE}Hz)")
            return True, f"双流录音开始: {filename}"
            
        except Exception as e:
            print(f"❌ 开始录音失败: {e}")
            return False, str(e)

    def stop_recording(self):
        """停止录音 - 保存两个流的文件"""
        if not self.recording:
            return False, "当前未在录音"
        
        try:
            self.recording = False
            self.recording_paused = False
            
            # 停止原有16kHz录音
            result_data = {"files": []}
            
            if self.record_data:
                # 保存标准质量文件
                audio_data = np.concatenate(self.record_data, axis=0)
                
                with wave.open(self.record_file, 'wb') as wf:
                    wf.setnchannels(self.device_channels)
                    wf.setsampwidth(2)
                    wf.setframerate(self.current_samplerate)
                    
                    audio_normalized = np.clip(audio_data, -1.0, 1.0)
                    audio_int16 = (audio_normalized * 32767).astype(np.int16)
                    wf.writeframes(audio_int16.tobytes())
                
                result_data["files"].append({
                    "type": "standard",
                    "filename": os.path.basename(self.record_file),
                    "filepath": self.record_file,
                    "samplerate": self.current_samplerate,
                    "channels": self.device_channels
                })
            
            # 🆕 停止高质量录音
            hq_filename = self.hq_recorder.stop_recording()
            if hq_filename:
                result_data["files"].append({
                    "type": "high_quality", 
                    "filename": os.path.basename(hq_filename),
                    "filepath": hq_filename,
                    "samplerate": RECORD_SAMPLE_RATE,
                    "channels": RECORD_CHANNELS
                })
            
            duration = time.time() - self.record_start_time
            effective_duration = self.record_audio_duration
            
            print(f"✅ 双流录音完成:")
            print(f"   📡 标准文件: {self.record_file}")
            if hq_filename:
                print(f"   🔴 高质量文件: {hq_filename}")
            print(f"   ⏱️ 录音时长: {duration:.1f}秒")
            
            return True, {
                "filename": os.path.basename(self.record_file),
                "filepath": self.record_file,
                "duration": duration,
                "effective_duration": effective_duration,
                "audio_duration": self.record_audio_duration,
                "dual_stream_files": result_data["files"]
            }
            
        except Exception as e:
            self.recording = False
            print(f"❌ 停止录音失败: {e}")
            return False, str(e)

    # 保持原有的所有WebSocket通信方法
    async def send_audio(self):
        print("🚀 send_audio() 协程启动 ✅")
        try:
            while self.running:
                if not self.ws or self.ws.state != websockets.protocol.State.OPEN:
                    await asyncio.sleep(0.2)
                    continue
                try:
                    pcm_data = await self.audio_queue.get()
                    await self.ws.send(pcm_data)
                except websockets.ConnectionClosed:
                    print("❌ WebSocket 连接关闭")
                    self.ws_connected = False
                    raise RuntimeError("WebSocket closed in send_audio")
                except Exception as e:
                    print(f"⚠️ 发送音频异常: {e}")
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            print("发送任务已取消")
        except Exception as e:
            print("发送音频异常:", e)

    async def send_device_list(self):
        """主动推送设备列表给前端"""
        if self.ws:
            try:
                _, device_list = list_audio_devices()
                self.device_list = device_list
                msg = json.dumps({"device_list": device_list})
                await self.ws.send(msg)
                print(f"📤 已推送设备列表")
            except Exception as e:
                print(f"❌ 推送设备列表失败: {e}")

    async def recv_msgs(self):
        print("📡 recv_msgs() 协程启动")
        try:
            async for message in self.ws:
                try:
                    if message.startswith('{'):
                        data = json.loads(message)
                        if 'switch_device' in data:
                            idx = int(data['switch_device'])
                            print(f"🔄 收到切换音频设备指令，切换到设备: {idx}")
                            self.new_device_index = idx
                            self.switch_device_event.set()
                            continue
                        if 'get_device_list' in data:
                            await self.send_device_list()
                            continue
                        # 录音控制命令
                        if 'start_recording' in data:
                            filename = data.get('filename')
                            success, result = self.start_recording(filename)
                            if success:
                                response = {
                                    "recording_started": True,
                                    "data": result,
                                    "start_time": self.record_start_time
                                }
                            else:
                                response = {
                                    "type": "error",
                                    "data": result
                                }
                            await self.ws.send(json.dumps(response))
                            continue
                        if 'stop_recording' in data:
                            success, result = self.stop_recording()
                            if success:
                                response = {
                                    "recording_completed": True,
                                    "data": result
                                }
                            else:
                                response = {
                                    "type": "error", 
                                    "data": result
                                }
                            await self.ws.send(json.dumps(response))
                            continue
                        if 'text' in data:
                            print("💬 实时识别:", data['text'])
                except Exception:
                    print("⚠️ 解析服务器消息失败:", message)
        except websockets.ConnectionClosed:
            print("❌ WebSocket 连接关闭")
            self.ws_connected = False
            raise RuntimeError("WebSocket closed in recv_msgs")
        except Exception as e:
            print("接收消息异常:", e)

    async def run(self, ws_url):
        """运行双流音频采集器 - 完全兼容原有架构"""
        print("🧪 双流音频采集器启动")
        self.loop = asyncio.get_running_loop()
        self.audio_queue = asyncio.Queue()

        while self.running:
            try:
                print(f"🔗 尝试连接 WebSocket：{ws_url}")
                try:
                    async with websockets.connect(ws_url) as websocket:
                        self.ws = websocket
                        self.ws_connected = True
                        print("✅ WebSocket 已连接")
                        await self.send_device_list()

                        recv_task = asyncio.create_task(self.recv_msgs())
                        send_task = asyncio.create_task(self.send_audio())

                        while self.running and self.ws_connected:
                            self.switch_device_event.clear()
                            try:
                                # 设备验证（保持原有逻辑）
                                self.device_channels = detect_device_optimal_channels(self.device_index)
                                
                                if self.device_channels is None:
                                    raise Exception("设备无输入通道，无法录制音频")
                                
                                supported_rate = find_supported_samplerate(self.device_index, SAMPLE_RATE)
                                
                                if supported_rate:
                                    self.current_samplerate = supported_rate
                                    print(f"✅ 设备[{self.device_index}]验证通过")
                                    print(f"   采样率: {supported_rate}Hz")
                                    print(f"   声道数: {self.device_channels}")
                                else:
                                    # 设备失败处理
                                    new_device = self._find_alternative_device()
                                    if new_device is not None:
                                        self.device_index = new_device
                                        supported_rate = find_supported_samplerate(self.device_index, SAMPLE_RATE)
                                        self.current_samplerate = supported_rate or SAMPLE_RATE
                                    else:
                                        print("❌ 没有可用的音频设备，等待5秒后重试")
                                        await asyncio.sleep(5)
                                        continue
                                
                                # 音频流启动
                                actual_chunk_size = int(self.current_samplerate * CHUNK_DURATION)
                                
                                print(f"🔧 双流音频配置:")
                                print(f"   设备采样率: {self.current_samplerate}Hz")
                                print(f"   ASR目标采样率: {self.target_samplerate}Hz")
                                print(f"   高质量目标采样率: {RECORD_SAMPLE_RATE}Hz")
                                print(f"   设备声道数: {self.device_channels}")
                                print(f"   块大小: {actual_chunk_size} samples ({CHUNK_DURATION}s)")
                                
                                with sd.InputStream(
                                    samplerate=self.current_samplerate,
                                    channels=self.device_channels,
                                    dtype='float32',
                                    blocksize=actual_chunk_size,
                                    callback=self.audio_callback,
                                    device=self.device_index):

                                    print("🚀 双流音频采集已启动")
                                    print("   📡 主流: 实时字幕识别 (16kHz)")
                                    print("   🔴 高质量流: 高品质录音 (48kHz)")
                                    print("   ✅ 完全兼容原有功能")
                                    
                                    while self.ws_connected and not self.switch_device_event.is_set():
                                        await asyncio.sleep(0.1)
                                    if not self.ws_connected:
                                        break
                                    if self.switch_device_event.is_set():
                                        print("🔄 触发设备切换事件")
                            except Exception as e:
                                print(f"❗ 音频流异常: {e}")
                                await asyncio.sleep(1)

                            if self.switch_device_event.is_set():
                                print(f"🔄 切换音频输入设备到: {self.new_device_index}")
                                self.device_index = self.new_device_index
                            else:
                                break

                        # 取消任务
                        for task in [recv_task, send_task]:
                            if not task.done():
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    pass
                                except Exception as e:
                                    print(f"❗ 协程取消出错: {e}")

                except Exception as e:
                    print(f"❗ WebSocket 连接或会话异常: {e}")
                print("🔁 等待3秒后尝试重连...")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"❗ run() 外层异常: {e}")
                await asyncio.sleep(3)

    def stop(self):
        self.running = False
        if self.recording:
            self.stop_recording()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="双流音频采集 - 完全兼容增强版")
    parser.add_argument('--uri', type=str, default="ws://127.0.0.1:27000/ws/upload", 
                       help='WebSocket服务器地址')
    parser.add_argument('--output', type=str, default="recordings", 
                       help='录音输出目录')
    args = parser.parse_args()

    print("🎵 双流音频采集服务")
    print("=" * 60)
    print("✅ 完全兼容原有架构 - 保持所有现有功能")
    print("🆕 增加高质量录音流 - 消除16kHz降采样噪音")
    print("📡 主流: 16kHz单声道 → 实时字幕识别")
    print("🔴 高质量流: 48kHz立体声 → 高品质录音")
    print("=" * 60)

    device_index = auto_select_audio_device()
    streamer = DualStreamAudioStreamer(device_index, args.output)

    try:
        asyncio.run(streamer.run(args.uri))
    except KeyboardInterrupt:
        print("\n🚦 退出程序...")
        streamer.stop()
        time.sleep(1)
        print("✅ 程序结束")