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

SAMPLE_RATE = 16000  # 后端固定要求16kHz
CHANNELS = 1         # 后端要求单声道
BIT_DEPTH = 16       # 后端要求16-bit
CHUNK_DURATION = 0.5 # 0.5秒块大小
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)  # 8000 samples

# 录音配置 - 高音质设置
RECORD_SAMPLE_RATE = 44100  # 高质量录音采样率
RECORD_CHANNELS = 2         # 立体声录音
RECORD_BIT_DEPTH = 32       # 32-bit浮点深度

def resample_audio(audio_data, source_rate, target_rate):
    """高质量音频重采样 - 支持任意采样率转换"""
    if source_rate == target_rate:
        return audio_data
    
    print(f"🔄 重采样: {source_rate}Hz → {target_rate}Hz")
    
    # 方法1: 使用scipy的高质量重采样（推荐）
    try:
        import scipy.signal
        target_length = int(len(audio_data) * target_rate / source_rate)
        if target_length > 0:
            resampled = scipy.signal.resample(audio_data, target_length, axis=0)
            print(f"   ✅ scipy重采样: {len(audio_data)} → {len(resampled)} samples")
            return resampled.astype(np.float32)
    except ImportError:
        print("   ⚠️ scipy未安装，使用numpy替代")
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
        
        print(f"   ✅ librosa重采样: {len(audio_data)} → {len(resampled)} samples")
        return resampled.astype(np.float32)
        
    except ImportError:
        print("   ⚠️ librosa未安装，使用numpy插值")
    except Exception as e:
        print(f"   ⚠️ librosa重采样失败: {e}")
    
    # 方法3: 使用numpy线性插值（备用方案）
    try:
        # 计算目标长度
        target_length = int(len(audio_data) * target_rate / source_rate)
        
        if target_length <= 0:
            print("   ❌ 目标长度无效")
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
        
        print(f"   ✅ numpy插值: {len(audio_data)} → {len(resampled)} samples")
        return resampled.astype(np.float32)
        
    except Exception as e:
        print(f"   ❌ numpy重采样失败: {e}")
    
    # 方法4: 简单下采样/上采样（最后手段）
    try:
        ratio = target_rate / source_rate
        
        if ratio < 1:
            # 下采样：每隔几个样本取一个
            step = int(1 / ratio)
            if step > 1:
                resampled = audio_data[::step]
            else:
                resampled = audio_data
        else:
            # 上采样：重复样本
            repeat = int(ratio)
            if repeat > 1:
                resampled = np.repeat(audio_data, repeat, axis=0)
            else:
                resampled = audio_data
        
        print(f"   ⚠️ 简单重采样: {len(audio_data)} → {len(resampled)} samples")
        return resampled.astype(np.float32)
        
    except Exception as e:
        print(f"   ❌ 简单重采样失败: {e}")
        print("   🔥 使用原始数据")
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

def detect_device_optimal_channels(device_index):
    """检测设备的最佳声道配置"""
    try:
        device_info = sd.query_devices(device_index)
        max_channels = device_info['max_input_channels']
        device_name_lower = device_info['name'].lower()
        
        print(f"🔍 设备[{device_index}]声道检测: 最大输入通道={max_channels}")
        
        # 如果设备没有输入通道，这不是一个可录制的设备
        if max_channels == 0:
            print(f"❌ 设备[{device_index}]无输入通道，无法录制")
            return None
        
        # 立体声混音等系统音频设备通常需要立体声输入
        system_keywords = [
            "stereo mix", "立体声混音", "what u hear", "您听到的声音",
            "loopback", "wave out mix", "混音", "speaker", "扬声器"
        ]
        
        is_system_device = any(keyword in device_name_lower for keyword in system_keywords)
        
        if is_system_device and max_channels >= 2:
            # 系统音频设备优先使用立体声
            return 2
        else:
            # 普通输入设备使用单声道，但不能超过设备最大通道数
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
        
        # 系统音频捕获设备关键词（这些设备用于捕获系统输出音频）
        system_audio_keywords = [
            "stereo mix", "立体声混音", "what u hear", "您听到的声音",
            "loopback", "wave out mix", "混音", "录制混音"
        ]
        
        # 检查是否为系统音频捕获设备
        is_system_audio = any(keyword in device_name_lower for keyword in system_audio_keywords)
        
        # 系统音频设备优先：即使输入通道为0也允许（某些驱动报告可能不准确）
        if is_system_audio:
            print(f"✅ 设备[{device_index}] {device_info['name']} 是系统音频捕获设备")
            return True
        
        # 普通录音设备：必须有输入通道
        if max_channels == 0:
            print(f"⚠️ 设备[{device_index}] {device_info['name']} 无输入通道，跳过")
            return False
        
        # 排除明显的纯输出设备（但不包含系统音频关键词的）
        pure_output_keywords = [
            "headphone", "耳机", "speakers (", "扬声器 (", 
            "hdmi", "displayport", "bluetooth", "蓝牙音箱"
        ]
        
        is_pure_output = any(keyword in device_name_lower for keyword in pure_output_keywords)
        if is_pure_output:
            print(f"⚠️ 设备[{device_index}] {device_info['name']} 是纯输出设备，跳过")
            return False
        
        # 其他有输入通道的设备（麦克风等）可录制
        return True
        
    except Exception as e:
        print(f"❌ 检查设备[{device_index}]时出错: {e}")
        return False

