window.addEventListener('DOMContentLoaded', () => {
  const subtitleContainer = document.getElementById('subtitles');
  const langSelect = document.getElementById('target-lang');
  const deviceSelect = document.getElementById('audio-device');

  const MAX_HISTORY = 2;
  let history = [];
  let currentTargetLang = 'en';
  let currentDeviceId = '';

  function isArabic(text) {
    return /[؀-ۿ]/.test(text);
  }

  function renderSubtitles() {
    if (!subtitleContainer) return;
    if (history.length === 0) {
      subtitleContainer.innerText = '暂无字幕数据';
      return;
    }
    const toShow = history.slice(-MAX_HISTORY);
    subtitleContainer.innerHTML = toShow.map(pair => {
      const infoClass = isArabic(pair.text) ? 'info arabic' : 'info';
      const transClass = isArabic(pair.translated) ? 'translated arabic' : 'translated';
      return `
        <div class="pair">
          <div class="${infoClass}">${sanitizeText(pair.text)}</div>
          <div class="${transClass}">${sanitizeText(pair.translated)}</div>
        </div>`;
    }).join('');
    subtitleContainer.scrollTop = subtitleContainer.scrollHeight;
  }

  function sanitizeText(text) {
    if (typeof text !== 'string') return '';
    return text.trim();
  }

  function renderDeviceList(list) {
    if (!deviceSelect) return;
    deviceSelect.innerHTML = '';
    list.forEach((dev, idx) => {
      const opt = document.createElement('option');
      opt.value = dev.index;
      opt.textContent = dev.name || `设备${idx}`;
      deviceSelect.appendChild(opt);
    });
    if (list.length > 0) {
      deviceSelect.value = list[0].index;
      currentDeviceId = list[0].index;
    }
  }

  function handleSubtitleData(data) {
    if (data.device_list) {
      renderDeviceList(data.device_list);
      return;
    }
    if (data.translated || data.data || data.info) {
      const original = (typeof data.data === 'string' && data.data.trim()) ? data.data
                      : (typeof data.info === 'string' ? data.info : '');
      const translated = data.translated || '';
      history.push({ text: original, translated });
      if (history.length > MAX_HISTORY) history.shift();
      renderSubtitles();
    } else {
      subtitleContainer.innerText = '收到数据但无info字段：' + JSON.stringify(data);
    }
  }

  function reconnectWS() {
    console.warn('[WS] reconnectWS: 连接断开，2 秒后尝试重连...');
    closeOldWS();
    setTimeout(() => {
      console.warn('[WS] reconnectWS: 执行connectToSubtitleWS');
      connectToSubtitleWS(currentTargetLang);
    }, 2000);
  }

  function bindWSEvents(ws) {
    if (!ws) return;
    ws.onclose = (e) => {
      console.warn('[WS] onclose', e);
      reconnectWS();
    };
    ws.onerror = (e) => {
      console.warn('[WS] onerror', e);
      reconnectWS();
    };
  }

  let wsReadyInterval = null;
  function closeOldWS() {
    const ws = window.subtitleAPI?.getCurrentWS?.();
    if (ws && (ws.readyState === 0 || ws.readyState === 1)) {
      try {
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
      } catch (e) { console.warn('[WS] 关闭旧ws异常', e); }
    }
  }

  function waitWSReady(cb) {
    if (wsReadyInterval) clearInterval(wsReadyInterval);
    wsReadyInterval = setInterval(() => {
      const ws = window.subtitleAPI?.getCurrentWS?.();
      if (ws && ws.readyState === 1) {
        clearInterval(wsReadyInterval);
        wsReadyInterval = null;
        cb && cb();
      }
    }, 200);
  }

  function syncTargetLangToWS(lang) {
    const ws = window.subtitleAPI?.getCurrentWS?.();
    const targetLang = lang || langSelect?.value || currentTargetLang;
    if (ws && ws.readyState === 1) {
      try {
        window.subtitleAPI.setTargetLang(targetLang);
        console.log('[Lang] ws ready后同步目标语言:', targetLang);
      } catch (e) {
        console.warn('[Lang] 设置目标语言失败:', e);
      }
    }
  }

  function connectToSubtitleWS(langForSync) {
    closeOldWS();
    if (!window.subtitleAPI || !window.subtitleAPI.connect) {
      console.error('[WS] subtitleAPI 未注入');
      return;
    }
    try {
      window.subtitleAPI.connect(
        handleSubtitleData,
        () => {
          const targetLang = langForSync || currentTargetLang;
          console.log('[WS] 已连接，立即设置语言:', targetLang);
          const ws = window.subtitleAPI.getCurrentWS && window.subtitleAPI.getCurrentWS();
          bindWSEvents(ws);
          try {
            window.subtitleAPI.setTargetLang(targetLang);
          } catch (e) {
            console.warn('[Lang] 初始设置语言失败:', e);
          }
          waitWSReady(() => {
            setTimeout(() => {
              if (currentDeviceId) window.subtitleAPI.switchDevice(currentDeviceId);
              ws?.send(JSON.stringify({ get_device_list: true }));
            }, 200);
          });
        },
        (err) => {
          console.warn('[WS] onerror (from preload)', err);
          reconnectWS();
        },
        (e) => {
          console.warn('[WS] onclose (from preload)', e);
          reconnectWS();
        }
      );
    } catch (err) {
      console.error('[WS] connect() 异常:', err);
    }
  }

  if (langSelect) {
    langSelect.addEventListener('change', () => {
      const newLang = langSelect.value;
      if (newLang === currentTargetLang) return;
      currentTargetLang = newLang;
      console.log('[Lang] 切换语言:', currentTargetLang);
      const ws = window.subtitleAPI?.getCurrentWS?.();
      if (ws && ws.readyState === 1) {
        window.subtitleAPI.setTargetLang(currentTargetLang);
      } else {
        connectToSubtitleWS(currentTargetLang);
        waitWSReady(() => syncTargetLangToWS(currentTargetLang));
        console.warn('WebSocket 未连接，正在自动重连并切换语言...');
      }
    });
  }

  if (deviceSelect) {
    deviceSelect.addEventListener('change', () => {
      const devId = deviceSelect.value;
      if (devId === currentDeviceId) return;
      currentDeviceId = devId;
      console.log('[Device] 切换设备:', devId);
      window.subtitleAPI.switchDevice(devId);
    });
  }

  if (window.subtitleAPI) {
    connectToSubtitleWS(currentTargetLang);
  } else {
    subtitleContainer.innerText = 'window.subtitleAPI 未注入，preload.js 可能未生效';
  }
});
