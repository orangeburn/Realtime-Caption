#!/usr/bin/env python3
"""
后端启动检测脚本
自动检测硬件环境并启动后端服务
"""

import os
import sys
import subprocess
import importlib.util

def check_gpu_availability():
    """检测GPU可用性"""
    print("🔍 检测硬件环境...")
    
    try:
        import torch
        if torch.cuda.is_available():
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0)
            print(f"✅ 检测到GPU: {gpu_name} (共{gpu_count}个设备)")
            return True, gpu_name
        else:
            print("⚠️ 未检测到CUDA GPU")
            return False, None
    except ImportError:
        print("⚠️ PyTorch未安装，无法检测GPU")
        return False, None
    except Exception as e:
        print(f"❌ GPU检测失败: {e}")
        return False, None

def check_dependencies():
    """检查必要的依赖"""
    print("\n📋 检查依赖包...")
    
    required_packages = [
        ("torch", "PyTorch"),
        ("ctranslate2", "CTranslate2"),
        ("sentencepiece", "SentencePiece"),
        ("funasr", "FunASR"),
        ("fastapi", "FastAPI"),
        ("websockets", "WebSockets"),
        ("uvicorn", "Uvicorn"),
        ("loguru", "Loguru")
    ]
    
    missing_packages = []
    
    for package, display_name in required_packages:
        if importlib.util.find_spec(package) is None:
            print(f"❌ {display_name} 未安装")
            missing_packages.append(package)
        else:
            print(f"✅ {display_name} 已安装")
    
    if missing_packages:
        print(f"\n💡 缺少以下依赖包: {', '.join(missing_packages)}")
        print("请运行以下命令安装:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    return True

def estimate_memory_usage(has_gpu):
    """估算内存使用量"""
    print("\n💾 内存需求评估...")
    
    if has_gpu:
        print("🎯 GPU模式:")
        print("  - ASR模型 (GPU): ~2-4GB 显存")
        print("  - VAD模型 (CPU): ~500MB 内存")
        print("  - 翻译模型 (CPU): ~1-2GB 内存")
        print("  - 总计: ~2GB内存 + 2-4GB显存")
    else:
        print("🎯 CPU模式:")
        print("  - ASR模型 (CPU): ~2-4GB 内存")
        print("  - VAD模型 (CPU): ~500MB 内存") 
        print("  - 翻译模型 (CPU): ~1-2GB 内存")
        print("  - 总计: ~4-7GB 内存")
    
    return True

def show_performance_tips(has_gpu):
    """显示性能优化建议"""
    print("\n💡 性能优化建议:")
    
    if has_gpu:
        print("✅ GPU加速已启用，性能最佳")
        print("  - ASR识别: 实时处理，低延迟")
        print("  - 建议: 确保GPU驱动最新")
    else:
        print("⚠️ 仅CPU模式，性能会有所降低")
        print("  - ASR识别: 可能有轻微延迟")
        print("  - 建议: 使用多核CPU，关闭不必要程序")
        print("  - 备选: 考虑使用云GPU服务")

def start_backend_server(port=27000):
    """启动后端服务器"""
    print(f"\n🚀 启动后端服务器 (端口: {port})...")
    
    try:
        # 检查端口是否被占用
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result == 0:
            print(f"⚠️ 端口 {port} 已被占用")
            print("请检查是否已有后端服务在运行")
            return False
        
        # 启动服务器
        script_dir = os.path.dirname(os.path.abspath(__file__))
        server_script = os.path.join(script_dir, "../a4s/server_wss_split.py")
        
        if not os.path.exists(server_script):
            print(f"❌ 找不到服务器脚本: {server_script}")
            return False
        
        print("✅ 启动中...")
        subprocess.run([
            sys.executable, server_script, "--port", str(port)
        ])
        
    except KeyboardInterrupt:
        print("\n🚦 用户中断，正在停止...")
        return True
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False

def main():
    """主函数"""
    print("🎵 实时字幕后端启动检测")
    print("=" * 50)
    
    # 检查GPU
    has_gpu, gpu_name = check_gpu_availability()
    
    # 检查依赖
    if not check_dependencies():
        print("\n❌ 依赖检查失败，请安装缺少的包后重试")
        sys.exit(1)
    
    # 内存评估
    estimate_memory_usage(has_gpu)
    
    # 性能建议
    show_performance_tips(has_gpu)
    
    # 询问是否启动
    print("\n" + "="*50)
    choice = input("是否现在启动后端服务？(y/n): ").lower().strip()
    
    if choice in ['y', 'yes', '是']:
        port = 27000
        port_input = input(f"端口号 (默认 {port}): ").strip()
        if port_input:
            try:
                port = int(port_input)
            except ValueError:
                print("⚠️ 端口号无效，使用默认端口")
        
        success = start_backend_server(port)
        
        if success:
            print("\n✅ 后端服务已停止")
        else:
            print("\n❌ 后端服务启动失败")
            sys.exit(1)
    else:
        print("\n👋 已取消启动")

if __name__ == "__main__":
    main()