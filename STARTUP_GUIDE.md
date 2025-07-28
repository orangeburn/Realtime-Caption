# 实时字幕系统启动指南（Windows）

## 启动脚本功能

已创建 `start.py` 启动脚本，专为Windows环境设计，实现以下功能：

### 启动顺序
1. **第一阶段：后端和前端同步启动**
   - 后端：启动 FastAPI 服务器 (端口 8000)
   - 前端：启动 Electron 应用

2. **第二阶段：音频采集模块启动**
   - 等待后端完全启动后
   - 启动音频采集 WebSocket 客户端

### 前端启动日志显示

前端已添加启动日志界面，会在显示字幕前显示：
- 系统初始化日志
- 后端服务状态检查
- 前端加载状态
- 音频采集模块状态
- 各模块启动进度

### 使用方法

#### 方法1：使用启动脚本（推荐）
```cmd
python start.py
```

#### 方法2：手动分步启动

1. **启动后端（在 a4s 目录）**
```cmd
cd a4s
# 激活虚拟环境
torch-env\Scripts\activate
# 启动后端
python -m uvicorn server_wss_split:app --host 0.0.0.0 --port 8000 --reload
```

2. **启动前端（在根目录，新命令行窗口）**
```cmd
npm start
```

3. **启动音频采集（等后端启动完成后，新命令行窗口）**
```cmd
# 激活虚拟环境
torch-env\Scripts\activate
python python/audio_capture_websocket.py
```

### Windows环境特性

- ✅ 自动检测Windows虚拟环境（torch-env, venv, .venv）
- ✅ 使用Windows路径格式（Scripts/python.exe）
- ✅ 实时启动日志显示
- ✅ 健康检查端点 (/health)
- ✅ 优雅的进程管理和清理
- ✅ Ctrl+C 安全退出

### 前端启动日志界面

前端会先显示启动日志界面，包含：
- 🚀 系统启动标题
- 📋 实时日志输出（不同颜色区分模块）
  - 绿色：后端日志
  - 蓝色：前端日志
  - 橙色：音频采集日志
  - 白色：系统日志
- ⏳ 启动进度显示
- ✅ 完成后自动切换到字幕界面

### 故障排除

1. **虚拟环境未找到**
   - 确保已创建 torch-env 虚拟环境：`python -m venv torch-env`
   - 检查目录结构：`torch-env\Scripts\python.exe` 应该存在

2. **端口占用**
   - 检查端口 8000 和 8765 是否被占用
   - 使用 `netstat -an | findstr :8000` 检查

3. **模块导入错误**
   - 激活虚拟环境：`torch-env\Scripts\activate`
   - 安装依赖：`pip install -r requirements.txt`

4. **前端启动失败**
   - 确保已安装 Node.js 和 npm
   - 运行 `npm install` 安装依赖

### 系统要求

- Windows 10/11
- Python 3.8+
- Node.js 16+
- torch-env 虚拟环境（包含所有Python依赖）

### 快速启动流程

1. 确保虚拟环境已配置
2. 运行启动脚本：`python start.py`
3. 等待前端显示启动日志
4. 系统自动完成所有模块启动
5. 启动完成后自动切换到字幕界面