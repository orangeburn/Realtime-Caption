# device_check.py
import sounddevice as sd

print("🎧 可用音频设备列表：")
for i, dev in enumerate(sd.query_devices()):
    print(f"[{i}] {dev['name']} | 输入通道: {dev['max_input_channels']} | 输出通道: {dev['max_output_channels']}")