def validate_audio_format(audio_data, sample_rate):
    """验证音频格式是否符合后端要求"""
    if sample_rate != SAMPLE_RATE:
        return False, f"采样率不匹配: {sample_rate} != {SAMPLE_RATE}"
    
    if len(audio_data.shape) != 2 or audio_data.shape[1] != 1:
        return False, f"声道数不匹配: shape={audio_data.shape}, 需要单声道"
    
    if audio_data.dtype != np.float32:
        return False, f"数据类型不匹配: {audio_data.dtype} != float32"
    
    return True, "格式正确"

def find_supported_samplerate(device_index, preferred_rate=16000):
    """查找设备支持的采样率，自动检测最佳声道配置"""
    # 获取设备信息
    try:
        device_info = sd.query_devices(device_index)
        max_channels = device_info['max_input_channels']
        default_rate = int(device_info['default_samplerate'])
        device_name_lower = device_info['name'].lower()
        
        print(f"🔍 设备[{device_index}]信息: 最大声道={max_channels}, 默认采样率={default_rate}Hz")
        
        # 检查是否为系统音频设备
        system_audio_keywords = [
            "stereo mix", "立体声混音", "what u hear", "您听到的声音",
            "loopback", "wave out mix", "混音", "录制混音"
        ]
        is_system_audio = any(keyword in device_name_lower for keyword in system_audio_keywords)
        
        # 对于系统音频设备，采用宽松策略
        if is_system_audio:
            print(f"🔊 检测到系统音频设备，使用宽松检测模式")
            # 直接使用设备默认采样率，跳过严格验证
            print(f"✅ 系统音频设备[{device_index}]采用默认配置: {default_rate}Hz")
            return default_rate
            
    except Exception as e:
        print(f"⚠️ 无法获取设备信息: {e}")
        max_channels = 2
        default_rate = 44100
    
    # 扩展的采样率列表，优先使用设备默认采样率
    test_rates = [
        default_rate,    # 设备默认采样率（最高优先级）
        preferred_rate,  # 首选采样率
        44100, 48000,    # 标准音频采样率
        22050, 32000,    # 中等采样率
        8000, 11025,     # 低采样率
        96000, 88200,    # 高质量采样率
        24000, 16000     # 语音采样率
    ]
    
    # 去重，保持顺序
    seen = set()
    unique_rates = []
    for rate in test_rates:
        if rate not in seen:
            seen.add(rate)
            unique_rates.append(rate)
    test_rates = unique_rates
    
    # 可能的声道配置
    possible_channels = [1, 2]
    
    # 逐一测试采样率和声道组合
    for rate in test_rates:
        for channels in possible_channels:
            # 只测试设备支持的声道数
            if channels > max_channels:
                continue
                
            try:
                sd.check_input_settings(
                    device=device_index, 
                    samplerate=rate, 
                    channels=channels
                )
                print(f"✅ 设备[{device_index}]支持: {rate}Hz, {channels}声道")
                return rate
            except Exception as e:
                print(f"❌ 测试失败 {rate}Hz/{channels}ch: {e}")
                continue
    
    print(f"⚠️ 设备[{device_index}]标准检测全部失败，使用默认配置")
    
    # 最后尝试：强制使用设备默认配置（不验证）
    try:
        device_info = sd.query_devices(device_index)
        final_rate = int(device_info['default_samplerate'])
        print(f"🔧 强制使用设备[{device_index}]默认采样率: {final_rate}Hz")
        return final_rate
    except Exception:
        print(f"❌ 无法获取设备[{device_index}]默认采样率，使用备用值")
        return 44100  # 通用备用采样率

