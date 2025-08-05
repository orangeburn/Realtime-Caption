// main.js
/* Electron 主进程脚本，创建无边框、置顶字幕窗口 */
const { app, BrowserWindow, ipcMain, screen, shell } = require('electron');
const path = require('path');
const fs = require('fs');

let mainWindow;
let originalWindowSize = { width: 800, height: 200 }; // 保存原始窗口尺寸

function createWindow() {
  mainWindow = new BrowserWindow({
    width: originalWindowSize.width,
    height: originalWindowSize.height,
    frame: false,        // 无边框
    alwaysOnTop: false,  // 默认不置顶，由固定按钮控制
    transparent: false,   // 背景透明（配合 index.html rgba）
    resizable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  // mainWindow.webContents.openDevTools(); // 如需调试可启用
}

// 窗口控制IPC处理程序
ipcMain.handle('set-always-on-top', async (event, alwaysOnTop) => {
  if (mainWindow) {
    mainWindow.setAlwaysOnTop(alwaysOnTop);
    console.log('[Window] 窗口置顶设置:', alwaysOnTop);
  }
});

ipcMain.handle('set-window-size', async (event, { width, height }) => {
  if (mainWindow) {
    mainWindow.setSize(width, height);
    console.log('[Window] 窗口尺寸设置:', width, 'x', height);
  }
});

ipcMain.handle('set-window-position', async (event, { x, y }) => {
  if (mainWindow) {
    mainWindow.setPosition(x, y);
    console.log('[Window] 窗口位置设置:', x, ',', y);
  }
});

ipcMain.handle('set-window-bounds', async (event, { x, y, width, height }) => {
  if (mainWindow) {
    mainWindow.setBounds({ x, y, width, height });
    console.log('[Window] 窗口边界设置:', x, ',', y, ',', width, 'x', height);
  }
});

ipcMain.handle('get-screen-size', async (event) => {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize; // 获取工作区尺寸（排除任务栏）
  console.log('[Window] 屏幕工作区尺寸:', width, 'x', height);
  return { width, height };
});

ipcMain.handle('close-app', async (event) => {
  console.log('[Window] 关闭应用程序');
  app.quit();
});

// 文件操作IPC处理程序
ipcMain.handle('open-recording-folder', async (event) => {
  try {
    // 尝试多个可能的录音文件夹路径，优先使用python/recordings
    const possiblePaths = [
      path.join(process.cwd(), 'python', 'recordings'),
      path.join(__dirname, '..', 'python', 'recordings'),
      path.join(process.cwd(), 'a4s', 'recordings'),
      path.join(process.cwd(), 'recordings'),
      path.join(__dirname, '..', 'a4s', 'recordings'),
      path.join(__dirname, '..', 'recordings')
    ];
    
    let recordingFolderPath = null;
    
    // 找到第一个存在的录音文件夹
    for (const folderPath of possiblePaths) {
      if (fs.existsSync(folderPath)) {
        recordingFolderPath = folderPath;
        console.log('[File] 找到录音文件夹:', recordingFolderPath);
        break;
      }
    }
    
    // 如果没有找到现有文件夹，创建默认的python/recordings文件夹
    if (!recordingFolderPath) {
      recordingFolderPath = path.join(process.cwd(), 'python', 'recordings');
      if (!fs.existsSync(recordingFolderPath)) {
        fs.mkdirSync(recordingFolderPath, { recursive: true });
        console.log('[File] 创建录音文件夹:', recordingFolderPath);
      }
    }
    
    // 打开文件夹
    await shell.openPath(recordingFolderPath);
    console.log('[File] 已打开录音文件夹:', recordingFolderPath);
    
    return { success: true, path: recordingFolderPath };
  } catch (error) {
    console.error('[File] 打开录音文件夹失败:', error);
    return { success: false, error: error.message };
  }
});

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
