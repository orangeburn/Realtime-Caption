window.addEventListener('DOMContentLoaded', () => {
  const subtitleContainer = document.getElementById('subtitles');
  const langSelect = document.getElementById('target-lang');
  const deviceSelect = document.getElementById('audio-device');
  const languageSelector = document.querySelector('.language-selector');
  const controlsContainer = document.querySelector('.controls-container');

  const MAX_HISTORY = 2;
  let history = [];
  let currentTargetLang = 'en';
  let currentDeviceId = '';
  let systemStarted = false;
  let isStartupMode = false;
  let translationModelLoaded = false; // 新增：标记翻译模型是否已加载
  let translationEnabled = false; // 新增：标记翻译功能是否启用

  // 控制栏显示控制
  function initControlsVisibility() {
    let hideTimeout;
    let isMouseInControls = false;
    
    function showControls() {
      if (hideTimeout) {
        clearTimeout(hideTimeout);
        hideTimeout = null;
      }
      if (controlsContainer) {
        controlsContainer.classList.add('show');
      }
    }
    
    function hideControls(delay = 200) {
      if (isMouseInControls) return;
      
      if (hideTimeout) clearTimeout(hideTimeout);
      hideTimeout = setTimeout(() => {
        if (controlsContainer && !isMouseInControls) {
          controlsContainer.classList.remove('show');
        }
      }, delay);
    }
    
    // 鼠标在窗口内移动时显示控制栏
    document.addEventListener('mousemove', showControls);
    
    // 鼠标进入窗口时显示控制栏
    document.addEventListener('mouseenter', showControls);
    
    // 鼠标离开窗口时隐藏控制栏（延长延迟，给拖拽更多时间）
    document.addEventListener('mouseleave', () => {
      hideControls(1000); // 增加到1秒延迟
    });
    
    // 控制栏自身的鼠标事件
    if (controlsContainer) {
      controlsContainer.addEventListener('mouseenter', () => {
        isMouseInControls = true;
        showControls();
      });
      
      controlsContainer.addEventListener('mouseleave', () => {
        isMouseInControls = false;
        hideControls(500); // 离开控制栏时稍长延迟
      });
    }
  }
  
  initControlsVisibility();

  // 翻译模型管理
  async function ensureTranslationModelLoaded() {
    if (translationModelLoaded) return true;
    
    try {
      // 先检查状态
      const status = await window.subtitleAPI.getTranslationStatus();
      if (status.loaded) {
        translationModelLoaded = true;
        return true;
      }
      
      if (status.loading) {
        // 正在加载中，等待加载完成
        addStartupLog('翻译模型正在加载中...', 'backend');
        return false;
      }
      
      // 开始加载翻译模型
      addStartupLog('正在加载翻译模型...', 'backend');
      const result = await window.subtitleAPI.loadTranslationModel();
      
      if (result.success) {
        translationModelLoaded = true;
        addStartupLog('翻译模型加载成功', 'backend');
        return true;
      } else {
        addStartupLog(`翻译模型加载失败: ${result.message}`, 'backend');
        return false;
      }
    } catch (error) {
      console.error('Failed to load translation model:', error);
      addStartupLog(`翻译模型加载失败: ${error.message}`, 'backend');
      return false;
    }
  }

  function isArabic(text) {
    return /[؀-ۿ]/.test(text);
  }

  // 启动日志管理 - 在字幕容器内显示
  function addStartupLog(message, type = 'system') {
    if (systemStarted || !isStartupMode) return;
    
    // 只显示后端模型加载相关的日志
    if (type !== 'backend' && !message.includes('模型') && !message.includes('Model')) return;
    
    if (!subtitleContainer.classList.contains('startup-mode')) {
      subtitleContainer.classList.add('startup-mode');
      subtitleContainer.innerHTML = '<div class="progress">🚀 系统启动中...</div>';
    }
    
    const logLine = document.createElement('div');
    logLine.className = `log-line log-${type}`;
    logLine.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    
    // 插入到进度信息之前
    const progressElement = subtitleContainer.querySelector('.progress');
    if (progressElement) {
      subtitleContainer.insertBefore(logLine, progressElement);
    } else {
      subtitleContainer.appendChild(logLine);
    }
    
    subtitleContainer.scrollTop = subtitleContainer.scrollHeight;
    
    // 限制日志行数，避免过多
    const logLines = subtitleContainer.querySelectorAll('.log-line');
    if (logLines.length > 5) {
      logLines[0].remove();
    }
  }

  function updateProgress(message) {
    if (systemStarted || !isStartupMode) return;
    
    let progressElement = subtitleContainer.querySelector('.progress');
    if (!progressElement) {
      progressElement = document.createElement('div');
      progressElement.className = 'progress';
      subtitleContainer.appendChild(progressElement);
    }
    progressElement.textContent = message;
  }

  function finishStartup() {
    if (systemStarted) return;
    systemStarted = true;
    isStartupMode = false;
    
    // 清空启动日志，恢复字幕界面
    subtitleContainer.classList.remove('startup-mode');
    const subtitlesContainer = subtitleContainer.querySelector('.subtitles-container');
    if (subtitlesContainer) {
      subtitlesContainer.innerHTML = '<div class="pair"><div class="info">等待字幕中...</div></div>';
    }
  }

  if (window.subtitleAPI) {
    // 立即退出启动模式并连接WebSocket
    finishStartup();
    connectToSubtitleWS(currentTargetLang);
  } else {
    subtitleContainer.innerText = 'window.subtitleAPI 未注入，preload.js 可能未生效';
  }

  let subtitleHeight = 0; // 追踪字幕总高度

  function renderSubtitles() {
    if (!subtitleContainer || isStartupMode) return;
    
    const subtitlesContainer = subtitleContainer.querySelector('.subtitles-container');
    if (!subtitlesContainer) return;
    
    if (history.length === 0) {
      subtitlesContainer.innerHTML = '<div class="pair"><div class="info">暂无字幕数据</div></div>';
      subtitleHeight = 0;
      return;
    }
    
    const toShow = history.slice(-MAX_HISTORY);
    
    // 检查是否有新字幕添加
    const currentCount = subtitlesContainer.children.length;
    const newCount = toShow.length;
    
    if (newCount > currentCount) {
      // 标记现有字幕为旧字幕（淡出）
      Array.from(subtitlesContainer.children).forEach(child => {
        child.classList.add('old');
      });
      
      // 有新字幕，添加到底部
      const newPairs = toShow.slice(currentCount);
      newPairs.forEach(pair => {
        const infoClass = isArabic(pair.text) ? 'info arabic' : 'info';
        const transClass = isArabic(pair.translated) ? 'translated arabic' : 'translated';
        
        const pairElement = document.createElement('div');
        pairElement.className = 'pair'; // 新字幕不添加old类，保持清晰
        
        if (!translationEnabled) {
          pairElement.innerHTML = `<div class="${infoClass}">${sanitizeText(pair.text)}</div>`;
        } else {
          pairElement.innerHTML = `
            <div class="${infoClass}">${sanitizeText(pair.text)}</div>
            <div class="${transClass}">${sanitizeText(pair.translated)}</div>`;
        }
        
        subtitlesContainer.appendChild(pairElement);
      });
      
      // 计算新字幕的高度并执行滚动
      setTimeout(() => {
        const newPairElements = Array.from(subtitlesContainer.children).slice(currentCount);
        let newHeight = 0;
        newPairElements.forEach(el => {
          newHeight += el.offsetHeight;
        });
        
        subtitleHeight += newHeight;
        subtitlesContainer.style.transform = `translateY(-${subtitleHeight}px)`;
        
        // 移除超出历史限制的旧字幕
        while (subtitlesContainer.children.length > MAX_HISTORY) {
          const firstChild = subtitlesContainer.firstChild;
          const removedHeight = firstChild.offsetHeight;
          subtitleHeight -= removedHeight;
          firstChild.remove();
          subtitlesContainer.style.transform = `translateY(-${subtitleHeight}px)`;
        }
      }, 50);
    } else {
      // 重新渲染所有字幕（如翻译开关切换）
      subtitlesContainer.innerHTML = '';
      subtitleHeight = 0;
      
      toShow.forEach((pair, index) => {
        const infoClass = isArabic(pair.text) ? 'info arabic' : 'info';
        const transClass = isArabic(pair.translated) ? 'translated arabic' : 'translated';
        
        const pairElement = document.createElement('div');
        pairElement.className = 'pair';
        
        // 为旧字幕添加old类实现淡出效果，最新字幕保持清晰
        if (index < toShow.length - 1) {
          pairElement.classList.add('old');
        }
        
        if (!translationEnabled) {
          pairElement.innerHTML = `<div class="${infoClass}">${sanitizeText(pair.text)}</div>`;
        } else {
          pairElement.innerHTML = `
            <div class="${infoClass}">${sanitizeText(pair.text)}</div>
            <div class="${transClass}">${sanitizeText(pair.translated)}</div>`;
        }
        
        subtitlesContainer.appendChild(pairElement);
      });
      
      subtitlesContainer.style.transform = 'translateY(0)';
    }
  }

  function sanitizeText(text) {
    if (typeof text !== 'string') return '';
    return text.trim();
  }

  function renderDeviceList(list) {
    if (!deviceSelect) return;
    
    // 保存当前选择的设备ID
    const previouslySelectedDevice = currentDeviceId || deviceSelect.value;
    
    deviceSelect.innerHTML = '';
    list.forEach((dev, idx) => {
      const opt = document.createElement('option');
      opt.value = dev.index;
      opt.textContent = dev.name || `设备${idx}`;
      deviceSelect.appendChild(opt);
    });
    
    if (list.length > 0) {
      // 尝试恢复之前选择的设备
      const deviceExists = list.some(dev => dev.index == previouslySelectedDevice);
      if (deviceExists && previouslySelectedDevice) {
        deviceSelect.value = previouslySelectedDevice;
        currentDeviceId = previouslySelectedDevice;
      } else {
        // 如果之前的设备不存在，才使用第一个设备
        deviceSelect.value = list[0].index;
        currentDeviceId = list[0].index;
      }
    }
  }

  function handleSubtitleData(data) {
    // 如果还在启动模式，忽略字幕数据
    if (isStartupMode) return;
    
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
    // 只有在翻译功能启用时才同步目标语言
    if (ws && ws.readyState === 1 && translationEnabled) {
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
        async () => {
          const targetLang = langForSync || currentTargetLang;
          console.log('[WS] 已连接，立即设置语言:', targetLang);
          const ws = window.subtitleAPI.getCurrentWS && window.subtitleAPI.getCurrentWS();
          bindWSEvents(ws);
          
          // 检查翻译模型状态（但不自动加载）
          try {
            const status = await window.subtitleAPI.getTranslationStatus();
            translationModelLoaded = status.loaded;
            console.log('[WS] 翻译模型状态:', status);
          } catch (error) {
            console.warn('[WS] 检查翻译模型状态失败:', error);
          }
          
          try {
            // 只有在翻译功能启用时才设置目标语言
            if (translationEnabled) {
              window.subtitleAPI.setTargetLang(targetLang);
            }
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

  // 翻译图标点击处理
  const translateIcon = document.getElementById('translate-icon');
  if (translateIcon) {
    translateIcon.addEventListener('click', async () => {
      const wasEnabled = translationEnabled;
      
      if (!wasEnabled) {
        // 启用翻译 - 显示加载状态
        translateIcon.classList.add('loading');
        translateIcon.classList.remove('active');
        
        console.log('[Translation] 启用翻译功能，正在加载翻译模型...');
        const loadSuccess = await ensureTranslationModelLoaded();
        
        translateIcon.classList.remove('loading');
        
        if (loadSuccess) {
          translationEnabled = true;
          translateIcon.classList.add('active');
          
          // 显示语言选择容器
          if (languageSelector) {
            languageSelector.classList.remove('hidden');
          }
          
          // 发送当前目标语言设置
          const ws = window.subtitleAPI?.getCurrentWS?.();
          if (ws && ws.readyState === 1) {
            window.subtitleAPI.setTargetLang(currentTargetLang);
          }
          
          console.log('[Translation] 翻译功能已启用');
        } else {
          console.warn('[Translation] 翻译模型加载失败');
          // 保持置灰状态
        }
      } else {
        // 禁用翻译
        translationEnabled = false;
        translateIcon.classList.remove('active');
        
        // 隐藏语言选择容器
        if (languageSelector) {
          languageSelector.classList.add('hidden');
        }
        
        // 重新渲染字幕（只显示原文）
        renderSubtitles();
        
        console.log('[Translation] 翻译功能已禁用');
      }
    });
  }

  if (langSelect) {
    langSelect.addEventListener('change', async () => {
      const newLang = langSelect.value;
      if (newLang === currentTargetLang) return;
      
      // 确保翻译模型已加载
      if (!translationModelLoaded) {
        console.log('[Lang] 切换语言时发现翻译模型未加载，正在加载...');
        const loadSuccess = await ensureTranslationModelLoaded();
        if (!loadSuccess) {
          console.warn('[Lang] 翻译模型加载失败，将继续切换语言但可能无翻译');
        }
      }
      
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

  if (!window.subtitleAPI) {
    subtitleContainer.innerText = 'window.subtitleAPI 未注入，preload.js 可能未生效';
  }
  // 注意：WebSocket连接将在启动检查完成后由 finishStartup() 函数建立
});