def list_audio_devices():
    devices = sd.query_devices()
    device_list = []
    seen_names = set()
    print("\n可用音频设备列表：")
    exclude_keywords = [
        "映射器", "mapper", "主声音捕获", "主声音", "主音频", "主驱动", "driver",
        "input ()", "声音捕获驱动程序"
    ]
    
    # 优先显示系统输出设备的loopback
    loopback_keywords = [
        "loopback", "stereo mix", "立体声混音", "what u hear", "您听到的声音",
        "wave out mix", "混音", "录制混音", "speaker", "扬声器", "monitor"
    ]
    
    for i, dev in enumerate(devices):
        # 首先检查设备是否可录制
        if not is_recordable_device(i):
            continue
            
        # 检查是否有输入通道或者是系统输出loopback设备
        has_input = dev['max_input_channels'] > 0
        is_loopback = any(k in dev['name'].lower() for k in loopback_keywords)
        
        if has_input or is_loopback:
            name = dev['name'].strip()
            name_lower = name.lower()
            if any(k in name_lower for k in exclude_keywords) or name == "":
                continue
            # 去重：只保留第一个同名设备
            if name in seen_names:
                continue
            seen_names.add(name)
            try:
                # 对于loopback设备，可能需要特殊的验证方式
                if is_loopback:
                    # 对于loopback设备，使用动态采样率检测
                    supported_rate = find_supported_samplerate(i, SAMPLE_RATE)
                    if supported_rate:
                        print(f"✅ Loopback设备[{i}] {name} 支持采样率: {supported_rate}Hz")
                    else:
                        print(f"⚠️ Loopback设备[{i}] {name} 采样率检测失败，但仍保留")
                else:
                    # 普通输入设备使用标准验证
                    sd.check_input_settings(device=i, samplerate=SAMPLE_RATE, channels=CHANNELS)
            except Exception:
                if not is_loopback:  # 只对非loopback设备跳过
                    continue
            
            device_type = "🎤 输入" if has_input and not is_loopback else "🔊 系统输出"
            print(f"  [{i}] {name} ({device_type})")
            device_list.append({"index": i, "name": name, "type": device_type})
    return devices, device_list

def find_default_audio_device():
    keywords = [
        "loopback", "stereo mix", "立体声混音", "what u hear", "您听到的声音",
        "wave out mix", "混音", "录制混音", "speaker", "扬声器", "monitor"
    ]
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        # 优先查找系统输出loopback设备
        if any(k in name for k in keywords):
            return i, dev['name']
    # 如果没有找到loopback设备，查找普通输入设备
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            return i, dev['name']
    return None, None

def select_audio_device():
    devices, device_list = list_audio_devices()
    default_idx, default_name = find_default_audio_device()
    if default_idx is not None:
        print(f"\n按回车直接使用推荐设备: [{default_idx}] {default_name}")
    else:
        print("\n未检测到推荐设备，请手动选择。")
    while True:
        try:
            user_input = input("请输入要使用的音频输入设备编号 (回车=默认): ")
            if user_input.strip() == '' and default_idx is not None:
                print(f"✅ 选中默认设备: [{default_idx}] {default_name}")
                return default_idx
            idx = int(user_input)
            # 检查设备是否在可录制设备列表中
            if 0 <= idx < len(devices) and is_recordable_device(idx):
                print(f"✅ 选中设备: [{idx}] {devices[idx]['name']}")
                return idx
            else:
                print("❌ 设备编号无效或设备无法录制，请重新输入。")
        except Exception:
            print("❌ 输入无效，请输入数字编号或直接回车。")

