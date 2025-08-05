#!/usr/bin/env python3
"""
音频服务启动器
选择使用原始单流架构或增强双流架构
"""

import sys
import os
import subprocess
import argparse
sys.path.append(os.path.dirname(__file__))

def show_menu():
    """显示启动菜单"""
    print("\n" + "="*60)
    print("🎵 实时字幕 - 音频服务启动器")
    print("="*60)
    print("请选择音频服务版本:")
    print()
    print("1. 🔄 原始单流架构 (audio_capture_websocket.py)")
    print("   - 稳定可靠的基础版本")
    print("   - 16kHz统一采样率")
    print("   - 适合标准ASR + 基础录音")
    print()
    print("2. 🚀 增强双流架构 (enhanced_dual_audio_service.py)")
    print("   - 新增高质量录音功能") 
    print("   - ASR流: 16kHz + 录音流: 48kHz")
    print("   - 完全兼容原有功能")
    print("   - 消除16kHz降采样噪音")
    print()
    print("3. 🔍 查看音频设备列表")
    print("4. ❌ 退出")
    print("-"*60)

def start_legacy_service():
    """启动原始单流架构服务"""
    print("\n🔄 启动原始单流架构服务...")
    print("✅ 稳定可靠的基础版本")
    print("⚡ 16kHz统一采样率，低延迟")
    print("-"*40)
    
    try:
        script_path = os.path.join(os.path.dirname(__file__), "audio_capture_websocket.py")
        subprocess.run([sys.executable, script_path])
    except KeyboardInterrupt:
        print("\n🚦 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")

def start_enhanced_service():
    """启动增强双流架构服务"""
    print("\n🚀 启动增强双流架构服务...")
    print("🆕 新增高质量录音功能")
    print("📡 ASR流: 16kHz单声道 → 实时字幕识别")
    print("🔴 录音流: 48kHz立体声 → 高品质录音")
    print("✅ 完全兼容原有架构功能")
    print("🎯 消除16kHz降采样噪音")
    print("-"*40)
    
    try:
        script_path = os.path.join(os.path.dirname(__file__), "enhanced_dual_audio_service.py")
        subprocess.run([sys.executable, script_path])
    except KeyboardInterrupt:
        print("\n🚦 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")

def show_audio_devices():
    """显示音频设备列表"""
    print("\n🔍 扫描音频设备...")
    try:
        # 使用增强版服务中的设备列表功能
        from enhanced_dual_audio_service import list_audio_devices
        devices, device_list = list_audio_devices()
        
        print("\n💡 设备选择建议:")
        print("  🎤 麦克风: 用于语音输入、会议记录")
        print("  🔊 立体声混音: 用于捕获系统播放音频")
        print("  📱 USB设备: 通常提供更好的音质")
        print("\n💡 前端控制:")
        print("  - 启动任一服务后，可在前端界面选择具体设备")
        print("  - 支持动态切换音频输入设备")
        
    except Exception as e:
        print(f"❌ 设备扫描失败: {e}")
    
    input("\n按回车键继续...")

def main():
    """主函数"""
    # 支持命令行参数直接启动
    parser = argparse.ArgumentParser(description="音频服务启动器", add_help=False)
    parser.add_argument('--legacy', action='store_true', help='直接启动原始单流架构')
    parser.add_argument('--enhanced', action='store_true', help='直接启动增强双流架构')
    parser.add_argument('--help', '-h', action='store_true', help='显示帮助信息')
    
    try:
        args = parser.parse_args()
        
        if args.help:
            print("音频服务启动器 - 使用说明")
            print("="*40)
            print("python audio_service_launcher.py         # 显示菜单")
            print("python audio_service_launcher.py --legacy   # 直接启动原始版本")
            print("python audio_service_launcher.py --enhanced # 直接启动增强版本")
            return
            
        if args.legacy:
            start_legacy_service()
            return
            
        if args.enhanced:
            start_enhanced_service()
            return
            
    except SystemExit:
        pass
    
    # 交互式菜单
    while True:
        show_menu()
        try:
            choice = input("请选择 (1-4): ").strip()
            
            if choice == "1":
                start_legacy_service()
                
            elif choice == "2":
                start_enhanced_service()
                
            elif choice == "3":
                show_audio_devices()
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

if __name__ == "__main__":
    main()