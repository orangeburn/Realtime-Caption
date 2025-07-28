#!/usr/bin/env python3
"""
音频采集启动器
提供简单的交互界面来选择音频采集模式
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from unified_audio_capture import UnifiedAudioCapture, AudioCaptureMode
import asyncio

def show_menu():
    """显示主菜单"""
    print("\n" + "="*60)
    print("🎵 实时字幕 - 音频采集系统")
    print("="*60)
    print("选择音频采集模式:")
    print("  1. 🎤 麦克风录音 (捕获语音输入)")
    print("  2. 🔊 系统音频 (捕获播放的音乐/视频)")
    print("  3. 🔧 查看可用设备")
    print("  4. ❌ 退出")
    print("-"*60)

def main():
    """主函数"""
    while True:
        show_menu()
        try:
            choice = input("请选择 (1-4): ").strip()
            
            if choice == "1":
                print("\n🎤 启动麦克风录音模式...")
                print("💡 适用场景: 会议记录、语音输入、口述转文字")
                capturer = UnifiedAudioCapture(mode=AudioCaptureMode.MICROPHONE)
                break
                
            elif choice == "2":
                print("\n🔊 启动系统音频捕获模式...")
                print("💡 适用场景: 视频字幕、音乐识别、游戏音频转文字")
                capturer = UnifiedAudioCapture(mode=AudioCaptureMode.SYSTEM_AUDIO)
                break
                
            elif choice == "3":
                print("\n🔧 扫描可用音频设备...")
                capturer = UnifiedAudioCapture()
                capturer.list_available_devices()
                
                print("\n💡 使用提示:")
                print("  - 麦克风设备: 用于录制您的语音")
                print("  - 系统音频设备: 用于捕获电脑播放的声音")
                print("  - 如果没有系统音频设备，请启用'立体声混音'")
                
                input("\n按回车键继续...")
                continue
                
            elif choice == "4":
                print("👋 再见!")
                sys.exit(0)
                
            else:
                print("❌ 无效选择，请输入 1-4")
                continue
                
        except KeyboardInterrupt:
            print("\n👋 再见!")
            sys.exit(0)
        except Exception as e:
            print(f"❌ 错误: {e}")
            continue
    
    # 启动选定的采集器
    try:
        print("\n🚀 正在启动音频采集...")
        print("💡 按 Ctrl+C 停止采集")
        asyncio.run(capturer.run("ws://127.0.0.1:27000/ws/upload"))
    except KeyboardInterrupt:
        print("\n🚦 正在停止...")
        capturer.stop()
        print("✅ 已停止")
    except Exception as e:
        print(f"❌ 运行错误: {e}")
        print("💡 请检查:")
        print("  1. WebSocket服务器是否运行 (端口 27000)")
        print("  2. 音频设备是否可用")
        print("  3. 系统权限是否足够")

if __name__ == "__main__":
    main()