def auto_select_audio_device():
    """自动优选推荐设备，无需终端交互"""
    devices, device_list = list_audio_devices()
    default_idx, _ = find_default_audio_device()
    if default_idx is not None:
        # 验证设备是否真正可用且可录制
        if is_recordable_device(default_idx):
            try:
                supported_rate = find_supported_samplerate(default_idx, SAMPLE_RATE)
                if supported_rate:
                    print(f"\n自动选用推荐设备: [{default_idx}]，采样率: {supported_rate}Hz")
                    return default_idx
                else:
                    print(f"⚠️ 推荐设备[{default_idx}]无可用采样率")
            except Exception as e:
                print(f"⚠️ 推荐设备[{default_idx}]不可用: {e}")
        else:
            print(f"⚠️ 推荐设备[{default_idx}]无法录制音频")
    
    # 没有推荐设备或推荐设备不可用，选第一个可用设备
    if device_list:
        for device in device_list:
            if is_recordable_device(device['index']):
                try:
                    supported_rate = find_supported_samplerate(device['index'], SAMPLE_RATE)
                    if supported_rate:
                        print(f"\n自动选用第一个可用设备: [{device['index']}] {device['name']}，采样率: {supported_rate}Hz")
                        return device['index']
                except Exception as e:
                    print(f"⚠️ 设备[{device['index']}] {device['name']} 不可用: {e}")
                    continue
    
    print("❌ 未检测到可用音频输入设备！")
    sys.exit(1)

