const { contextBridge } = require('electron');
console.log('[preload.js] preload script is running');


let lastSocket = null;

contextBridge.exposeInMainWorld('subtitleAPI', {
  connect: (onMessage, onReady, onError, onClose) => {
    // 先关闭旧连接
    if (lastSocket && (lastSocket.readyState === WebSocket.CONNECTING || lastSocket.readyState === WebSocket.OPEN)) {
      console.log('[preload.js] Closing old WebSocket connection');
      lastSocket.onclose = null;
      lastSocket.onerror = null;
      lastSocket.close();
    }
    
    const socket = new WebSocket('ws://127.0.0.1:27000/ws/subscribe');

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (e) {
        console.error('[preload.js] JSON parse error:', e);
      }
    };

    socket.onopen = () => {
      console.log('[preload.js] WebSocket connected');
      lastSocket = socket;
      if (typeof onReady === 'function') onReady();
    };

    socket.onerror = (err) => {
      if (typeof onError === 'function') onError(err);
    };
    socket.onclose = (e) => {
      if (typeof onClose === 'function') onClose(e);
    };

    lastSocket = socket;
  },

  getCurrentWS: () => lastSocket,

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
  }
});
