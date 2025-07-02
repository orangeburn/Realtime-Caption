import asyncio
import websockets
import sounddevice as sd
import numpy as np
import json
import sys
import argparse
import time

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 0.5
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)

def list_audio_devices():
    devices = sd.query_devices()
    device_list = []
    seen_names = set()
    print("\n可用音频输入设备列表：")
    exclude_keywords = [
        "映射器", "mapper", "主声音捕获", "主声音", "主音频", "主驱动", "driver",
        "input ()", "声音捕获驱动程序"
    ]
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            name = dev['name'].strip()
            name_lower = name.lower()
            if any(k in name_lower for k in exclude_keywords) or name == "":
                continue
            # 去重：只保留第一个同名设备
            if name in seen_names:
                continue
            seen_names.add(name)
            try:
                sd.check_input_settings(device=i, samplerate=SAMPLE_RATE, channels=CHANNELS)
            except Exception:
                continue
            print(f"  [{i}] {name}")
            device_list.append({"index": i, "name": name})
    return devices, device_list

def find_default_audio_device():
    keywords = ["loopback", "stereo mix", "立体声混音", "主声音捕获"]
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        if dev['max_input_channels'] > 0 and any(k in name for k in keywords):
            return i, dev['name']
    return None, None

def select_audio_device():
    devices = list_audio_devices()
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
            if 0 <= idx < len(devices) and devices[idx]['max_input_channels'] > 0:
                print(f"✅ 选中设备: [{idx}] {devices[idx]['name']}")
                return idx
            else:
                print("❌ 设备编号无效，请重新输入。")
        except Exception:
            print("❌ 输入无效，请输入数字编号或直接回车。")

def auto_select_audio_device():
    """自动优选推荐设备，无需终端交互"""
    _, device_list = list_audio_devices()
    default_idx, _ = find_default_audio_device()
    if default_idx is not None:
        print(f"\n自动选用推荐设备: [{default_idx}]")
        return default_idx
    # 没有推荐设备则选第一个可用
    if device_list:
        print(f"\n无推荐设备，自动选用第一个可用设备: [{device_list[0]['index']}] {device_list[0]['name']}")
        return device_list[0]['index']
    print("❌ 未检测到可用音频输入设备！")
    sys.exit(1)

class AudioStreamer:
    def __init__(self, device_index):
        self.device_index = device_index
        self.ws = None
        self.running = True
        self.audio_queue = None   # 延后初始化
        self.loop = None          # 延后初始化
        self.input_stream = None
        self.switch_device_event = asyncio.Event()
        self.new_device_index = device_index
        self.device_list = []
        self.ws_connected = False  # 新增：WebSocket连接状态

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print("⚠️ 音频状态警告:", status)
        print(f"🎤 捕获到音频数据，shape: {indata.shape}, dtype: {indata.dtype}")
        pcm_data = (indata * 32767).astype(np.int16).tobytes()
        print(f"📦 放入队列数据大小: {len(pcm_data)}")

        try:
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, pcm_data)
        except RuntimeError as e:
            print(f"❌ 无法放入音频数据队列: {e}")

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
                                with sd.InputStream(
                                    samplerate=SAMPLE_RATE,
                                    channels=CHANNELS,
                                    dtype='float32',
                                    blocksize=CHUNK_SIZE,
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
    parser = argparse.ArgumentParser(description="Audio capture and WebSocket streaming.")
    parser.add_argument('--uri', type=str, default="ws://127.0.0.1:27000/ws/upload", help='WebSocket server URI.')
    args = parser.parse_args()

    device_index = auto_select_audio_device()
    streamer = AudioStreamer(device_index)

    try:
        asyncio.run(streamer.run(args.uri))
    except KeyboardInterrupt:
        print("\n🚦 退出程序，停止采集...")
        streamer.stop()
        time.sleep(1)
        print("✅ 程序结束。")
