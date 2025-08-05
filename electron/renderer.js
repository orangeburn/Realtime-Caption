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
  
  // 记录模式相关变量
  let recordMode = false; // 记录模式开关
  let pendingModeSwitch = false; // 标记是否有待处理的模式切换
  let recordHistory = []; // 记录的字幕历史
  let editEventsBound = false; // 标记是否已经绑定编辑事件
  let isEditingRecord = false; // 标记是否正在编辑记录
  let lastTranslationState = false; // 记录上次翻译状态，用于检测状态变化
  let currentEditingElement = null; // 保存当前正在编辑的元素
  let editingScrollPosition = 0; // 保存编辑时的滚动位置
  let recordStartTime = null; // 记录模式开始时间
  
  // 录音控制相关变量（简化版 - 移除暂停功能）
  let recordingState = 'idle'; // 录音状态: 'idle', 'recording', 'stopped'
  let recordingStartTime = null; // 录音开始时间（第一段音频的时间戳）
  let recordingConfirmed = false; // 后端录音开始确认状态
  let currentSessionId = null;
  
  // 音频录制器实例 - 使用后端服务
  let audioRecorderConnected = false;
  let currentRecordingFile = null;
  
  // 录音WebSocket连接
  let recordingWS = null;
  
  // 导出对话框控制变量 - 防止重复弹窗
  let exportDialogShown = false;

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

  // 初始显示控制栏，确保用户可以看到控制选项
  if (controlsContainer) {
    // 延迟显示控制栏，确保DOM完全加载
    setTimeout(() => {
      controlsContainer.classList.add('show');
      console.log('[Controls] 控制栏已初始显示');
    }, 200);
  }

  // 新增：WebSocket状态诊断函数
  function diagnoseWebSocketState() {
    console.log('[WebSocket诊断] 开始检查WebSocket状态');
    console.log('  window.subtitleAPI存在:', !!window.subtitleAPI);
    console.log('  getCurrentWS函数存在:', !!window.subtitleAPI?.getCurrentWS);
    
    const ws = window.subtitleAPI?.getCurrentWS?.();
    console.log('  WebSocket对象:', ws);
    console.log('  WebSocket对象详细信息:');
    console.log('    - 类型:', typeof ws);
    console.log('    - 是否为null/undefined:', ws == null);
    console.log('    - 构造函数:', ws?.constructor?.name);
    // 移除instanceof检查，因为在Electron上下文隔离中可能失败
    console.log('    - 对象键值:', Object.keys(ws || {}));
    
    if (ws) {
      const stateMap = {
        0: 'CONNECTING',
        1: 'OPEN', 
        2: 'CLOSING',
        3: 'CLOSED'
      };
      const currentState = stateMap[ws.readyState] || `未知状态(${ws.readyState})`;
      console.log('  WebSocket状态:', currentState, '(', ws.readyState, ')');
      console.log('  WebSocket URL:', ws.url);
      console.log('  WebSocket协议:', ws.protocol);
      
      // 检查是否有事件监听器和方法
      console.log('  方法检查:');
      console.log('    - onopen:', typeof ws.onopen, ws.onopen != null);
      console.log('    - onmessage:', typeof ws.onmessage, ws.onmessage != null);
      console.log('    - onerror:', typeof ws.onerror, ws.onerror != null);
      console.log('    - onclose:', typeof ws.onclose, ws.onclose != null);
      console.log('    - send:', typeof ws.send, typeof ws.send === 'function');
      console.log('    - close:', typeof ws.close, typeof ws.close === 'function');
      
      // 检查WebSocket是否有效
      const isValid = (
        typeof ws.send === 'function' &&
        typeof ws.close === 'function' &&
        typeof ws.readyState === 'number' &&
        ws.constructor?.name === 'WebSocket'
      );
      console.log('  WebSocket有效性检查:', isValid);
    } else {
      console.log('  WebSocket对象为null或undefined');
      
      // 尝试直接检查preload暴露的API
      console.log('  检查subtitleAPI详细结构:');
      if (window.subtitleAPI) {
        console.log('    - API对象键值:', Object.keys(window.subtitleAPI));
        console.log('    - getCurrentWS类型:', typeof window.subtitleAPI.getCurrentWS);
        
        // 尝试直接调用并检查结果
        try {
          const directResult = window.subtitleAPI.getCurrentWS();
          console.log('    - 直接调用结果:', directResult);
          console.log('    - 直接调用结果类型:', typeof directResult);
        } catch (e) {
          console.log('    - 直接调用异常:', e);
        }
      }
    }
  }

  // 记录模式管理
  async function toggleRecordMode() {
    // 如果当前在记录模式且正在录音，先弹出对话框确认
    if (recordMode && recordingState !== 'idle') {
      console.log('[Record] 记录模式下正在录音，弹出结束录音对话框');
      pendingModeSwitch = true; // 标记需要在对话框关闭后切换模式
      stopRecording(); // 这会触发录音结束和对话框显示
      return; // 不继续执行模式切换，等待对话框操作
    }
    
    // 执行实际的模式切换
    await performModeSwitch();
  }
  
  // 实际执行模式切换的函数
  async function performModeSwitch() {
    recordMode = !recordMode;
    const recordIcon = document.getElementById('record-icon');
    const floatingRecordPanel = document.getElementById('floating-record-panel');
    const body = document.body;
    
    if (recordMode) {
      // 启用记录模式前先诊断WebSocket状态
      console.log('[Record] 启用记录模式前的WebSocket状态诊断:');
      diagnoseWebSocketState();
      
      // 启用记录模式 - 调整窗口为全屏高度并定位到屏幕顶部
      recordIcon.classList.add('active');
      body.classList.add('record-mode');
      
      // 获取屏幕尺寸并调整窗口位置和尺寸
      try {
        const screenSize = await window.subtitleAPI.getScreenSize();
        // 将窗口设置为：x=0, y=0（屏幕顶部），宽度800，高度为屏幕高度
        await window.subtitleAPI.setWindowBounds(0, 0, 800, screenSize.height);
        console.log('[Record] 记录模式已启用 - 窗口已调整为全屏高度并移至屏幕顶部');
      } catch (error) {
        console.warn('[Record] 调整窗口尺寸和位置失败:', error);
      }
      
      // 显示悬浮录音控制面板
      if (floatingRecordPanel) {
        floatingRecordPanel.classList.add('active');
      }
      
      // 初始化记录显示区域（显示等待录音的状态）
      const recordContent = document.getElementById('record-content');
      if (recordContent) {
        recordContent.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">点击录音按钮开始录音和字幕记录</div>';
      }
      
      updateRecordDisplay();
      console.log('[Record] 记录模式已启用 - 点击右下角录音按钮开始录音');
    } else {
      // 关闭记录模式
      recordIcon.classList.remove('active');
      body.classList.remove('record-mode');
      
      // 恢复原始窗口尺寸和位置（居中显示）
      try {
        const screenSize = await window.subtitleAPI.getScreenSize();
        const centerX = Math.floor((screenSize.width - 800) / 2);
        const centerY = Math.floor((screenSize.height - 200) / 2);
        await window.subtitleAPI.setWindowBounds(centerX, centerY, 800, 200);
        console.log('[Record] 记录模式已关闭 - 窗口已恢复原始尺寸并居中显示');
      } catch (error) {
        console.warn('[Record] 恢复窗口尺寸和位置失败:', error);
      }
      
      // 隐藏悬浮录音控制面板
      if (floatingRecordPanel) {
        floatingRecordPanel.classList.remove('active');
      }
      
      // 恢复字幕模式 - 确保字幕容器结构正确并立即渲染
      console.log('[Record] 记录模式已关闭，恢复字幕显示');
      console.log('[Record] 当前录音状态:', recordingState, '历史记录数量:', history.length);
      
      // 确保字幕容器有正确的结构
      if (subtitleContainer) {
        let subtitlesContainer = subtitleContainer.querySelector('.subtitles-container');
        if (!subtitlesContainer) {
          // 如果没有subtitles-container，创建一个
          subtitlesContainer = document.createElement('div');
          subtitlesContainer.className = 'subtitles-container';
          subtitleContainer.innerHTML = '';
          subtitleContainer.appendChild(subtitlesContainer);
          console.log('[Record] 重建字幕容器结构');
        }
        
        // 重置字幕高度和样式
        subtitleHeight = 0;
        subtitlesContainer.style.transform = 'translateY(0)';
        
        // 强制刷新字幕显示 - 先清空再重新渲染
        console.log('[Record] 强制刷新字幕显示，当前历史记录数量:', history.length);
        subtitlesContainer.innerHTML = '';
        
        // 立即渲染当前字幕历史，无论录音状态如何
        setTimeout(() => {
          console.log('[Record] 强制调用 renderSubtitles()');
          renderSubtitles();
          console.log('[Record] 字幕刷新完成，容器内容:', subtitlesContainer.innerHTML.length > 0 ? '有内容' : '空');
        }, 50);
      }
    }
    
    // 重置模式切换标记
    pendingModeSwitch = false;
  }

  // 更新录音UI状态（简化版 - 移除暂停功能）
  function updateRecordingUI() {
    const recordBtn = document.getElementById('record-btn');
    const stopBtn = document.getElementById('stop-btn');
    const statusElement = document.querySelector('.recording-status');
    const statusText = document.querySelector('.status-text');
    
    // 移除所有状态类
    statusElement.classList.remove('recording', 'stopped');
    recordBtn.classList.remove('recording');
    
    switch (recordingState) {
      case 'idle':
        recordBtn.style.display = 'flex';
        stopBtn.style.display = 'none';
        statusText.textContent = '待录音';
        break;
        
      case 'recording':
        recordBtn.style.display = 'none';
        stopBtn.style.display = 'flex';
        statusElement.classList.add('recording');
        recordBtn.classList.add('recording');
        statusText.textContent = '录音中';
        break;
        
      case 'stopped':
        recordBtn.style.display = 'flex';
        stopBtn.style.display = 'none';
        statusElement.classList.add('stopped');
        statusText.textContent = '已完成';
        break;
    }
  }

  // WebSocket监控相关变量
  let recordingMonitorInterval = null;
  
  // 启动录音期间的WebSocket监控
  function startRecordingMonitor() {
    if (recordingMonitorInterval) {
      clearInterval(recordingMonitorInterval);
    }
    
    console.log('[Recording] 启动WebSocket连接监控');
    recordingMonitorInterval = setInterval(() => {
      // 只有在完全空闲状态时才停止监控
      if (recordingState === 'idle' && !recordMode) {
        // 录音已结束且不在记录模式，停止监控
        stopRecordingMonitor();
        return;
      }
      
      const wsState = window.subtitleAPI?.getWebSocketState?.();
      console.log('[Recording] WebSocket监控检查:', wsState);
      
      if (!wsState || !wsState.connected) {
        console.warn('[Recording] 检测到WebSocket连接断开，立即尝试重连...');
        console.warn('[Recording] 当前录音状态:', recordingState);
        console.warn('[Recording] 当前session_id:', currentSessionId);
        console.warn('[Recording] 当前记录模式:', recordMode);
        
        // 立即尝试重连
        reconnectWS();
        
        // 显示警告给用户
        if (recordingState === 'recording') {
          console.warn('[Recording] 录音过程中连接断开，可能会丢失音频数据');
        }
      } else {
        console.log('[Recording] WebSocket连接正常');
      }
    }, 3000); // 每3秒检查一次，更频繁的检查
  }
  
  // 停止录音监控
  function stopRecordingMonitor() {
    if (recordingMonitorInterval) {
      clearInterval(recordingMonitorInterval);
      recordingMonitorInterval = null;
      console.log('[Recording] 已停止WebSocket连接监控');
    }
  }
  async function startRecording() {
    if (recordingState !== 'idle') {
      console.log('[Recording] 录音已在进行中或已完成，当前状态:', recordingState);
      return;
    }

    // 重置双流架构标志
    window.isDualStreamRecording = false;
    
    try {
      console.log('[Recording] ========== 开始新的录音流程（WebSocket方式） ==========');
      
      // 强制重置所有录音相关状态，确保干净的开始
      recordingState = 'idle';
      recordingConfirmed = false;
      currentSessionId = null;
      recordingStartTime = null;
      currentRecordingFile = null;
      recordHistory = [];
      exportDialogShown = false; // 重置导出对话框状态
      
      console.log('[Recording] 录音状态已重置，准备开始新录音');
      
      // 生成唯一的文件名和session ID
      const now = new Date();
      const year = now.getFullYear();
      const month = (now.getMonth() + 1).toString().padStart(2, '0');
      const day = now.getDate().toString().padStart(2, '0');
      const hour = now.getHours().toString().padStart(2, '0');
      const minute = now.getMinutes().toString().padStart(2, '0');
      const second = now.getSeconds().toString().padStart(2, '0');
      const millisecond = now.getMilliseconds().toString().padStart(3, '0');
      const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
      
      const filename = `recording-${year}-${month}-${day}-${hour}${minute}${second}${millisecond}-${random}.wav`;
      const sessionId = `session-${year}${month}${day}-${hour}${minute}${second}${millisecond}-${random}`;
      
      console.log('[Recording] 生成新录音标识:', { filename, sessionId });
      
      // 检查WebSocket连接状态
      const wsState = window.subtitleAPI?.getWebSocketState?.();
      if (!wsState || !wsState.connected) {
        throw new Error('WebSocket未连接，无法开始录音');
      }
      
      // 通过WebSocket发送录音开始命令
      const startCommand = {
        start_recording: true,
        filename: filename,
        session_id: sessionId  // 显式指定session ID
      };
      
      console.log('[Recording] 发送录音开始命令:', startCommand);
      const sendResult = window.subtitleAPI?.sendMessage?.(JSON.stringify(startCommand));
      
      if (!sendResult || !sendResult.success) {
        throw new Error(`发送录音命令失败: ${sendResult?.error || '未知错误'}`);
      }
      
      // 设置前端状态（等待后端确认）
      recordingState = 'recording';
      recordingStartTime = now.getTime();
      recordingConfirmed = false;
      currentRecordingFile = filename;
      currentSessionId = sessionId;  // 设置新的session ID
      
      // 清空之前的记录
      recordHistory = [];
      updateRecordDisplay();
      updateRecordingUI();
      
      console.log('[Recording] WebSocket录音命令已发送，等待后端确认');
      console.log('[Recording] 前端录音状态:', {
        recordingState,
        currentSessionId,
        currentRecordingFile,
        recordingStartTime
      });
      
      // 启动录音期间的WebSocket监控（用于字幕同步）
      startRecordingMonitor();
      
    } catch (error) {
      console.error('[Recording] 启动录音失败:', error);
      recordingState = 'idle';
      updateRecordingUI();
      alert(`启动录音失败: ${error.message}`);
    }
  }
  
  // 暂停和恢复录音功能已移除 - 简化录音控制
  
  async function stopRecording() {
    if (recordingState === 'idle') {
      console.log('[Recording] 没有正在进行的录音');
      return;
    }
    
    try {
      console.log('[Recording] ========== 停止录音流程 ==========');
      console.log('[Recording] 停止前状态检查:', {
        recordingState,
        currentSessionId,
        recordHistory: recordHistory.length,
        recordingStartTime
      });
      
      // 移除暂停状态检查 - 简化录音停止逻辑
      
      // 通过新API发送录音停止命令给Python模块
      const wsState = window.subtitleAPI?.getWebSocketState?.();
      console.log('[Recording] 停止录音前WebSocket状态:', wsState);
      console.log('[Recording] 当前session_id:', currentSessionId);
      console.log('[Recording] 当前recordHistory长度:', recordHistory.length);
      
      if (wsState && wsState.connected) {
        const stopCommand = {
          stop_recording: true,
          session_id: currentSessionId
        };
        
        console.log('[Recording] 准备发送停止命令:', stopCommand);
        const sendResult = window.subtitleAPI?.sendMessage?.(JSON.stringify(stopCommand));
        
        if (!sendResult || !sendResult.success) {
          console.warn(`发送停止命令失败: ${sendResult?.error || '未知错误'}`);
          console.warn('[Recording] WebSocket可能已断开，尝试重连后重新发送');
          
          // 如果发送失败，尝试重连并重新发送
          reconnectWS();
          setTimeout(() => {
            const retryState = window.subtitleAPI?.getWebSocketState?.();
            if (retryState && retryState.connected) {
              console.log('[Recording] 重连成功，重新发送停止命令');
              const retryResult = window.subtitleAPI?.sendMessage?.(JSON.stringify(stopCommand));
              if (retryResult && retryResult.success) {
                console.log('[Recording] 重试发送停止命令成功');
              } else {
                console.error('[Recording] 重试发送停止命令仍然失败');
              }
            } else {
              console.error('[Recording] 重连失败，无法发送停止命令');
            }
          }, 2000);
        } else {
          console.log('[Recording] 已发送录音停止命令:', stopCommand);
        }
        
        // 不再设置旧的超时逻辑，因为后端现在会立即发送recording_completed消息
      } else {
        console.warn('[Recording] WebSocket未连接，无法发送停止命令');
        console.warn('[Recording] 尝试重连WebSocket...');
        
        // 尝试重连
        reconnectWS();
        alert('录音停止失败：WebSocket连接断开\n\n正在尝试重连，请稍后重试');
      }
      
      recordingState = 'stopped';
      audioRecorderConnected = false;
      
      // 停止WebSocket监控
      stopRecordingMonitor();
      
      updateRecordingUI();
      updateRecordDisplay(); // 更新显示状态
      
      // 计算录音时长（简化版 - 移除暂停时间计算）
      const totalDuration = new Date().getTime() - recordingStartTime;
      
      console.log('[Recording] 录音统计:');
      console.log('  录音时长:', totalDuration, 'ms');
      
      // 立即显示导出对话框，提升用户体验
      console.log('[Recording] 立即显示导出对话框，音频文件已保存');
      exportDialogShown = true; // 标记对话框已显示，防止后端响应重复弹窗
      showExportOptionsWithProgress(totalDuration / 1000);
      
      // 移除原有的后备超时机制，因为现在立即显示对话框
      // 保留一个简短的超时来处理真正的网络问题
      const fallbackTimeoutId = setTimeout(() => {
        console.warn('[Recording] 30秒内未收到后端响应，可能存在网络问题');
        // 由于文件是实时保存的，不需要显示失败状态
      }, 30000);
      
      // 保存后备超时ID用于在收到消息时清除
      window.fallbackTimeoutId = fallbackTimeoutId;
      
    } catch (error) {
      console.error('[Recording] 停止录音失败:', error);
      alert(`停止录音失败: ${error.message}`);
    }
  }
  
  // 新增：独立API版本的停止录音
  async function stopRecordingIndependent() {
    if (!currentSessionId) {
      console.log('[Recording] 没有活跃的录音会话');
      return;
    }
    
    try {
      console.log('[Recording] 使用独立API停止录音:', currentSessionId);
      
      // 调用独立录音API停止
      const response = await fetch('http://127.0.0.1:27000/api/recording/stop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: currentSessionId
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        console.log('[Recording] 独立录音停止成功:', result);
        
        // 显示结果并提供下载
        const message = `录音完成！\n\n音频文件: ${result.audio_file}\n字幕文件: ${result.subtitle_file}\n录音时长: ${result.duration.toFixed(1)}s\n同步质量: ${result.sync_quality.accuracy}`;
        alert(message);
        
        // 自动下载文件
        if (result.download_urls) {
          // 使用 fetch + 下载链接的方式，避免弹出空白窗口
          try {
            // 下载音频文件
            const audioResponse = await fetch(`http://127.0.0.1:27000${result.download_urls.audio}`);
            const audioBlob = await audioResponse.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audioLink = document.createElement('a');
            audioLink.href = audioUrl;
            audioLink.download = result.audio_file;
            document.body.appendChild(audioLink);
            audioLink.click();
            document.body.removeChild(audioLink);
            URL.revokeObjectURL(audioUrl);
            
            // 下载字幕文件
            const subtitleResponse = await fetch(`http://127.0.0.1:27000${result.download_urls.subtitle}`);
            const subtitleBlob = await subtitleResponse.blob();
            const subtitleUrl = URL.createObjectURL(subtitleBlob);
            const subtitleLink = document.createElement('a');
            subtitleLink.href = subtitleUrl;
            subtitleLink.download = result.subtitle_file;
            document.body.appendChild(subtitleLink);
            subtitleLink.click();
            document.body.removeChild(subtitleLink);
            URL.revokeObjectURL(subtitleUrl);
            
            console.log('[Recording] 文件下载完成');
          } catch (downloadError) {
            console.error('[Recording] 下载文件失败:', downloadError);
            alert('文件下载失败，请检查网络连接');
          }
        }
        
        // 重置前端状态 - 这里是关键！
        console.log('[Recording] 开始重置前端录音状态...');
        recordingState = 'idle';
        recordingStartTime = null;
        recordStartTime = null;
        recordingConfirmed = false;
        audioRecorderConnected = false;
        currentRecordingFile = null;
        currentSessionId = null;
        
        // 停止WebSocket监控
        stopRecordingMonitor();
        
        // 清空字幕记录
        recordHistory = [];
        
        // 如果在记录模式下，更新记录显示
        if (recordMode) {
          updateRecordDisplay();
        } else {
          // 如果不在记录模式，清空常规字幕显示
          history = [];
          renderSubtitles();
        }
        
        // 更新录音UI状态
        updateRecordingUI();
        
        console.log('[Recording] 前端录音状态已完全重置');
        
      } else {
        throw new Error(result.error || '停止录音失败');
      }
      
    } catch (error) {
      console.error('[Recording] 独立API停止录音失败:', error);
      alert(`停止录音失败: ${error.message}`);
    }
  }
  
  // 优化版导出选项对话框 - 录音完成后立即显示，文件已准备就绪
  function showExportOptionsWithProgress(duration) {
    console.log('[Export] 显示导出选项, duration:', duration);
    console.log('[Export] 音频缓存状态:', {
      hasBlob: !!window.lastAudioBlob,
      hasFilename: !!window.lastDownloadedAudioFile,
      filename: window.lastDownloadedAudioFile
    });
    
    // 移除可能存在的旧对话框，防止重复
    const existingDialog = document.getElementById('export-options-dialog');
    if (existingDialog) {
      document.body.removeChild(existingDialog);
      console.log('[Export] 移除了已存在的导出对话框');
    }
    
    // 创建导出对话框
    const dialog = document.createElement('div');
    dialog.id = 'export-options-dialog';
    dialog.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: #2a2a2a;
      color: white;
      padding: 30px;
      border-radius: 12px;
      border: 1px solid #444;
      box-shadow: 0 8px 32px rgba(0,0,0,0.7);
      z-index: 10000;
      text-align: center;
      min-width: 450px;
      max-width: 550px;
    `;
    
    dialog.innerHTML = `
      <div style="text-align: center; margin-bottom: 24px;">
        <div style="width: 48px; height: 48px; background: #4CAF50; border-radius: 50%; margin: 0 auto 16px auto; display: flex; align-items: center; justify-content: center;">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M9 12l2 2 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h2 style="margin: 0 0 8px 0; color: #ffffff; font-size: 20px; font-weight: 600;">录音完成</h2>
        <p style="margin: 0; color: #888; font-size: 14px;">录音和字幕已成功保存</p>
      </div>
      
      <div style="background: #333; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 8px 0; border-bottom: 1px solid #444;">
          <div>
            <span style="color: #ccc; font-size: 14px;">字幕条数</span>
            <span style="color: #fff; font-weight: 500; margin-left: 8px;">${recordHistory.length}条</span>
          </div>
          <button id="export-subtitles-btn" style="
            background: #4CAF50;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.2s ease;
          ">导出</button>
        </div>
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 8px 0; border-bottom: 1px solid #444;">
          <div>
            <span style="color: #ccc; font-size: 14px;">录音文件</span>
            <span style="color: #4CAF50; font-weight: 500; margin-left: 8px;">已保存</span>
          </div>
          <button id="export-audio-btn" style="
            background: #2196F3;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.2s ease;
          " title="打开录音文件夹">打开文件夹</button>
        </div>
        
        ${duration > 0 ? `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
          <div>
            <span style="color: #ccc; font-size: 14px;">录音时长</span>
            <span style="color: #fff; font-weight: 500; margin-left: 8px;">${duration.toFixed(1)}秒</span>
          </div>
        </div>` : ''}
      </div>
      
      <div style="display: flex; justify-content: center;">
        <button id="skip-export-btn" style="
          background: transparent;
          color: #ccc;
          border: 1px solid #555;
          padding: 12px 24px;
          border-radius: 8px;
          cursor: pointer;
          font-size: 14px;
          font-weight: 500;
          transition: all 0.2s ease;
        ">结束</button>
      </div>
    `;
    
    document.body.appendChild(dialog);
    
    // 绑定按钮事件
    const exportSubtitlesBtn = document.getElementById('export-subtitles-btn');
    const exportAudioBtn = document.getElementById('export-audio-btn');
    const skipBtn = document.getElementById('skip-export-btn');
    
    // 添加按钮悬停效果
    exportSubtitlesBtn.addEventListener('mouseenter', () => {
      exportSubtitlesBtn.style.background = '#45a049';
      exportSubtitlesBtn.style.transform = 'translateY(-1px)';
    });
    exportSubtitlesBtn.addEventListener('mouseleave', () => {
      exportSubtitlesBtn.style.background = '#4CAF50';
      exportSubtitlesBtn.style.transform = 'translateY(0)';
    });
    
    exportAudioBtn.addEventListener('mouseenter', () => {
      exportAudioBtn.style.background = '#1976D2';
      exportAudioBtn.style.transform = 'translateY(-1px)';
    });
    exportAudioBtn.addEventListener('mouseleave', () => {
      exportAudioBtn.style.background = '#2196F3';
      exportAudioBtn.style.transform = 'translateY(0)';
    });
    
    skipBtn.addEventListener('mouseenter', () => {
      skipBtn.style.borderColor = '#777';
      skipBtn.style.color = '#fff';
      skipBtn.style.transform = 'translateY(-1px)';
    });
    skipBtn.addEventListener('mouseleave', () => {
      skipBtn.style.borderColor = '#555';
      skipBtn.style.color = '#ccc';
      skipBtn.style.transform = 'translateY(0)';
    });
    
    const cleanup = () => {
      if (document.body.contains(dialog)) {
        document.body.removeChild(dialog);
      }
      exportDialogShown = false; // 重置状态，允许后续显示其他对话框
      resetRecordingStateAndRefreshSubtitles();
      
      // 如果有待处理的模式切换，执行切换
      if (pendingModeSwitch) {
        console.log('[Export] 检测到待处理的模式切换，执行模式切换');
        performModeSwitch();
      }
    };
    
    exportSubtitlesBtn.addEventListener('click', () => {
      console.log('[Export] 用户选择导出字幕');
      exportRecordingData();
    });
    
    exportAudioBtn.addEventListener('click', () => {
      console.log('[Export] 用户点击打开录音文件夹按钮');
      openRecordingFolder();
    });
    
    skipBtn.addEventListener('click', () => {
      console.log('[Export] 用户选择跳过导出');
      cleanup();
    });
    
    // 添加键盘支持
    const handleKeyPress = (e) => {
      if (e.key === 'Enter') {
        exportSubtitlesBtn.click();
      } else if (e.key === 'Escape') {
        skipBtn.click();
      }
    };
    
    document.addEventListener('keydown', handleKeyPress);
    
    // 增强清理函数
    const originalCleanup = cleanup;
    window.exportDialogCleanup = () => {
      document.removeEventListener('keydown', handleKeyPress);
      originalCleanup();
    };
  }
  
  
  function showExportOptions(duration, audioAvailable = false) {
    console.log('[Export] 显示导出选项, duration:', duration, 'audioAvailable:', audioAvailable);
    console.log('[Export] 音频缓存状态:', {
      hasBlob: !!window.lastAudioBlob,
      hasFilename: !!window.lastDownloadedAudioFile,
      filename: window.lastDownloadedAudioFile
    });
    
    // 移除可能存在的旧对话框，防止重复
    const existingDialog = document.getElementById('export-options-dialog');
    if (existingDialog) {
      document.body.removeChild(existingDialog);
      console.log('[Export] 移除了已存在的导出对话框');
    }
    
    // 创建一个更友好的导出对话框
    const dialog = document.createElement('div');
    dialog.id = 'export-options-dialog';
    dialog.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: #2a2a2a;
      color: white;
      padding: 30px;
      border-radius: 12px;
      border: 1px solid #444;
      box-shadow: 0 8px 32px rgba(0,0,0,0.7);
      z-index: 10000;
      text-align: center;
      min-width: 450px;
      max-width: 550px;
    `;
    
    const audioDownloadedText = window.lastDownloadedAudioFile ? 
      `<p style="color: #4CAF50;">✅ 音频文件已下载: ${window.lastDownloadedAudioFile}</p>` : '';
    
    dialog.innerHTML = `
      <div style="text-align: center; margin-bottom: 24px;">
        <div style="width: 48px; height: 48px; background: #4CAF50; border-radius: 50%; margin: 0 auto 16px auto; display: flex; align-items: center; justify-content: center;">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M9 12l2 2 4-4" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h2 style="margin: 0 0 8px 0; color: #ffffff; font-size: 20px; font-weight: 600;">录音完成</h2>
        <p style="margin: 0; color: #888; font-size: 14px;">录音和字幕已成功保存</p>
      </div>
      
      <div style="background: #333; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 8px 0; border-bottom: 1px solid #444;">
          <div>
            <span style="color: #ccc; font-size: 14px;">字幕条数</span>
            <span style="color: #fff; font-weight: 500; margin-left: 8px;">${recordHistory.length}条</span>
          </div>
          <button id="export-subtitles-btn" style="
            background: #4CAF50;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 500;
            transition: all 0.2s ease;
          ">导出</button>
        </div>
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding: 8px 0; border-bottom: 1px solid #444;">
          <div>
            <span style="color: #ccc; font-size: 14px;">录音文件</span>
            <span style="color: ${audioAvailable ? '#4CAF50' : '#ff6b6b'}; font-weight: 500; margin-left: 8px;">${audioAvailable ? '已保存' : '不可用'}</span>
          </div>
          <button id="export-audio-btn" style="
            background: ${audioAvailable ? '#2196F3' : '#666'};
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: ${audioAvailable ? 'pointer' : 'not-allowed'};
            font-size: 12px;
            font-weight: 500;
            transition: all 0.2s ease;
            opacity: ${audioAvailable ? '1' : '0.6'};
          " ${audioAvailable ? '' : 'disabled'} title="${audioAvailable ? (window.isDualStreamRecording ? '打开录音文件夹' : '导出音频文件') : '音频文件不可用'}">${window.isDualStreamRecording ? '打开文件夹' : '导出音频'}</button>
        </div>
        
        ${duration > 0 ? `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
          <div>
            <span style="color: #ccc; font-size: 14px;">录音时长</span>
            <span style="color: #fff; font-weight: 500; margin-left: 8px;">${duration.toFixed(1)}秒</span>
          </div>
        </div>` : ''}
      </div>
      
      <div style="display: flex; justify-content: center;">
        <button id="skip-export-btn" style="
          background: transparent;
          color: #ccc;
          border: 1px solid #555;
          padding: 12px 24px;
          border-radius: 8px;
          cursor: pointer;
          font-size: 14px;
          font-weight: 500;
          transition: all 0.2s ease;
        ">结束</button>
      </div>
    `;
    
    document.body.appendChild(dialog);
    
    // 绑定按钮事件
    const exportSubtitlesBtn = document.getElementById('export-subtitles-btn');
    const exportAudioBtn = document.getElementById('export-audio-btn');
    const skipBtn = document.getElementById('skip-export-btn');
    
    // 添加按钮悬停效果
    exportSubtitlesBtn.addEventListener('mouseenter', () => {
      exportSubtitlesBtn.style.background = '#45a049';
      exportSubtitlesBtn.style.transform = 'translateY(-1px)';
    });
    exportSubtitlesBtn.addEventListener('mouseleave', () => {
      exportSubtitlesBtn.style.background = '#4CAF50';
      exportSubtitlesBtn.style.transform = 'translateY(0)';
    });
    
    // 音频按钮悬停效果（仅在可用时）
    if (!exportAudioBtn.disabled) {
      exportAudioBtn.addEventListener('mouseenter', () => {
        exportAudioBtn.style.background = '#1976D2';
        exportAudioBtn.style.transform = 'translateY(-1px)';
      });
      exportAudioBtn.addEventListener('mouseleave', () => {
        exportAudioBtn.style.background = '#2196F3';
        exportAudioBtn.style.transform = 'translateY(0)';
      });
    }
    
    skipBtn.addEventListener('mouseenter', () => {
      skipBtn.style.borderColor = '#777';
      skipBtn.style.color = '#fff';
      skipBtn.style.transform = 'translateY(-1px)';
    });
    skipBtn.addEventListener('mouseleave', () => {
      skipBtn.style.borderColor = '#555';
      skipBtn.style.color = '#ccc';
      skipBtn.style.transform = 'translateY(0)';
    });
    
    const cleanup = () => {
      if (document.body.contains(dialog)) {
        document.body.removeChild(dialog);
      }
      exportDialogShown = false; // 重置状态，允许后续显示其他对话框
      
      // 清理完毕后重置录音状态并刷新字幕显示
      resetRecordingStateAndRefreshSubtitles();
      
      // 如果有待处理的模式切换，执行切换
      if (pendingModeSwitch) {
        console.log('[Export] 检测到待处理的模式切换，执行模式切换');
        performModeSwitch();
      }
    };
    
    exportSubtitlesBtn.addEventListener('click', () => {
      console.log('[Export] 用户选择导出字幕');
      exportRecordingData();
      // 不关闭对话框，让用户可以继续导出音频
    });
    
    exportAudioBtn.addEventListener('click', () => {
      console.log('[Export] 用户点击导出音频按钮, audioAvailable:', audioAvailable);
      if (audioAvailable) {
        console.log('[Export] 音频可用，执行导出');
        // 对于双流架构，直接打开录音文件夹
        if (window.isDualStreamRecording) {
          console.log('[Export] 双流架构录音，打开录音文件夹');
          openRecordingFolder();
        } else {
          // 传统的WebSocket音频数据导出
          exportAudioFile();
        }
        // 不关闭对话框，让用户可以继续导出字幕
      } else {
        console.log('[Export] 音频不可用，显示提示');
        alert('音频文件不可用\n\n可能的原因：\n- 录音数据未正确保存\n- 网络连接在录音过程中中断\n- 后端音频处理异常\n\n建议：重新录音以获得完整的音频文件');
      }
    });
    
    skipBtn.addEventListener('click', () => {
      console.log('[Export] 用户选择跳过导出');
      cleanup();
    });
    
    // 添加键盘支持
    const handleKeyPress = (e) => {
      if (e.key === 'Enter') {
        exportSubtitlesBtn.click();
      } else if (e.key === 'Escape') {
        skipBtn.click();
      }
    };
    
    document.addEventListener('keydown', handleKeyPress);
    
    // 清理函数中也要移除键盘监听
    const originalCleanup = cleanup;
    const enhancedCleanup = () => {
      document.removeEventListener('keydown', handleKeyPress);
      originalCleanup();
    };
    
    // 移除重复的onclick绑定，只使用addEventListener
    exportSubtitlesBtn.onclick = null;
    exportAudioBtn.onclick = null;
    skipBtn.onclick = null;
  }
  
  // 导出音频文件
  function exportAudioFile() {
    try {
      console.log('[Export] 导出音频文件请求，检查音频状态:', {
        hasBlob: !!window.lastAudioBlob,
        hasFilename: !!window.lastDownloadedAudioFile,
        filename: window.lastDownloadedAudioFile,
        sessionId: currentSessionId
      });
      
      if (window.lastAudioBlob && window.lastDownloadedAudioFile) {
        // 情况1：有缓存的音频数据，直接下载
        console.log('[Export] 使用缓存音频数据下载');
        const url = URL.createObjectURL(window.lastAudioBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = window.lastDownloadedAudioFile;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        
        console.log('[Export] 音频文件重新下载成功:', window.lastDownloadedAudioFile);
        
        // 显示成功提示
        showAudioExportSuccess(window.lastDownloadedAudioFile);
        
      } else if (currentSessionId || recordHistory.length > 0) {
        // 情况2：没有缓存但有录音数据，尝试从服务器获取或提供指导
        console.log('[Export] 音频文件未缓存，提供用户指导');
        
        // 尝试生成一个预估的文件名
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
        const estimatedFilename = `recording-${timestamp}.wav`;
        
        const message = `音频文件导出说明\n\n` +
          `❌ 音频文件未在前端缓存\n` +
          `✅ 音频文件可能已保存到服务器端\n\n` +
          `📁 服务器保存路径:\n` +
          `   - a4s/recordings/ （主要路径）\n` +
          `   - python/recordings/ （备用路径）\n\n` +
          `📝 文件名格式: recording-时间戳.wav\n` +
          `📝 预估文件名: ${estimatedFilename}\n\n` +
          `💡 解决方案:\n` +
          `   1. 检查项目根目录下的 a4s/recordings/ 或 python/recordings/ 目录\n` +
          `   2. 查找匹配当前时间的 .wav 文件\n` +
          `   3. 确保录音过程中网络连接稳定\n` +
          `   4. 下次录音时立即点击音频下载按钮\n\n` +
          `🔍 提示：录音文件已保存，请检查上述目录`;
        
        alert(message);
        
      } else {
        console.log('[Export] 没有任何音频数据可导出');
        alert('音频文件不可用\n\n❌ 音频数据未缓存\n❌ 无录音会话信息\n❌ 无录音历史记录\n\n💡 建议：重新开始录音');
      }
    } catch (error) {
      console.error('[Export] 导出音频文件失败:', error);
      alert('导出音频文件失败: ' + error.message);
    }
  }
  
  // 打开录音文件夹
  async function openRecordingFolder() {
    try {
      console.log('[Export] 打开录音文件夹...');
      const result = await window.subtitleAPI.openRecordingFolder();
      
      if (result.success) {
        console.log('[Export] 录音文件夹已打开:', result.path);
        
        // 显示成功提示
        const successMessage = document.createElement('div');
        successMessage.style.cssText = `
          position: fixed;
          top: 80px;
          right: 20px;
          background: #2196F3;
          color: white;
          padding: 15px 20px;
          border-radius: 5px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.3);
          z-index: 10001;
          font-size: 14px;
          max-width: 300px;
        `;
        successMessage.innerHTML = `已打开录音文件夹<br><small>${result.path}</small>`;
        document.body.appendChild(successMessage);
        
        // 3秒后自动移除提示
        setTimeout(() => {
          if (document.body.contains(successMessage)) {
            document.body.removeChild(successMessage);
          }
        }, 3000);
        
      } else {
        console.error('[Export] 打开录音文件夹失败:', result.error);
        alert(`打开录音文件夹失败: ${result.error}`);
      }
    } catch (error) {
      console.error('[Export] 打开录音文件夹异常:', error);
      alert('打开录音文件夹失败: ' + error.message);
    }
  }
  
  // 显示音频导出成功提示
  function showAudioExportSuccess(filename) {
    const successMessage = document.createElement('div');
    successMessage.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      background: #2196F3;
      color: white;
      padding: 15px 20px;
      border-radius: 5px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      z-index: 10001;
      font-size: 14px;
    `;
    successMessage.textContent = `音频文件已导出: ${filename}`;
    document.body.appendChild(successMessage);
    
    // 3秒后自动移除提示
    setTimeout(() => {
      if (document.body.contains(successMessage)) {
        document.body.removeChild(successMessage);
      }
    }, 3000);
  }
  
  // 新增：重置录音状态并刷新字幕的函数
  function resetRecordingStateAndRefreshSubtitles() {
    console.log('[Recording] 开始重置录音状态并刷新字幕...');
    recordingState = 'idle';
    recordingStartTime = null;
    recordStartTime = null;
    recordingConfirmed = false;
    
    // 停止WebSocket监控
    stopRecordingMonitor();
    
    // 清理所有可能的超时和对话框
    if (window.fallbackTimeoutId) {
      clearTimeout(window.fallbackTimeoutId);
      window.fallbackTimeoutId = null;
    }
    if (window.downloadPrepareTimeoutId) {
      clearTimeout(window.downloadPrepareTimeoutId);
      window.downloadPrepareTimeoutId = null;
    }
    const prepareDialog = document.getElementById('prepare-download-dialog');
    if (prepareDialog) {
      document.body.removeChild(prepareDialog);
    }
    
    // 注意：不在这里重置 exportDialogShown，让对话框的关闭来管理状态
    
    // 清空字幕记录
    recordHistory = [];
    updateRecordDisplay();
    
    // 清理音频录制器资源
    audioRecorderConnected = false;
    currentRecordingFile = null;
    currentSessionId = null; // 重置session ID，确保下次录音生成新的ID
    
    // 不清理音频缓存，让用户可以重复导出音频
    // if (window.lastAudioBlob) {
    //   window.lastAudioBlob = null;
    // }
    // if (window.lastDownloadedAudioFile) {
    //   window.lastDownloadedAudioFile = null;
    // }
    
    updateRecordingUI();
    
    // 重要：强制刷新字幕显示，无论当前模式如何
    console.log('[Recording] 录音结束，强制刷新字幕显示');
    console.log('[Recording] 当前模式:', recordMode ? '记录模式' : '字幕模式');
    console.log('[Recording] 历史记录数量:', history.length);
    
    if (!recordMode) {
      // 如果不在记录模式，强制刷新字幕显示
      if (subtitleContainer) {
        let subtitlesContainer = subtitleContainer.querySelector('.subtitles-container');
        if (!subtitlesContainer) {
          // 如果没有subtitles-container，创建一个
          subtitlesContainer = document.createElement('div');
          subtitlesContainer.className = 'subtitles-container';
          subtitleContainer.innerHTML = '';
          subtitleContainer.appendChild(subtitlesContainer);
          console.log('[Recording] 重建字幕容器结构');
        }
        
        // 重置字幕高度和样式
        subtitleHeight = 0;
        subtitlesContainer.style.transform = 'translateY(0)';
        
        // 先清空容器内容，再重新渲染
        subtitlesContainer.innerHTML = '';
        
        // 延迟渲染确保DOM更新完成
        setTimeout(() => {
          console.log('[Recording] 强制调用 renderSubtitles()，状态已重置为idle');
          renderSubtitles();
          console.log('[Recording] 字幕显示已强制刷新');
        }, 100);
      }
    }
    
    console.log('[Recording] 录音状态已完全重置，字幕显示已刷新，可以立即开始新录音');
  }
  
  // 保持向后兼容的重置函数
  function resetRecordingState() {
    resetRecordingStateAndRefreshSubtitles();
  }
  
  // 导出录音数据
  async function exportRecordingData() {
    try {
      console.log('[Export] 开始导出字幕，当前recordHistory长度:', recordHistory.length);
      console.log('[Export] recordHistory内容:', recordHistory);
      
      if (recordHistory.length === 0) {
        console.warn('[Export] recordHistory为空，检查是否需要使用history');
        // 如果recordHistory为空，尝试使用常规字幕历史
        if (history && history.length > 0) {
          console.log('[Export] 使用常规字幕历史导出，长度:', history.length);
          exportRegularSubtitles();
          return;
        } else {
          alert('没有字幕记录可导出');
          return;
        }
      }
      
      // 生成字幕文本
      let subtitleText = `字幕记录 - ${new Date().toLocaleString()}\n`;
      subtitleText += `总计 ${recordHistory.length} 条记录\n`;
      subtitleText += '='.repeat(50) + '\n\n';
      
      recordHistory.forEach((item, index) => {
        subtitleText += `[${item.timestamp}] ${item.original}\n`;
        if (item.translated && item.translated.trim()) {
          subtitleText += `翻译: ${item.translated}\n`;
        }
        subtitleText += '\n';
      });
      
      // 创建下载链接
      const blob = new Blob([subtitleText], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `subtitles_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      console.log('[Export] 字幕文本已导出');
      
      // 显示成功提示
      const successMessage = document.createElement('div');
      successMessage.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4CAF50;
        color: white;
        padding: 15px 20px;
        border-radius: 5px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        z-index: 10001;
        font-size: 14px;
      `;
      successMessage.textContent = `字幕文件已导出: ${recordHistory.length}条记录`;
      document.body.appendChild(successMessage);
      
      // 3秒后自动移除提示
      setTimeout(() => {
        if (document.body.contains(successMessage)) {
          document.body.removeChild(successMessage);
        }
      }, 3000);
      
    } catch (error) {
      console.error('[Export] 导出失败:', error);
      alert('导出失败: ' + error.message);
    }
  }
  
  // 新增：导出常规字幕历史
  function exportRegularSubtitles() {
    try {
      let subtitleText = `字幕记录 - ${new Date().toLocaleString()}\n`;
      subtitleText += `总计 ${history.length} 条记录\n`;
      subtitleText += '='.repeat(50) + '\n\n';
      
      history.forEach((item, index) => {
        subtitleText += `[${index + 1}] ${item.text}\n`;
        if (item.translated && item.translated.trim() && translationEnabled) {
          subtitleText += `翻译: ${item.translated}\n`;
        }
        subtitleText += '\n';
      });
      
      // 创建下载链接
      const blob = new Blob([subtitleText], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `subtitles_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5)}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      console.log('[Export] 常规字幕已导出');
      
      // 显示成功提示
      const successMessage = document.createElement('div');
      successMessage.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #4CAF50;
        color: white;
        padding: 15px 20px;
        border-radius: 5px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        z-index: 10001;
        font-size: 14px;
      `;
      successMessage.textContent = `字幕文件已导出: ${history.length}条记录`;
      document.body.appendChild(successMessage);
      
      // 3秒后自动移除提示
      setTimeout(() => {
        if (document.body.contains(successMessage)) {
          document.body.removeChild(successMessage);
        }
      }, 3000);
      
    } catch (error) {
      console.error('[Export] 常规字幕导出失败:', error);
      alert('导出失败: ' + error.message);
    }
  }

  function addToRecord(originalText, translatedText, backendTimestamp) {
    if (!recordMode) return;
    
    // 关键检查：只有在录音确认后才处理字幕记录
    if (!recordingConfirmed || !currentSessionId || recordingState !== 'recording') {
      console.log('[Record] 跳过字幕记录 - 录音状态不符合:', {
        recordingConfirmed,
        currentSessionId,
        recordingState
      });
      return;
    }
    
    console.log('[Record] addToRecord 被调用:', originalText);
    console.log('[Record] 当前录音状态:', recordingState);
    console.log('[Record] recordingStartTime:', recordingStartTime);
    console.log('[Record] backendTimestamp:', backendTimestamp);
    
    let displayTimestamp = '00:00:00';
    let effectiveRecordingTime = 0;
    
    // 优先使用后端提供的精确音频同步时间戳
    if (backendTimestamp && typeof backendTimestamp === 'object') {
      if (backendTimestamp.recording_relative_time !== undefined) {
        // 使用后端计算的精确录音相对时间（基于音频数据）
        effectiveRecordingTime = backendTimestamp.recording_relative_time * 1000; // 转换为毫秒
        console.log('[Record] 使用后端精确音频时间戳:', backendTimestamp.recording_relative_time, '秒');
      } else if (backendTimestamp.audio_chunk_offset !== undefined && backendTimestamp.recording_start_time !== undefined) {
        // 使用音频块偏移计算精确时间
        const audioSyncTime = backendTimestamp.audio_sync_time || backendTimestamp.timestamp;
        const recordingStartTime = backendTimestamp.recording_start_time;
        effectiveRecordingTime = (audioSyncTime - recordingStartTime + backendTimestamp.audio_chunk_offset) * 1000;
        console.log('[Record] 使用音频块偏移计算时间戳:', {
          audioSyncTime,
          recordingStartTime, 
          offset: backendTimestamp.audio_chunk_offset,
          result: effectiveRecordingTime / 1000
        });
      } else {
        // 回退到前端计算
        effectiveRecordingTime = calculateFrontendTimestamp();
        console.log('[Record] 回退到前端时间戳计算:', effectiveRecordingTime / 1000, '秒');
      }
    } else {
      // 回退到前端计算的时间戳
      effectiveRecordingTime = calculateFrontendTimestamp();
      console.log('[Record] 使用前端时间戳计算:', effectiveRecordingTime / 1000, '秒');
    }
    
    function calculateFrontendTimestamp() {
      console.log('[Record] ========== 前端时间戳计算（简化版 - 无暂停功能）==========');
      console.log('[Record] 计算参数:', {
        recordingStartTime,
        recordingState,
        currentTime: new Date().getTime()
      });
      
      const currentTime = new Date().getTime();
      
      // 如果还没有开始录音，直接使用0作为时间戳
      if (!recordingStartTime) {
        console.log('[Record] 录音尚未开始，使用时间戳0');
        return 0;
      }
      
      // 计算从开始到现在的总时长
      const totalElapsed = currentTime - recordingStartTime;
      
      // 简化版：直接返回总时长，不考虑暂停时间
      const result = Math.max(0, totalElapsed);
      
      console.log('[Record] 前端时间计算详情:');
      console.log('  - 录音开始时间:', new Date(recordingStartTime).toLocaleTimeString());
      console.log('  - 录音时长:', totalElapsed, 'ms =', (totalElapsed/1000).toFixed(1), '秒');
      console.log('  - 有效录音时长:', result, 'ms =', (result/1000).toFixed(1), '秒');
      console.log('[Record] ========== 前端时间戳计算结束 ==========');
      
      return result;
    }
    
    // 关键检查：如果计算出的时间戳为0或负数，跳过这个字幕
    if (effectiveRecordingTime <= 0) {
      console.log('[Record] 跳过字幕记录 - 时间戳无效:', effectiveRecordingTime);
      return;
    }
    
    // 转换为时分秒格式
    const totalSeconds = Math.floor(effectiveRecordingTime / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    
    displayTimestamp = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
    
    const recordItem = {
      original: originalText,
      translated: translatedText,
      timestamp: displayTimestamp,
      backendTimestamp: backendTimestamp,
      absoluteTimestamp: new Date().getTime(),
      effectiveRecordingTime: effectiveRecordingTime, // 保存有效录音时间用于调试
      timestampSource: backendTimestamp?.recording_relative_time !== undefined ? 'backend_audio_data' : 
                      backendTimestamp?.audio_chunk_offset !== undefined ? 'backend_audio_offset' : 'frontend_calculation',
      audioSyncData: {  // 保存音频同步相关数据
        audioChunkOffset: backendTimestamp?.audio_chunk_offset,
        audioSyncTime: backendTimestamp?.audio_sync_time,
        recordingRelativeTime: backendTimestamp?.recording_relative_time,
        audioDuration: backendTimestamp?.audio_duration  // 新增：音频数据时长
      },
      recordingSession: currentSessionId,  // 新增：关联录音会话
      isValidTimestamp: effectiveRecordingTime > 0  // 新增：时间戳有效性标记
    };
    
    recordHistory.push(recordItem);
    
    console.log('[Record] 已添加记录:', {
      text: originalText.substring(0, 20) + '...',
      timestamp: displayTimestamp,
      timestampSource: recordItem.timestampSource,
      effectiveTime: (effectiveRecordingTime / 1000).toFixed(3) + 's',
      historyLength: recordHistory.length,
      sessionId: currentSessionId,
      syncData: recordItem.audioSyncData
    });
    
    updateRecordDisplay();
  }
  
  function updateRecordDisplay() {
    const recordContent = document.getElementById('record-content');
    if (!recordContent) return;
    
    if (recordHistory.length === 0) {
      // 根据录音状态显示不同的提示
      if (recordingState === 'idle') {
        recordContent.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">点击录音按钮开始录音和字幕记录</div>';
      } else if (recordingState === 'recording') {
        recordContent.innerHTML = '<div style="text-align: center; color: #4CAF50; padding: 40px;">🔴 录音中，等待字幕...</div>';
      } else {
        recordContent.innerHTML = '<div style="text-align: center; color: #888; padding: 40px;">暂无记录</div>';
      }
      return;
    }
    
    recordContent.innerHTML = '';
    
    recordHistory.forEach((item, index) => {
      const recordItem = document.createElement('div');
      recordItem.className = 'record-item';
      recordItem.dataset.index = index;
      
      let content = `
        <div class="record-meta">
          <span class="timestamp">${item.timestamp}</span>
        </div>
        <div class="original" data-field="original" data-index="${index}">
          ${sanitizeText(item.original)}
        </div>`;
      
      if (item.translated && item.translated.trim() && translationEnabled) {
        content += `<div class="translation" data-field="translated" data-index="${index}">
          ${sanitizeText(item.translated)}
        </div>`;
      }
      
      recordItem.innerHTML = content;
      recordContent.appendChild(recordItem);
    });
  }

  function sanitizeText(text) {
    if (typeof text !== 'string') return '';
    return text.trim();
  }

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
    
    // 确保字幕容器结构正确
    let subtitlesContainer = subtitleContainer.querySelector('.subtitles-container');
    if (!subtitlesContainer) {
      // 创建字幕容器结构
      subtitlesContainer = document.createElement('div');
      subtitlesContainer.className = 'subtitles-container';
      subtitleContainer.innerHTML = '';
      subtitleContainer.appendChild(subtitlesContainer);
      console.log('[Startup] 创建字幕容器结构');
    } else {
      // 清空现有内容
      subtitlesContainer.innerHTML = '';
    }
    
    // 设置初始内容
    subtitlesContainer.innerHTML = '<div class="pair"><div class="info">等待字幕中...</div></div>';
    console.log('[Startup] 字幕界面已初始化');
  }

  if (window.subtitleAPI) {
    // 立即退出启动模式并连接WebSocket
    finishStartup();
    connectToSubtitleWS(currentTargetLang);
    
    // 确保字幕显示正确
    setTimeout(() => {
      renderSubtitles();
    }, 100);
  } else {
    subtitleContainer.innerText = 'window.subtitleAPI 未注入，preload.js 可能未生效';
  }

  let subtitleHeight = 0; // 追踪字幕总高度

  function renderSubtitles() {
    if (!subtitleContainer || isStartupMode) return;
    
    const subtitlesContainer = subtitleContainer.querySelector('.subtitles-container');
    if (!subtitlesContainer) return;
    
    if (history.length === 0) {
      subtitlesContainer.innerHTML = '<div class="pair"><div class="info">等待字幕中...</div></div>';
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
      let selectedDeviceId;
      
      // 尝试恢复之前选择的设备
      const deviceExists = list.some(dev => dev.index == previouslySelectedDevice);
      if (deviceExists && previouslySelectedDevice) {
        deviceSelect.value = previouslySelectedDevice;
        currentDeviceId = previouslySelectedDevice;
        selectedDeviceId = previouslySelectedDevice;
      } else {
        // 如果之前的设备不存在，才使用第一个设备
        deviceSelect.value = list[0].index;
        currentDeviceId = list[0].index;
        selectedDeviceId = list[0].index;
      }
      
      // 关键修复：自动启动选中设备的音频流
      console.log('[Device] 自动启动音频流，设备ID:', selectedDeviceId);
      if (window.subtitleAPI && window.subtitleAPI.switchDevice) {
        window.subtitleAPI.switchDevice(selectedDeviceId);
        console.log('[Device] 音频流已自动启动');
      } else {
        console.warn('[Device] switchDevice API不可用，无法启动音频流');
      }
    }
  }

  function handleSubtitleData(data) {
    // 如果还在启动模式，忽略字幕数据
    if (isStartupMode) return;
    
    // 调试：记录所有收到的消息
    if (data.recording_completed || data.audio_download_ready || data.audio_download_failed) {
      console.log('[Recording] 收到录音相关消息:', JSON.stringify(data, null, 2));
    }
    
    if (data.device_list) {
      renderDeviceList(data.device_list);
      return;
    }
    
    // 处理录音相关消息
    if (data.recording_started) {
      console.log('[Recording] ========== 收到录音开始确认 ==========');
      console.log('[Recording] 录音开始确认数据:', data);
      recordingConfirmed = true;
      
      // 设置session_id（用于字幕记录关联）
      if (data.session_id) {
        currentSessionId = data.session_id;
        console.log('[Recording] 设置session_id:', currentSessionId);
      }
      
      if (data.start_time) {
        recordingStartTime = data.start_time * 1000; // 转换为毫秒
      }
      console.log('[Recording] 录音已确认开始，更新后状态:', {
        recordingConfirmed,
        recordingStartTime,
        currentSessionId
      });
      return;
    }
    
    // 移除暂停和恢复录音的消息处理 - 简化录音控制
    
    if (data.recording_completed) {
      console.log('[Recording] ========== 收到录音完成通知 ==========');
      console.log('[Recording] 录音完成通知数据:', data);
      
      // 清除后备超时
      if (window.fallbackTimeoutId) {
        clearTimeout(window.fallbackTimeoutId);
        window.fallbackTimeoutId = null;
        console.log('[Recording] 已清除后备超时');
      }
      
      // 清除可能的下载准备超时
      if (window.downloadPrepareTimeoutId) {
        clearTimeout(window.downloadPrepareTimeoutId);
        window.downloadPrepareTimeoutId = null;
        console.log('[Recording] 已清除下载准备超时');
      }
      
      // 移除可能的准备对话框
      const prepareDialog = document.getElementById('prepare-download-dialog');
      if (prepareDialog) {
        document.body.removeChild(prepareDialog);
        console.log('[Recording] 已移除准备下载对话框');
      }
      
      // 检查是否正在准备下载
      if (data.data && data.data.preparing_download) {
        console.log('[Recording] 录音完成，正在准备音频下载...');
        
        // 显示准备下载状态
        const prepareDialog = document.createElement('div');
        prepareDialog.id = 'prepare-download-dialog';
        prepareDialog.style.cssText = `
          position: fixed;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          background: #2a2a2a;
          color: white;
          padding: 20px;
          border-radius: 8px;
          border: 1px solid #444;
          box-shadow: 0 4px 12px rgba(0,0,0,0.5);
          z-index: 10000;
          text-align: center;
          min-width: 300px;
        `;
        prepareDialog.innerHTML = `
          <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 15px;">
            <div style="width: 20px; height: 20px; border: 2px solid #4CAF50; border-top: 2px solid transparent; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 10px;"></div>
            <span style="font-size: 16px; font-weight: 500;">准备音频下载...</span>
          </div>
          <div style="font-size: 14px; color: #ccc;">录音已完成，正在准备高质量音频文件</div>
          <style>
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          </style>
        `;
        document.body.appendChild(prepareDialog);
        
        // 设置下载准备超时（60秒）
        window.downloadPrepareTimeoutId = setTimeout(() => {
          if (document.body.contains(prepareDialog)) {
            document.body.removeChild(prepareDialog);
          }
          console.warn('[Recording] 下载准备超时');
          alert('音频下载准备超时\n\n录音已完成并保存，但下载准备时间过长\n建议：检查网络连接或重启应用');
        }, 60000);
        
        return; // 等待 audio_download_ready 消息
      }
      
      // 原有的处理逻辑（向后兼容）
      console.log('[Recording] 数据结构检查:', {
        hasData: !!data.data,
        hasAudioData: !!(data.data && data.data.audio_data),
        audioDataLength: data.data?.audio_data?.length,
        filename: data.data?.filename,
        quality: data.data?.quality,
        amplitude: data.data?.amplitude,
        dataChunks: data.data?.data_chunks,
        exportDialogShown // 添加对话框状态检查
      });
      
      if (data.data && data.data.audio_data) {
        // 处理音频文件数据
        try {
          console.log('[Recording] 开始处理音频数据，长度:', data.data.audio_data.length);
          
          // 检查音频质量
          const quality = data.data.quality || 'unknown';
          const amplitude = data.data.amplitude || { max: 0, average: 0 };
          
          if (quality === 'silent') {
            console.warn('[Recording] ⚠️ 检测到完全静音录音，可能是音频设备未连接');
          } else if (quality === 'very_quiet') {
            console.warn('[Recording] ⚠️ 检测到非常安静的录音，可能是麦克风音量过低');
          } else {
            console.log('[Recording] ✅ 录音质量正常');
          }
          
          console.log('[Recording] 音频幅度信息:', amplitude);
          
          const audioBytes = new Uint8Array(data.data.audio_data.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
          const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
          
          console.log('[Recording] 音频Blob创建成功，大小:', audioBlob.size, 'bytes');
          
          // 缓存音频数据用于重复导出
          window.lastAudioBlob = audioBlob;
          window.lastDownloadedAudioFile = data.data.filename || `${currentSessionId}.wav`;
          
          // 创建下载链接
          const url = URL.createObjectURL(audioBlob);
          const link = document.createElement('a');
          link.href = url;
          link.download = window.lastDownloadedAudioFile;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
          
          console.log('[Recording] 录音文件已下载:', window.lastDownloadedAudioFile);
          
          // 根据音频质量显示不同的提示
          const successMessage = document.createElement('div');
          let backgroundColor, messageText, displayTime;
          
          switch (quality) {
            case 'silent':
              backgroundColor = '#f44336'; // 红色
              messageText = `⚠️ 录音文件已导出，但检测到完全静音<br><small>文件: ${window.lastDownloadedAudioFile}<br>可能原因：音频设备未连接或被静音</small>`;
              displayTime = 10000;
              break;
            case 'very_quiet':
              backgroundColor = '#FF9800'; // 橙色
              messageText = `⚠️ 录音文件已导出，但音频很安静<br><small>文件: ${window.lastDownloadedAudioFile}<br>建议：检查麦克风音量或环境噪音</small>`;
              displayTime = 8000;
              break;
            default:
              backgroundColor = '#4CAF50'; // 绿色
              messageText = `✅ 录音文件已成功导出: ${window.lastDownloadedAudioFile}`;
              displayTime = 3000;
          }
          
          successMessage.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${backgroundColor};
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            z-index: 10000;
            font-size: 14px;
            max-width: 400px;
            line-height: 1.4;
          `;
          
          successMessage.innerHTML = messageText;
          document.body.appendChild(successMessage);
          
          // 根据质量调整显示时间
          setTimeout(() => {
            if (document.body.contains(successMessage)) {
              document.body.removeChild(successMessage);
            }
          }, displayTime);
          
          // 音频文件下载成功后，立即调用showExportOptions显示字幕导出选项
          if (!exportDialogShown) {
            exportDialogShown = true;
            showExportOptions((data.data.effective_duration || data.data.duration || 0) / 1000, true);
          } else {
            console.log('[Recording] 导出对话框已显示，跳过重复显示');
          }
          
        } catch (error) {
          console.error('[Recording] 处理录音文件失败:', error);
          alert('音频文件下载失败: ' + error.message);
          // 即使音频下载失败，也要给用户导出字幕的机会
          // 检查是否有缓存的音频数据
          const hasAudio = !!(window.lastAudioBlob && window.lastDownloadedAudioFile);
          if (!exportDialogShown) {
            exportDialogShown = true;
            showExportOptions(0, hasAudio);
          } else {
            console.log('[Recording] 导出对话框已显示，跳过重复显示');
          }
        }
      } else {
        console.warn('[Recording] 录音完成但没有通过WebSocket收到音频数据');
        console.warn('[Recording] 完整数据对象:', JSON.stringify(data, null, 2));
        
        // 检查录音是否实际成功完成
        const recordingSuccessful = data.success !== false;
        const hasRecordingFiles = data.data && (
          data.data.files || 
          data.data.filename || 
          data.data.filepath ||
          data.data.dual_stream_files
        );
        
        // 检查是否为双流架构的正常完成（有文件信息但无WebSocket音频数据传输）
        const isDualStreamSuccess = recordingSuccessful && hasRecordingFiles && data.data.dual_stream_files;
        
        if (isDualStreamSuccess) {
          console.log('[Recording] ✅ 双流架构录音成功完成');
          
          // 设置双流架构标志
          window.isDualStreamRecording = true;
          
          // 显示成功提示
          const successMessage = document.createElement('div');
          successMessage.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            z-index: 10000;
            font-size: 14px;
            max-width: 400px;
            line-height: 1.4;
          `;
          
          const files = data.data.dual_stream_files;
          let fileInfo = `<br><small>已生成 ${files.length} 个录音文件</small>`;
          
          successMessage.innerHTML = `✅ 录音已成功完成并保存${fileInfo}`;
          document.body.appendChild(successMessage);
          
          setTimeout(() => {
            if (document.body.contains(successMessage)) {
              document.body.removeChild(successMessage);
            }
          }, 4000);
        }
        
        // 即使没有WebSocket音频数据，也要显示字幕导出选项
        // 检查是否有缓存的音频数据
        const hasAudio = !!(window.lastAudioBlob && window.lastDownloadedAudioFile);
        if (!exportDialogShown) {
          exportDialogShown = true;
          const duration = (data.data?.effective_duration || data.data?.duration || 0) / 1000;
          // 对于双流架构，音频文件已保存到本地，所以audioAvailable应该为true
          const audioAvailable = isDualStreamSuccess || hasAudio;
          showExportOptions(duration, audioAvailable);
        } else {
          console.log('[Recording] 导出对话框已显示，跳过重复显示');
        }
        
        // 只有当录音真正失败时才显示错误消息
        if (data.success === false) {
          alert('录音完成，但音频保存失败: ' + (data.message || '未知错误') + '\n\n字幕数据仍可导出');
        } else if (recordingSuccessful && hasRecordingFiles && !isDualStreamSuccess) {
          // 录音文件已成功保存到磁盘，但没有通过WebSocket传输（可能是单流架构）
          console.log('[Recording] 录音文件已保存到磁盘，使用"打开录音文件夹"功能访问文件');
          // 不显示错误消息，因为录音实际上是成功的
        } else if (!recordingSuccessful && !hasRecordingFiles) {
          // 只有在真正失败的情况下才显示错误
          alert('录音完成，但音频文件状态未知\n\n字幕数据仍可导出');
        }
      }
      return;
    }
    
    // 处理新的音频下载就绪消息
    if (data.audio_download_ready) {
      console.log('[Recording] ========== 收到音频下载就绪通知 ==========');
      console.log('[Recording] 音频下载数据:', data);
      
      // 清除下载准备超时
      if (window.downloadPrepareTimeoutId) {
        clearTimeout(window.downloadPrepareTimeoutId);
        window.downloadPrepareTimeoutId = null;
      }
      
      // 移除准备下载对话框
      const prepareDialog = document.getElementById('prepare-download-dialog');
      if (prepareDialog) {
        document.body.removeChild(prepareDialog);
      }
      
      if (data.data && data.data.audio_data) {
        try {
          console.log('[Recording] 开始处理音频下载数据，长度:', data.data.audio_data.length);
          const audioBytes = new Uint8Array(data.data.audio_data.match(/.{1,2}/g).map(byte => parseInt(byte, 16)));
          const audioBlob = new Blob([audioBytes], { type: 'audio/wav' });
          
          console.log('[Recording] 音频Blob创建成功，大小:', audioBlob.size, 'bytes');
          
          // 缓存音频数据用于重复导出
          window.lastAudioBlob = audioBlob;
          window.lastDownloadedAudioFile = data.data.filename || `${currentSessionId}.wav`;
          
          // 创建下载链接
          const url = URL.createObjectURL(audioBlob);
          const link = document.createElement('a');
          link.href = url;
          link.download = window.lastDownloadedAudioFile;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
          
          console.log('[Recording] 录音文件已下载:', window.lastDownloadedAudioFile);
          
          // 显示成功提示
          const successMessage = document.createElement('div');
          successMessage.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4CAF50;
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            z-index: 10000;
            font-size: 14px;
          `;
          successMessage.textContent = `音频文件已成功导出: ${window.lastDownloadedAudioFile}`;
          document.body.appendChild(successMessage);
          
          // 3秒后自动移除提示
          setTimeout(() => {
            if (document.body.contains(successMessage)) {
              document.body.removeChild(successMessage);
            }
          }, 3000);
          
          // 音频文件下载成功后，显示字幕导出选项
          if (!exportDialogShown) {
            exportDialogShown = true;
            showExportOptions((data.data.effective_duration || data.data.duration || 0) / 1000, true);
          } else {
            console.log('[Recording] 导出对话框已显示，跳过重复显示');
          }
          
        } catch (error) {
          console.error('[Recording] 处理音频下载失败:', error);
          alert('音频文件下载失败: ' + error.message + '\n\n字幕数据仍可导出');
          // 检查是否有缓存的音频数据
          const hasAudio = !!(window.lastAudioBlob && window.lastDownloadedAudioFile);
          if (!exportDialogShown) {
            exportDialogShown = true;
            showExportOptions(0, hasAudio);
          } else {
            console.log('[Recording] 导出对话框已显示，跳过重复显示');
          }
        }
      }
      return;
    }
    
    // 处理音频下载失败消息
    if (data.audio_download_failed) {
      console.log('[Recording] ========== 收到音频下载失败通知 ==========');
      console.log('[Recording] 下载失败数据:', data);
      
      // 清除下载准备超时
      if (window.downloadPrepareTimeoutId) {
        clearTimeout(window.downloadPrepareTimeoutId);
        window.downloadPrepareTimeoutId = null;
      }
      
      // 移除准备下载对话框
      const prepareDialog = document.getElementById('prepare-download-dialog');
      if (prepareDialog) {
        document.body.removeChild(prepareDialog);
      }
      
      alert(data.message || '音频下载失败，但录音已保存到本地' + '\n\n字幕数据仍可导出');
      // 检查是否有缓存的音频数据
      const hasAudio = !!(window.lastAudioBlob && window.lastDownloadedAudioFile);
      if (!exportDialogShown) {
        exportDialogShown = true;
        showExportOptions(0, hasAudio);
      } else {
        console.log('[Recording] 导出对话框已显示，跳过重复显示');
      }
      return;
    }
    
    if (data.translated || data.data || data.info) {
      const original = (typeof data.data === 'string' && data.data.trim()) ? data.data
                      : (typeof data.info === 'string' ? data.info : '');
      const translated = data.translated || '';
      const timestamp = data.timestamp || new Date().toISOString();
      
      // 添加到历史记录
      history.push({ text: original, translated });
      if (history.length > MAX_HISTORY) history.shift();
      
      // 如果启用了记录模式且正在录音状态，添加到记录历史
      // 关键修复：只有在录音已确认开始且正在录音时才记录字幕（严格检查非暂停状态）
      if (recordMode && recordingState === 'recording' && recordingConfirmed && currentSessionId && original.trim()) {
        console.log('[Record] ========== 添加字幕到记录 ==========');
        console.log('[Record] 字幕内容:', original);
        console.log('[Record] 当前状态:', {
          recordMode,
          recordingState,
          recordingConfirmed,
          currentSessionId,
          historyLength: recordHistory.length
        });
        // 传递完整的数据对象，包含可能的相对时间戳信息
        addToRecord(original, translated, data);
      } else if (recordMode) {
        console.log('[Record] 跳过字幕记录 - 状态:', {
          recordMode,
          recordingState,
          recordingConfirmed,
          currentSessionId,
          hasOriginal: !!original.trim(),
          reason: !recordingConfirmed ? '录音未确认' : !currentSessionId ? '无session' : recordingState !== 'recording' ? '非录音状态' : '无内容'
        });
      }
      
      // 渲染字幕的逻辑：
      // 1. 非记录模式：总是渲染字幕
      // 2. 记录模式且正在录音：渲染（实时显示）
      // 3. 记录模式但录音已结束或暂停：不渲染（显示记录内容）
      if (!recordMode) {
        // 字幕模式：无论录音状态如何都要渲染字幕
        renderSubtitles();
        console.log('[Subtitle] 字幕模式：渲染字幕，录音状态:', recordingState);
      } else if (recordingState === 'recording') {
        // 记录模式且正在录音：同时显示实时字幕
        renderSubtitles();
        console.log('[Subtitle] 记录模式录音中：渲染字幕');
      } else {
        // 记录模式但未录音或已暂停：只显示记录内容，不渲染新字幕
        console.log('[Subtitle] 记录模式非录音状态：跳过字幕渲染，当前状态:', { recordMode, recordingState });
      }
    } else {
      subtitleContainer.innerText = '收到数据但无info字段：' + JSON.stringify(data);
    }
  }

  function reconnectWS() {
    console.warn('[WS] reconnectWS: 连接断开，2 秒后尝试重连...');
    console.warn('[WS] 重连时的录音状态:', recordingState);
    console.warn('[WS] 重连时的session_id:', currentSessionId);
    
    closeOldWS();
    setTimeout(() => {
      console.warn('[WS] reconnectWS: 执行connectToSubtitleWS');
      connectToSubtitleWS(currentTargetLang);
      
      // 如果正在录音，重连后需要重新设置录音状态
      setTimeout(() => {
        if (recordingState === 'recording' && currentSessionId) {
          console.warn('[WS] 重连后检测到正在录音，但后端可能已丢失会话状态');
          console.warn('[WS] 建议用户重新开始录音以确保数据完整性');
          
          // 可以考虑在这里显示警告给用户
          // alert('检测到录音过程中网络重连，建议停止当前录音并重新开始以确保完整性');
        }
      }, 1000);
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
              // 启动音频流：先尝试使用之前的设备，如果没有则等待设备列表
              if (currentDeviceId) {
                console.log('[WS] WebSocket就绪，使用之前的设备启动音频流:', currentDeviceId);
                window.subtitleAPI.switchDevice(currentDeviceId);
              } else {
                console.log('[WS] WebSocket就绪，currentDeviceId为空，请求设备列表');
              }
              
              // 请求设备列表（这会触发renderDeviceList中的自动启动逻辑）
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

  // 记录功能事件监听器
  const recordIcon = document.getElementById('record-icon');
  
  if (recordIcon) {
    recordIcon.addEventListener('click', toggleRecordMode);
  }
  
  // 新录音控制按钮事件监听器（简化版 - 移除暂停功能）
  const recordBtn = document.getElementById('record-btn');
  const stopBtn = document.getElementById('stop-btn');
  
  if (recordBtn) {
    recordBtn.addEventListener('click', () => {
      startRecording();
    });
  }
  
  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      // 使用WebSocket方式停止录音（与ASR共享音频源）
      stopRecording();
    });
  }

  // 窗口控制按钮事件监听器
  const pinBtn = document.getElementById('pin-btn');
  const closeBtn = document.getElementById('close-btn');
  let isPinned = false;
  
  if (pinBtn) {
    pinBtn.addEventListener('click', () => {
      isPinned = !isPinned;
      
      if (window.subtitleAPI && window.subtitleAPI.setAlwaysOnTop) {
        window.subtitleAPI.setAlwaysOnTop(isPinned);
        
        // 更新按钮状态
        if (isPinned) {
          pinBtn.classList.add('pinned');
          pinBtn.title = '取消固定窗口';
        } else {
          pinBtn.classList.remove('pinned');
          pinBtn.title = '固定窗口为最前';
        }
        
        console.log(`[Window] 窗口置顶: ${isPinned ? '启用' : '禁用'}`);
      } else {
        console.warn('[Window] 窗口置顶API不可用');
      }
    });
  }
  
  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      if (window.subtitleAPI && window.subtitleAPI.closeApp) {
        window.subtitleAPI.closeApp();
        console.log('[Window] 关闭程序');
      } else {
        console.warn('[Window] 关闭程序API不可用');
      }
    });
  }

  if (!window.subtitleAPI) {
    subtitleContainer.innerText = 'window.subtitleAPI 未注入，preload.js 可能未生效';
  }
  // 注意：WebSocket连接将在启动检查完成后由 finishStartup() 函数建立
});
