const { contextBridge, ipcRenderer } = require('electron');
console.log('[preload.js] preload script is running');


let lastSocket = null;
let heartbeatInterval = null;

// 心跳机制：保持WebSocket连接活跃
function startHeartbeat(socket) {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
  }
  
  heartbeatInterval = setInterval(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: 'ping' }));
        console.log('[preload.js] 发送心跳ping');
      } catch (error) {
        console.error('[preload.js] 发送心跳失败:', error);
        clearInterval(heartbeatInterval);
      }
    } else {
      console.warn('[preload.js] 心跳检查：连接不可用，停止心跳');
      clearInterval(heartbeatInterval);
    }
  }, 30000); // 每30秒发送一次心跳
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
    console.log('[preload.js] 心跳已停止');
  }
}

contextBridge.exposeInMainWorld('subtitleAPI', {
  connect: (onMessage, onReady, onError, onClose) => {
    // 先关闭旧连接和心跳
    if (lastSocket && lastSocket instanceof WebSocket && (lastSocket.readyState === WebSocket.CONNECTING || lastSocket.readyState === WebSocket.OPEN)) {
      console.log('[preload.js] Closing old WebSocket connection');
      stopHeartbeat();
      lastSocket.onclose = null;
      lastSocket.onerror = null;
      lastSocket.close();
    }
    
    console.log('[preload.js] Creating new WebSocket connection to ws://127.0.0.1:27000/ws/subscribe');
    const socket = new WebSocket('ws://127.0.0.1:27000/ws/subscribe');

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // 处理心跳响应
        if (data.type === 'pong') {
          console.log('[preload.js] 收到心跳pong响应');
          return;
        }
        
        onMessage(data);
      } catch (e) {
        console.error('[preload.js] JSON parse error:', e);
      }
    };

    socket.onopen = () => {
      console.log('[preload.js] WebSocket connected successfully');
      lastSocket = socket;
      
      // 启动心跳机制
      startHeartbeat(socket);
      
      console.log('[preload.js] lastSocket updated:', {
        type: typeof lastSocket,
        constructor: lastSocket.constructor.name,
        readyState: lastSocket.readyState,
        url: lastSocket.url,
        hasSend: typeof lastSocket.send === 'function'
      });
      if (typeof onReady === 'function') onReady();
    };

    socket.onerror = (err) => {
      console.error('[preload.js] WebSocket error:', err);
      stopHeartbeat();
      if (typeof onError === 'function') onError(err);
    };
    
    socket.onclose = (e) => {
      console.log('[preload.js] WebSocket closed:', e);
      stopHeartbeat();
      
      // 连接关闭时清空lastSocket
      if (lastSocket === socket) {
        lastSocket = null;
      }
      if (typeof onClose === 'function') onClose(e);
    };

    // 临时设置lastSocket为正在连接的socket，但要等onopen确认
    // 这样getCurrentWS能返回正在连接的socket而不是null
    console.log('[preload.js] Socket created, current state:', socket.readyState);
  },

  // 直接返回WebSocket对象，而不是通过contextBridge序列化
  getCurrentWS: () => {
    console.log('[preload.js] getCurrentWS called, returning:', {
      exists: !!lastSocket,
      type: typeof lastSocket,
      constructor: lastSocket?.constructor?.name,
      readyState: lastSocket?.readyState,
      url: lastSocket?.url,
      hasSend: typeof lastSocket?.send === 'function'
    });
    return lastSocket;
  },

  // 封装WebSocket方法，避免直接传递WebSocket对象
  sendMessage: (message) => {
    console.log('[preload.js] 尝试发送消息:', message);
    console.log('[preload.js] 当前socket状态:', {
      exists: !!lastSocket,
      readyState: lastSocket?.readyState,
      readyStateName: lastSocket ? ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'][lastSocket.readyState] : 'NO_SOCKET',
      url: lastSocket?.url
    });
    
    if (lastSocket && lastSocket.readyState === WebSocket.OPEN) {
      try {
        lastSocket.send(message);
        console.log('[preload.js] Message sent successfully:', message);
        return { success: true };
      } catch (error) {
        console.error('[preload.js] Send message failed:', error);
        return { success: false, error: error.message };
      }
    } else if (lastSocket && lastSocket.readyState === WebSocket.CONNECTING) {
      console.warn('[preload.js] Cannot send message: WebSocket still connecting');
      return { success: false, error: 'WebSocket still connecting' };
    } else if (lastSocket && (lastSocket.readyState === WebSocket.CLOSING || lastSocket.readyState === WebSocket.CLOSED)) {
      console.warn('[preload.js] Cannot send message: WebSocket closed or closing');
      return { success: false, error: 'WebSocket closed or closing' };
    } else {
      console.warn('[preload.js] Cannot send message: No WebSocket connection');
      return { success: false, error: 'No WebSocket connection' };
    }
  },

  getWebSocketState: () => {
    const state = {
      connected: lastSocket && lastSocket.readyState === WebSocket.OPEN,
      readyState: lastSocket?.readyState,
      readyStateName: lastSocket ? ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'][lastSocket.readyState] : 'NO_SOCKET',
      url: lastSocket?.url,
      exists: !!lastSocket
    };
    console.log('[preload.js] getWebSocketState called:', state);
    return state;
  },

  setTargetLang: (lang) => {
    if (lastSocket && lastSocket.readyState === WebSocket.OPEN) {
      lastSocket.send(JSON.stringify({ set_target_lang: lang }));
      console.log('[preload.js] Sent set_target_lang:', lang);
    } else {
      console.warn('[preload.js] setTargetLang failed: socket not ready');
    }
  },

  switchDevice: (deviceId) => {
    if (lastSocket && lastSocket.readyState === WebSocket.OPEN) {
      lastSocket.send(JSON.stringify({ switch_device: deviceId }));
      console.log('[preload.js] Sent switch_device:', deviceId);
    } else {
      console.warn('[preload.js] switchDevice failed: socket not ready');
    }
  },

  // 翻译模型控制API
  loadTranslationModel: async () => {
    try {
      const response = await fetch('http://127.0.0.1:27000/translation/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const result = await response.json();
      console.log('[preload.js] Load translation model result:', result);
      return result;
    } catch (error) {
      console.error('[preload.js] Load translation model error:', error);
      return { success: false, message: error.message };
    }
  },

  unloadTranslationModel: async () => {
    try {
      const response = await fetch('http://127.0.0.1:27000/translation/unload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const result = await response.json();
      console.log('[preload.js] Unload translation model result:', result);
      return result;
    } catch (error) {
      console.error('[preload.js] Unload translation model error:', error);
      return { success: false, message: error.message };
    }
  },

  getTranslationStatus: async () => {
    try {
      const response = await fetch('http://127.0.0.1:27000/translation/status');
      const result = await response.json();
      console.log('[preload.js] Translation status:', result);
      return result;
    } catch (error) {
      console.error('[preload.js] Get translation status error:', error);
      return { enabled: false, loading: false, loaded: false };
    }
  },

  // 窗口控制API
  setAlwaysOnTop: async (alwaysOnTop) => {
    try {
      await ipcRenderer.invoke('set-always-on-top', alwaysOnTop);
      console.log('[preload.js] Set always on top:', alwaysOnTop);
    } catch (error) {
      console.error('[preload.js] Set always on top error:', error);
    }
  },

  setWindowSize: async (width, height) => {
    try {
      await ipcRenderer.invoke('set-window-size', width, height);
      console.log('[preload.js] Set window size:', width, height);
    } catch (error) {
      console.error('[preload.js] Set window size error:', error);
    }
  },

  closeApp: async () => {
    try {
      await ipcRenderer.invoke('close-app');
      console.log('[preload.js] Close app');
    } catch (error) {
      console.error('[preload.js] Close app error:', error);
    }
  },

  // 窗口尺寸控制API
  setWindowSize: async (width, height) => {
    try {
      await ipcRenderer.invoke('set-window-size', { width, height });
      console.log('[preload.js] Set window size:', width, 'x', height);
    } catch (error) {
      console.error('[preload.js] Set window size error:', error);
    }
  },

  setWindowPosition: async (x, y) => {
    try {
      await ipcRenderer.invoke('set-window-position', { x, y });
      console.log('[preload.js] Set window position:', x, ',', y);
    } catch (error) {
      console.error('[preload.js] Set window position error:', error);
    }
  },

  setWindowBounds: async (x, y, width, height) => {
    try {
      await ipcRenderer.invoke('set-window-bounds', { x, y, width, height });
      console.log('[preload.js] Set window bounds:', x, ',', y, ',', width, 'x', height);
    } catch (error) {
      console.error('[preload.js] Set window bounds error:', error);
    }
  },

  getScreenSize: async () => {
    try {
      const size = await ipcRenderer.invoke('get-screen-size');
      console.log('[preload.js] Get screen size:', size);
      return size;
    } catch (error) {
      console.error('[preload.js] Get screen size error:', error);
      return { width: 1920, height: 1080 }; // 默认值
    }
  },

  // 文件操作API
  openRecordingFolder: async () => {
    try {
      await ipcRenderer.invoke('open-recording-folder');
      console.log('[preload.js] Open recording folder');
      return { success: true };
    } catch (error) {
      console.error('[preload.js] Open recording folder error:', error);
      return { success: false, error: error.message };
    }
  }
});