class AudioStreamer:
    def __init__(self, device_index, output_dir="recordings"):
        self.device_index = device_index
        self.output_dir = output_dir
        self.ws = None
        self.running = True
        self.audio_queue = None   # 延后初始化
        self.loop = None          # 延后初始化
        self.input_stream = None
        self.switch_device_event = asyncio.Event()
        self.new_device_index = device_index
        self.device_list = []
        self.ws_connected = False  # 新增：WebSocket连接状态
        self.current_samplerate = SAMPLE_RATE  # 当前使用的采样率
        self.target_samplerate = SAMPLE_RATE   # 目标采样率（固定16kHz）
        self.device_channels = 1               # 设备使用的声道数
        
        # 录音相关功能
        self.recording = False
        self.recording_paused = False  # 新增：录音暂停状态
        self.record_data = []
        self.record_file = None
        self.record_start_time = None
        self.record_pause_start_time = None  # 新增：暂停开始时间
        self.record_total_paused_time = 0    # 新增：累计暂停时间
        self.record_audio_duration = 0       # 新增：基于音频数据的累积时长（秒）
        self.record_samplerate = RECORD_SAMPLE_RATE
        self.record_channels = RECORD_CHANNELS
        
        # 创建录音输出目录
        Path(self.output_dir).mkdir(exist_ok=True)

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print("⚠️ 音频状态警告:", status)
        
        try:
            # 调试信息：显示输入音频的基本信息
            max_amplitude = np.max(np.abs(indata))
            print(f"🎤 原始音频: shape={indata.shape}, max_amp={max_amplitude:.4f}", end=" ")
            
            # 检查音频是否为空或静音
            if max_amplitude < 1e-6:  # 几乎静音
                print("⚠️ 检测到静音或空音频")
            
            # 1. 保存原始高质量音频用于录音（只在未暂停时保存）
            if self.recording and not self.recording_paused:
                # 保存所有音频数据，包括静音部分（与ASR保持一致）
                self.record_data.append(indata.copy())
                # 计算累积音频时长（基于实际保存的音频数据）
                chunk_duration = len(indata) / self.current_samplerate
                self.record_audio_duration += chunk_duration
                
                if max_amplitude > 1e-6:
                    print(f"[录音] 保存音频块: {indata.shape}, amp={max_amplitude:.4f}, 累积时长={self.record_audio_duration:.3f}s")
                else:
                    print(f"[录音] 保存静音块: {indata.shape}, amp={max_amplitude:.6f}, 累积时长={self.record_audio_duration:.3f}s")
            elif self.recording and self.recording_paused:
                print(f"[录音] 暂停中，跳过音频块: {len(indata)/self.current_samplerate:.3f}s")
            
            # 2. 处理音频用于ASR实时字幕
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
            
            # 第4步：转换为int16 PCM格式（后端期望的格式）
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

    def _find_alternative_device(self):
        """查找替代的可用音频设备"""
        try:
            devices, device_list = list_audio_devices()
            for device in device_list:
                if device['index'] != self.device_index:  # 跳过当前失效设备
                    try:
                        # 使用动态采样率检测
                        supported_rate = find_supported_samplerate(device['index'], SAMPLE_RATE)
                        if supported_rate:
                            return device['index']
                    except Exception:
                        continue
            return None
        except Exception:
            return None

    def get_current_audio_duration(self):
        """获取当前录音的精确音频时长（秒）- 基于实际保存的音频数据"""
        return self.record_audio_duration if self.recording else 0
    
    def start_recording(self, filename=None):
        """开始录音"""
        if self.recording:
            return False, "已在录音中"
        
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"recording_{timestamp}.wav"
            
            self.record_file = os.path.join(self.output_dir, filename)
            self.record_data = []
            self.record_start_time = time.time()
            self.record_audio_duration = 0  # 重置音频时长计数器
            self.record_total_paused_time = 0  # 重置暂停时间
            self.record_pause_start_time = None
            self.recording_paused = False
            self.recording = True
            
            print(f"🔴 开始录音: {self.record_file}")
            return True, f"开始录音: {filename}"
            
        except Exception as e:
            print(f"❌ 开始录音失败: {e}")
            return False, str(e)

    def pause_recording(self):
        """暂停录音"""
        if not self.recording:
            return False, "当前未在录音"
        
        if self.recording_paused:
            return False, "录音已经暂停"
        
        try:
            self.recording_paused = True
            self.record_pause_start_time = time.time()
            
            print(f"⏸️ 录音已暂停: {self.record_file}")
            print(f"   暂停时间: {time.strftime('%H:%M:%S', time.localtime(self.record_pause_start_time))}")
            
            return True, f"录音已暂停"
            
        except Exception as e:
            print(f"❌ 暂停录音失败: {e}")
            return False, str(e)

    def resume_recording(self):
        """恢复录音"""
        if not self.recording:
            return False, "当前未在录音" 
        
        if not self.recording_paused:
            return False, "录音未暂停"
        
        try:
            # 计算本次暂停时长
            if self.record_pause_start_time:
                pause_duration = time.time() - self.record_pause_start_time
                self.record_total_paused_time += pause_duration
                print(f"▶️ 录音已恢复: {self.record_file}")
                print(f"   本次暂停时长: {pause_duration:.1f}秒")
                print(f"   总暂停时长: {self.record_total_paused_time:.1f}秒")
            
            self.recording_paused = False
            self.record_pause_start_time = None
            
            return True, f"录音已恢复"
            
        except Exception as e:
            print(f"❌ 恢复录音失败: {e}")
            return False, str(e)

    def stop_recording(self):
        """停止录音并保存文件"""
        if not self.recording:
            return False, "当前未在录音"
        
        try:
            # 如果正在暂停中，先计算最后的暂停时间
            if self.recording_paused and self.record_pause_start_time:
                final_pause_duration = time.time() - self.record_pause_start_time
                self.record_total_paused_time += final_pause_duration
                print(f"🔄 结算最后暂停时间: {final_pause_duration:.1f}秒")
            
            self.recording = False
            self.recording_paused = False
            
            if not self.record_data:
                return False, "没有录音数据"
            
            # 合并音频数据
            audio_data = np.concatenate(self.record_data, axis=0)
            
            # 检查合并后的音频数据
            total_amplitude = np.max(np.abs(audio_data))
            average_amplitude = np.mean(np.abs(audio_data))
            print(f"📊 合并音频数据: shape={audio_data.shape}, max_amp={total_amplitude:.6f}, avg_amp={average_amplitude:.6f}")
            
            # 更合理的音频质量检测
            if total_amplitude < 1e-8:  # 放宽检测标准，只有完全无声才警告
                print("⚠️ 警告：录音数据完全无声，可能是音频设备未连接")
                print("⚠️ 继续保存录音文件，请检查音频设备配置")
            elif total_amplitude < 1e-6:
                print("⚠️ 警告：录音数据很小，可能是麦克风音量过低或环境很安静")
                print("⚠️ 继续保存录音文件")
            else:
                print("✅ 录音数据正常")
            
            # 保存为WAV文件
            with wave.open(self.record_file, 'wb') as wf:
                wf.setnchannels(self.device_channels)
                wf.setsampwidth(2)  # 改为16-bit = 2 bytes（更通用的格式）
                wf.setframerate(self.current_samplerate)
                
                # 转换为int16保存（标准格式）
                audio_normalized = np.clip(audio_data, -1.0, 1.0)
                audio_int16 = (audio_normalized * 32767).astype(np.int16)
                wf.writeframes(audio_int16.tobytes())
                
                print(f"💾 WAV文件保存: {self.device_channels}声道, 16-bit, {self.current_samplerate}Hz")
            
            duration = time.time() - self.record_start_time
            # 使用基于音频数据的精确时长，而不是计算的暂停时间
            effective_duration = self.record_audio_duration  # 这就是真实的音频播放时长
            file_size = os.path.getsize(self.record_file) / (1024 * 1024)  # MB
            
            print(f"✅ 录音保存: {self.record_file}")
            print(f"   总录制时长: {duration:.1f}秒")
            print(f"   音频播放时长: {effective_duration:.1f}秒 (基于音频数据)")
            print(f"   暂停时长: {self.record_total_paused_time:.1f}秒 (计算值)")
            print(f"   文件大小: {file_size:.1f}MB")
            
            # 读取保存的音频文件并编码为十六进制字符串，供前端下载
            audio_data_hex = None
            try:
                with open(self.record_file, 'rb') as f:
                    audio_bytes = f.read()
                    audio_data_hex = audio_bytes.hex()
                    print(f"📦 音频数据已编码: {len(audio_bytes)} bytes -> {len(audio_data_hex)} hex chars")
            except Exception as e:
                print(f"❌ 读取音频文件失败: {e}")
            
            return True, {
                "filename": os.path.basename(self.record_file),
                "filepath": self.record_file,
                "duration": duration,  # 总录制时长
                "effective_duration": effective_duration,  # 音频播放时长（精确）
                "audio_duration": self.record_audio_duration,  # 基于音频数据的时长
                "paused_time": self.record_total_paused_time,  # 计算的暂停时长
                "file_size": file_size,
                "audio_data": audio_data_hex,  # 用于前端下载的十六进制数据
                "format": f"{self.device_channels}ch_{self.current_samplerate}Hz_16bit",
                "amplitude": {
                    "max": total_amplitude,
                    "average": average_amplitude
                },
                "quality": "normal" if total_amplitude > 1e-6 else "very_quiet" if total_amplitude > 1e-8 else "silent",
                "data_chunks": len(self.record_data)  # 录音数据块数量
            }
            
        except Exception as e:
            self.recording = False
            print(f"❌ 停止录音失败: {e}")
            return False, str(e)

    async def send_audio(self):
        print("🚀 send_audio() 协程启动 ✅")
        try:
            while self.running:
                if not self.ws or self.ws.state != websockets.protocol.State.OPEN:
                    print("⚠️ send_audio: WebSocket 未连接，等待...")
                    await asyncio.sleep(0.2)
                    continue
                print("⌛ 等待队列音频数据...")
                try:
                    pcm_data = await self.audio_queue.get()
                    print(f"📤 取出音频数据，长度: {len(pcm_data)} bytes")
                    await self.ws.send(pcm_data)
                    print(f"📤 Sent audio chunk: {len(pcm_data)} bytes")
                except websockets.ConnectionClosed:
                    print("❌ send_audio: WebSocket 连接关闭，抛出异常促使主循环重连")
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
                print(f"📤 已推送设备列表: {msg}")
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
                        # 处理录音控制命令
                        if 'start_recording' in data:
                            filename = data.get('filename')
                            success, result = self.start_recording(filename)
                            if success:
                                response = {
                                    "recording_started": True,
                                    "data": result,
                                    "start_time": self.record_start_time  # 使用Python录音开始时间
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
                        # 处理录音暂停命令
                        if 'pause_recording' in data:
                            success, result = self.pause_recording()
                            if success:
                                response = {
                                    "recording_paused": True,
                                    "data": result
                                }
                            else:
                                response = {
                                    "type": "error",
                                    "data": result
                                }
                            await self.ws.send(json.dumps(response))
                            continue
                        # 处理录音恢复命令
                        if 'resume_recording' in data:
                            success, result = self.resume_recording()
                            if success:
                                response = {
                                    "recording_resumed": True,
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
            print("❌ recv_msgs: WebSocket 连接关闭，抛出异常促使主循环重连")
            self.ws_connected = False
            raise RuntimeError("WebSocket closed in recv_msgs")
        except Exception as e:
            print("接收消息异常:", e)

    async def run(self, ws_url):
        print("🧪 AudioStreamer.run() 已启动")
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
                                # 在启动音频流前验证设备可用性
                                try:
                                    # 首先检测设备的最佳配置
                                    self.device_channels = detect_device_optimal_channels(self.device_index)
                                    
                                    # 如果设备无法录制（0输入通道），跳过此设备
                                    if self.device_channels is None:
                                        raise Exception("设备无输入通道，无法录制音频")
                                    
                                    supported_rate = find_supported_samplerate(self.device_index, SAMPLE_RATE)
                                    
                                    if supported_rate:
                                        self.current_samplerate = supported_rate
                                        print(f"✅ 设备[{self.device_index}]验证通过")
                                        print(f"   采样率: {supported_rate}Hz")
                                        print(f"   声道数: {self.device_channels}")
                                    else:
                                        # 如果标准验证失败，尝试宽松模式
                                        print(f"⚠️ 设备[{self.device_index}]标准验证失败，尝试宽松模式")
                                        device_info = sd.query_devices(self.device_index)
                                        
                                        # 再次检查输入通道
                                        if device_info['max_input_channels'] == 0:
                                            raise Exception("设备确实无输入通道")
                                        
                                        self.current_samplerate = int(device_info['default_samplerate'])
                                        self.device_channels = min(device_info['max_input_channels'], 2)
                                        print(f"   使用设备默认配置: {self.current_samplerate}Hz, {self.device_channels}声道")
                                        
                                except Exception as e:
                                    print(f"❌ 设备[{self.device_index}]验证失败: {e}")
                                    # 尝试重新选择可用设备
                                    new_device = self._find_alternative_device()
                                    if new_device is not None:
                                        print(f"🔄 切换到替代设备: [{new_device}]")
                                        self.device_index = new_device
                                        # 重新检测新设备的采样率
                                        supported_rate = find_supported_samplerate(self.device_index, SAMPLE_RATE)
                                        self.current_samplerate = supported_rate or SAMPLE_RATE
                                    else:
                                        print("❌ 没有可用的音频设备，等待5秒后重试")
                                        await asyncio.sleep(5)
                                        continue
                                
                                # 计算正确的块大小
                                # 后端期望: 300ms块，16kHz = 4800 samples
                                # 我们使用500ms块，16kHz = 8000 samples
                                actual_chunk_size = int(self.current_samplerate * CHUNK_DURATION)
                                
                                print(f"🔧 音频流配置:")
                                print(f"   设备采样率: {self.current_samplerate}Hz")
                                print(f"   目标采样率: {self.target_samplerate}Hz") 
                                print(f"   设备声道数: {self.device_channels}")
                                print(f"   块大小: {actual_chunk_size} samples ({CHUNK_DURATION}s)")
                                
                                with sd.InputStream(
                                    samplerate=self.current_samplerate,
                                    channels=self.device_channels,  # 使用动态声道数
                                    dtype='float32',
                                    blocksize=actual_chunk_size,
                                    callback=self.audio_callback,
                                    device=self.device_index):

                                    print("🚀 成功进入 sd.InputStream block ✅")
                                    while self.ws_connected and not self.switch_device_event.is_set():
                                        await asyncio.sleep(0.1)
                                    if not self.ws_connected:
                                        print("🛑 WebSocket 断开，立即退出音频采集流")
                                        break
                                    if self.switch_device_event.is_set():
                                        print("🔄 触发设备切换事件，准备重启音频流")
                            except Exception as e:
                                print(f"❗ 音频流异常: {e}")
                                await asyncio.sleep(1)

                            if self.switch_device_event.is_set():
                                print(f"🔄 切换音频输入设备到: {self.new_device_index}")
                                self.device_index = self.new_device_index
                            else:
                                break

                        # ⭐ 主动取消任务，确保能重连
                        for task in [recv_task, send_task]:
                            if not task.done():
                                task.cancel()
                                try:
                                    await task
                                except asyncio.CancelledError:
                                    print("✅ 协程取消成功")
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="音频采集和WebSocket流传输，集成高音质录音功能")
    parser.add_argument('--uri', type=str, default="ws://127.0.0.1:27000/ws/upload", help='WebSocket服务器地址')
    parser.add_argument('--output', type=str, default="recordings", help='录音输出目录')
    args = parser.parse_args()

    device_index = auto_select_audio_device()
    streamer = AudioStreamer(device_index, args.output)

    print(f"\n✅ 音频服务配置完成")
    print(f"   ASR设备: [{device_index}]")
    print(f"   录音输出目录: {args.output}")
    print(f"   功能: 实时字幕 + 高音质录音")

    try:
        asyncio.run(streamer.run(args.uri))
    except KeyboardInterrupt:
        print("\n🚦 退出程序，停止采集...")
        streamer.stop()
        if streamer.recording:
            streamer.stop_recording()
        time.sleep(1)
        print("✅ 程序结束。")
