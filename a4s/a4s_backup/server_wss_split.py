# server_wss_split.py
# ✅ 基于 server_wss_original.py 重构，采用上传者/订阅者分离架构
from download_model import ModelDownloader
from threading import Thread
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from urllib.parse import parse_qs
from loguru import logger
import numpy as np
import traceback
import json
import time
import asyncio  # 修复未定义asyncio
import os
from collections import deque
import struct


# 初始化下载器
downloader = ModelDownloader()

# 加载模型路径
def ensure_model_ready(model_name: str) -> str:
    """确保模型存在并返回本地路径，优先使用系统级缓存"""
    config = downloader.models_config.get(model_name)
    if not config:
        raise RuntimeError(f"[模型加载] 未知模型: {model_name}")
    
    # 1. 优先检查版本记录中的系统缓存路径
    version_info = downloader.versions.get(model_name)
    if version_info and version_info.local_path and os.path.exists(version_info.local_path):
        logger.info(f"[模型加载] {model_name} 使用系统缓存路径: {version_info.local_path}")
        return version_info.local_path
    
    # 2. 检查旧路径（向后兼容）
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    old_paths = {
        "nllb200": os.path.join(BASE_DIR, "nllb200_ct2"),
        "fsmn_vad": os.path.join(BASE_DIR, "model", "vad")
    }
    
    old_path = old_paths.get(model_name)
    if old_path and os.path.exists(old_path):
        logger.info(f"[模型加载] {model_name} 使用项目内旧路径: {old_path}")
        logger.info(f"[模型加载] 提示: 下次重新下载将使用系统缓存")
        return old_path
    
    # 3. 需要下载到系统缓存
    logger.warning(f"[模型加载] {model_name} 本地不存在，下载到系统缓存...")
    success = downloader.download_model(model_name)
    if not success:
        raise RuntimeError(f"[模型加载] 无法下载模型 {model_name}")
    
    # 重新获取版本信息
    version_info = downloader.versions.get(model_name)
    final_path = version_info.local_path if version_info else None
    if not final_path:
        raise RuntimeError(f"[模型加载] 下载完成但无法获取路径: {model_name}")
    
    logger.info(f"[模型加载] {model_name} 下载到系统缓存: {final_path}")
    return final_path

async def prepare_models():
    asr_path = ensure_model_ready("sensevoice_small")
    vad_path = ensure_model_ready("fsmn_vad")
    translate_path = ensure_model_ready("nllb200")
    return {
        "asr": asr_path,
        "vad": vad_path,
        "translate": translate_path
    }

class Config:
    chunk_size_ms = 800
    sample_rate = 16000
    bit_depth = 16
    channels = 1
    avg_logprob_thr = -0.5
    sv_thr = 0.3
config = Config()

import ctranslate2
import sentencepiece as spm
import os
import re
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
from funasr import AutoModel
import soundfile as sf

# 设备检测函数
def get_device():
    """自动检测可用设备"""
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda:0"
            logger.info(f"检测到CUDA设备，使用GPU: {device}")
        else:
            device = "cpu"
            logger.info("未检测到CUDA设备，使用CPU")
        return device
    except ImportError:
        logger.warning("PyTorch未安装，默认使用CPU")
        return "cpu"
    except Exception as e:
        logger.warning(f"设备检测失败: {e}，默认使用CPU")
        return "cpu"

# ASR与VAD模型加载
asr_model_path = ensure_model_ready("sensevoice_small")
vad_model_path = ensure_model_ready("fsmn_vad")

# 自动选择设备
device = get_device()

try:
    model_asr = AutoModel(
        model=asr_model_path,
        trust_remote_code=True,
        remote_code="./model.py",
        device=device,
        disable_update=True,
        vad_model="fsmn-vad"
        # 暂时移除说话人分离功能，避免punc_model依赖问题
        # spk_model="cam++"  
    )
    logger.info(f"ASR模型加载成功，使用设备: {device}")
except Exception as e:
    if device == "cuda:0":
        logger.warning(f"GPU加载失败: {e}，尝试使用CPU")
        try:
            model_asr = AutoModel(
                model=asr_model_path,
                trust_remote_code=True,
                remote_code="./model.py",
                device="cpu",
                disable_update=True,
                vad_model="fsmn-vad"
                # 暂时移除说话人分离功能，避免punc_model依赖问题
                # spk_model="cam++"  
            )
            device = "cpu"
            logger.info("ASR模型CPU加载成功")
        except Exception as cpu_error:
            logger.error(f"CPU加载也失败: {cpu_error}")
            raise RuntimeError("ASR模型加载完全失败")
    else:
        logger.error(f"ASR模型加载失败: {e}")
        raise
model_vad = AutoModel(
    model=vad_model_path,
    model_revision="v2.0.4",
    disable_pbar=True,
    max_end_silence_time=350,
    disable_update=True,
)

def asr(audio, lang, cache, use_itn=False):
    import time
    start_time = time.time()
    result = model_asr.generate(
        input           = audio,
        cache           = cache,
        language        = lang.strip(),
        use_itn         = use_itn,
        batch_size_s    = 60,
    )
    end_time = time.time()
    elapsed_time = end_time - start_time
    logger.debug(f"asr elapsed: {elapsed_time * 1000:.2f} milliseconds")
    return result

def format_str_v3(s):
    # 精简版，保留原有多语种符号过滤逻辑
    def get_emo(s):
        return s[-1] if s and s[-1] in {"😊", "😔", "😡", "😰", "🤢", "😮"} else None
    def get_event(s):
        return s[0] if s and s[0] in {"🎼", "👏", "😀", "😭", "🤧", "😷"} else None
    s = s.replace("<|nospeech|><|Event_UNK|>", "❓")
    for lang in ["<|zh|>", "<|en|>", "<|yue|>", "<|ja|>", "<|ko|>", "<|nospeech|>"]:
        s = s.replace(lang, "<|lang|>")
    s_list = [s_i.strip() for s_i in s.split("<|lang|>")]
    new_s = " " + s_list[0] if s_list else ""
    cur_ent_event = get_event(new_s)
    for i in range(1, len(s_list)):
        if len(s_list[i]) == 0:
            continue
        if get_event(s_list[i]) == cur_ent_event and get_event(s_list[i]) != None:
            s_list[i] = s_list[i][1:]
        cur_ent_event = get_event(s_list[i])
        if get_emo(s_list[i]) != None and get_emo(new_s) == get_emo(s_list[i]):
            new_s = new_s[:-1]
        new_s += s_list[i].strip().lstrip()
    new_s = new_s.replace("The.", " ")
    return new_s.strip()

def clean_text_for_translate(text):
    # 只保留中英文、数字和常用标点，去除emoji和特殊符号，但保留所有空格
    return re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9，。！？、,.!?;:：；“”‘’\"'\s]", '', text)

# 翻译模型按需加载的全局变量
translator = None
sp = None
translate_model_path = None
translation_device = None
translation_enabled = False
translation_loading = False  # 新增：标记是否正在加载中

# 获取翻译模型设备（翻译模型通常在CPU上运行更稳定）
def get_translation_device():
    """为翻译模型选择设备"""
    try:
        import torch
        if torch.cuda.is_available():
            # 翻译模型可以选择GPU，但CPU通常更稳定
            # 对于大多数用户，建议使用CPU
            return "cpu"  # 可以改为 "cuda" 如果希望使用GPU
        else:
            return "cpu"
    except:
        return "cpu"

def load_translation_model():
    """按需加载翻译模型"""
    global translator, sp, translate_model_path, translation_device, translation_enabled, translation_loading
    
    if translation_loading:
        logger.info("翻译模型正在加载中，请稍候...")
        return False
    
    if translator is not None and sp is not None:
        logger.info("翻译模型已加载，跳过重复加载")
        return True
    
    try:
        translation_loading = True
        logger.info("开始加载翻译模型...")
        translate_model_path = ensure_model_ready("nllb200")
        translation_device = get_translation_device()
        
        translator = ctranslate2.Translator(translate_model_path, device=translation_device)
        logger.info(f"翻译模型加载成功，使用设备: {translation_device} (路径: {translate_model_path})")
        
        sp = spm.SentencePieceProcessor()
        sp.Load(os.path.join(translate_model_path, "sentencepiece.bpe.model"))
        logger.info("分词器加载成功")
        
        translation_enabled = True
        return True
    except Exception as e:
        translator = None
        sp = None
        translation_enabled = False
        logger.error(f"翻译模型加载失败: {e}")
        return False
    finally:
        translation_loading = False

def unload_translation_model():
    """卸载翻译模型以释放内存"""
    global translator, sp, translation_enabled
    translator = None
    sp = None
    translation_enabled = False
    logger.info("翻译模型已卸载")

def translate_text(text, src_lang="zh", tgt_lang="en"):
    # 如果翻译模型未启用或加载，先尝试加载
    if not translation_enabled:
        if not load_translation_model():
            return ""
    
    if translator is None or sp is None or not text.strip():
        return ""
    try:
        # 补全所有前端支持的目标语言映射
        lang_map = {
            "zh": "zho_Hans",      # 中文简体
            "en": "eng_Latn",     # 英语
            "ja": "jpn_Jpan",     # 日语
            "ko": "kor_Hang",     # 韩语
            "fr": "fra_Latn",     # 法语
            "de": "deu_Latn",     # 德语
            "es": "spa_Latn",     # 西班牙语
            "ru": "rus_Cyrl",     # 俄语
            "ar": "ara_Arab",     # 阿拉伯语
            "vi": "vie_Latn",     # 越南语
            "th": "tha_Thai",     # 泰语
            "id": "ind_Latn",     # 印尼语
            "pt": "por_Latn",     # 葡萄牙语
            "it": "ita_Latn",     # 意大利语
            "hi": "hin_Deva",     # 印地语
            "yue": "yue_Hant",    # 粤语（繁体）
        }
        src = lang_map.get(src_lang, src_lang)
        tgt = lang_map.get(tgt_lang, tgt_lang)
        if not text.strip():
            logger.debug(f"Translate input is empty: {text}")
            return ""
        tokens = [src] + sp.EncodeAsPieces(text) + ["</s>"]
        logger.debug(f"Translate input: {text}, tokens: {tokens}")
        results = translator.translate_batch([tokens], target_prefix=[[tgt]])
        output_tokens = results[0].hypotheses[0]
        output_tokens = [t for t in output_tokens if t not in [src, tgt, "</s>"]]
        return sp.DecodePieces(output_tokens)
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return ""
# ===== END =====

# 导入独立录音服务和播放时间同步
# 注意：recording_service 和 audio_playback_sync 模块已被清理
# 相关功能已迁移到 python/ 目录下的双流音频服务中
# import sys
# import os
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from recording_service import recording_service
# from audio_playback_sync import get_playback_sync_manager

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加翻译模型控制接口
@app.post("/translation/load")
async def load_translation():
    """加载翻译模型"""
    success = load_translation_model()
    return {
        "success": success,
        "enabled": translation_enabled,
        "loading": translation_loading,
        "message": "翻译模型加载成功" if success else "翻译模型加载失败"
    }

@app.post("/translation/unload")
async def unload_translation():
    """卸载翻译模型"""
    unload_translation_model()
    return {
        "success": True,
        "enabled": translation_enabled,
        "message": "翻译模型已卸载"
    }

@app.get("/translation/status")
async def translation_status():
    """获取翻译模型状态"""
    return {
        "enabled": translation_enabled,
        "loading": translation_loading,
        "loaded": translator is not None and sp is not None
    }

# ===== 独立录音API =====
from pydantic import BaseModel
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional

class StartRecordingRequest(BaseModel):
    filename: str
    session_id: Optional[str] = None

class StopRecordingRequest(BaseModel):
    session_id: str

class RecordingControlRequest(BaseModel):
    session_id: str

# 录音相关的API功能已迁移到双流音频服务，暂时禁用这些端点
# 用户可以通过 python/enhanced_dual_audio_service.py 获得更好的录音功能

@app.post("/api/recording/start")
async def start_independent_recording_disabled(request: StartRecordingRequest):
    """录音功能已迁移到双流音频服务"""
    return {
        "success": False,
        "error": "API_MIGRATED",
        "message": "录音功能已迁移到双流音频服务，请使用 python/enhanced_dual_audio_service.py"
    }

@app.post("/api/recording/pause")
async def pause_independent_recording_disabled(request: RecordingControlRequest):
    """录音功能已迁移到双流音频服务"""
    return {
        "success": False,
        "error": "API_MIGRATED",
        "message": "录音功能已迁移到双流音频服务"
    }

@app.post("/api/recording/resume")
async def resume_independent_recording_disabled(request: RecordingControlRequest):
    """录音功能已迁移到双流音频服务"""
    return {
        "success": False,
        "error": "API_MIGRATED", 
        "message": "录音功能已迁移到双流音频服务"
    }

@app.post("/api/recording/stop")
async def stop_independent_recording_disabled(request: StopRecordingRequest):
    """录音功能已迁移到双流音频服务"""
    return {
        "success": False,
        "error": "API_MIGRATED",
        "message": "录音功能已迁移到双流音频服务"
    }

@app.get("/api/recording/status/{session_id}")
async def get_recording_status_disabled(session_id: str):
    """录音功能已迁移到双流音频服务"""
    return {
        "success": False,
        "error": "API_MIGRATED",
        "message": "录音功能已迁移到双流音频服务"
    }

@app.get("/download/{filename}")
async def download_file(filename: str):
    """下载录音相关文件"""
    try:
        recordings_dir = Path("recordings")
        file_path = recordings_dir / filename
        
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                filename=filename,
                media_type='application/octet-stream'
            )
        else:
            return {
                "success": False,
                "error": "文件不存在",
                "message": f"文件 {filename} 不存在"
            }
    except Exception as e:
        logger.error(f"[API] 文件下载异常: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "文件下载异常"
        }

subscribers = set()
subscriber_langs = dict()  # 记录目标语言
latest_subscriber = None   # 只保留最新的订阅者
last_plain_text = None     # 最近一次的纯文本字幕
last_info_text = None     # 最近一次的 info 字幕
latest_device_list = []   # 新增：全局缓存最新设备列表
latest_uploader = None   # 新增：记录最新采集端连接
current_recording_start_time = None  # 新增：当前录音开始时间（用于时间戳同步）

# 音频数据缓存 - 用于录音功能（只在录音时启用）
recording_audio_buffer = {}  # {session_id: deque(...)}
recording_timestamps = {}    # {session_id: deque(...)}
recording_sessions = {}      # 活跃的录音会话 {session_id: {start_time, end_time, filename, is_active}}
recording_enabled = False    # 全局录音缓存开关

# 全局音频处理器引用 - 用于获取精确音频时长
global_audio_handler = None

# 音频参数
SAMPLE_RATE = 16000  # ASR处理用
CHANNELS = 1         # ASR处理用
BYTES_PER_SAMPLE = 2  # 16-bit ASR处理用

# 高质量录音参数（用于后端录音缓存）
HQ_SAMPLE_RATE = 44100  # 44.1kHz 高质量
HQ_CHANNELS = 2         # 立体声
HQ_BYTES_PER_SAMPLE = 3 # 24-bit = 3 bytes

# 启动时检查一次模型更新
def startup_model_check():
    """启动时检查模型更新并下载"""
    try:
        logger.info("[启动检查] 检查模型更新中...")
        updated_models = downloader.update_models_background()
        if updated_models:
            logger.info(f"[启动检查] 发现并下载了更新: {updated_models}")
        else:
            logger.info("[启动检查] 所有模型都是最新版本")
    except Exception as e:
        logger.error(f"[启动检查] 执行失败: {e}")

# 启动时执行一次模型检查
startup_model_check()

class TranscriptionResponse(BaseModel):
    code: int
    info: str
    data: str
    translated: str = ""

@app.websocket("/ws/subscribe")
async def subtitle_subscriber(websocket: WebSocket):
    global latest_subscriber, last_plain_text, last_info_text, latest_device_list, latest_uploader, current_recording_start_time
    await websocket.accept()
    subscribers.add(websocket)
    latest_subscriber = websocket  # 只保留最新
    subscriber_langs[websocket] = 'en'  # 默认英语
    logger.info(f"[subscribe] new client: {websocket.client}")
    # 新增：连接建立后立即推送设备列表（如有）
    if latest_device_list:
        try:
            await websocket.send_json({"device_list": latest_device_list})
            logger.info(f"[subscribe] 首次推送设备列表: {latest_device_list}")
        except Exception as e:
            logger.warning(f"[subscribe] 首次推送设备列表失败: {e}")
    try:
        while True:
            msg = await websocket.receive_text()
            logger.info(f"[subscribe] 收到消息: {msg}")
            try:
                data = json.loads(msg)
            except Exception as e:
                logger.warning(f"[subscribe] JSON解析失败: {e}, 原始消息: {msg}")
                continue
            # 优先处理心跳ping-pong，收到ping立即响应pong
            if isinstance(data, dict) and data.get('type') == 'ping':
                logger.debug(f"[subscribe] 收到心跳ping，立即响应pong")
                try:
                    await websocket.send_json({'type': 'pong'})
                    logger.debug(f"[subscribe] 已发送pong")
                except Exception as e:
                    logger.warning(f"[subscribe] 发送pong失败: {e}")
                    # 不要因为心跳失败就断开连接，继续处理其他消息
                continue
            # 新增：收到 switch_device 指令时转发给采集端
            if isinstance(data, dict) and 'switch_device' in data:
                if latest_uploader:
                    try:
                        await latest_uploader.send_json({'switch_device': data['switch_device']})
                        logger.info(f"[subscribe] 已转发切换设备请求到采集端: {data['switch_device']}")
                    except Exception as e:
                        logger.warning(f"[subscribe] 转发切换设备失败: {e}")
                else:
                    logger.warning("[subscribe] 没有采集端在线，无法转发切换设备")
                continue
            
            # 新增：处理录音命令并转发给采集端
            if isinstance(data, dict) and 'start_recording' in data:
                if latest_uploader:
                    try:
                        await latest_uploader.send_text(json.dumps(data))
                        logger.info(f"[subscribe] 已转发录音开始命令到采集端: {data}")
                    except Exception as e:
                        logger.warning(f"[subscribe] 转发录音开始命令失败: {e}")
                else:
                    logger.warning("[subscribe] 没有采集端在线，无法开始录音")
                continue
            
            if isinstance(data, dict) and 'stop_recording' in data:
                if latest_uploader:
                    try:
                        await latest_uploader.send_text(json.dumps(data))
                        logger.info(f"[subscribe] 已转发录音停止命令到采集端: {data}")
                    except Exception as e:
                        logger.warning(f"[subscribe] 转发录音停止命令失败: {e}")
                else:
                    logger.warning("[subscribe] 没有采集端在线，无法停止录音")
                continue
            
            # 新增：处理录音暂停命令并转发给采集端
            if isinstance(data, dict) and 'pause_recording' in data:
                if latest_uploader:
                    try:
                        await latest_uploader.send_text(json.dumps(data))
                        logger.info(f"[subscribe] 已转发录音暂停命令到采集端: {data}")
                    except Exception as e:
                        logger.warning(f"[subscribe] 转发录音暂停命令失败: {e}")
                else:
                    logger.warning("[subscribe] 没有采集端在线，无法暂停录音")
                continue
            
            # 新增：处理录音恢复命令并转发给采集端
            if isinstance(data, dict) and 'resume_recording' in data:
                if latest_uploader:
                    try:
                        await latest_uploader.send_text(json.dumps(data))
                        logger.info(f"[subscribe] 已转发录音恢复命令到采集端: {data}")
                    except Exception as e:
                        logger.warning(f"[subscribe] 转发录音恢复命令失败: {e}")
                else:
                    logger.warning("[subscribe] 没有采集端在线，无法恢复录音")
                continue
            if isinstance(data, dict) and data.get('get_device_list'):
                await websocket.send_json({"device_list": latest_device_list})
                logger.info(f"[subscribe] 已推送设备列表: {latest_device_list}")
                continue
            if isinstance(data, dict) and 'set_target_lang' in data:
                subscriber_langs[websocket] = data['set_target_lang']
                logger.info(f"[subscribe] {websocket.client} set target lang: {data['set_target_lang']} 当前 subscriber_langs: {subscriber_langs}")
                # 新增：切换目标语言后，立即用新目标语言重翻译最近字幕并推送
                if last_plain_text is not None and last_info_text is not None:
                    tgt_lang_sub = subscriber_langs.get(websocket, 'en')
                    try:
                        translated = translate_text(last_plain_text, tgt_lang=tgt_lang_sub)
                    except Exception as e:
                        logger.error(f"Translate error (on lang switch): {e}")
                        translated = ""
                    response = TranscriptionResponse(
                        code=0,
                        info=last_info_text,
                        data=last_info_text,
                        translated=translated
                    )
                    await websocket.send_json(response.model_dump())
            # 新增：心跳ping-pong机制
            if isinstance(data, dict) and data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})
                continue
    except WebSocketDisconnect:
        subscribers.discard(websocket)
        subscriber_langs.pop(websocket, None)
        if websocket == latest_subscriber:
            latest_subscriber = None
        logger.info("[subscribe] client disconnected")

@app.websocket("/ws/upload")
async def audio_uploader(websocket: WebSocket):
    global latest_subscriber, last_plain_text, last_info_text, latest_device_list, latest_uploader, current_recording_start_time
    await websocket.accept()
    latest_uploader = websocket  # 新增：注册采集端连接
    try:
        query_params = parse_qs(websocket.scope['query_string'].decode())
        sv = query_params.get('sv', ['false'])[0].lower() in ['true', '1', 't', 'y', 'yes']
        lang = query_params.get('lang', ['auto'])[0].lower()
        tgt_lang = query_params.get('tgt_lang', ['en'])[0].lower()

        chunk_size = int(config.chunk_size_ms * config.sample_rate / 1000)
        audio_buffer = np.array([], dtype=np.float32)
        audio_vad = np.array([], dtype=np.float32)
        cache, cache_asr = {}, {}
        last_vad_beg = last_vad_end = -1
        offset, hit = 0, False
        buffer = b""

        while True:
            try:
                msg = await websocket.receive()
                if msg['type'] == 'websocket.disconnect':
                    logger.info("[upload] WebSocket disconnect message received")
                    break
                elif msg['type'] == 'websocket.receive':
                    if 'bytes' in msg:
                        data = msg['bytes']
                        buffer += data
                        if len(buffer) < 2:
                            continue

                        raw_audio_data = buffer[:len(buffer) - (len(buffer) % 2)]
                        
                        # 只在有活跃录音会话时才缓存音频数据
                        if recording_enabled and recording_sessions:
                            current_time = time.time()
                            cached_sessions = 0
                            for session_id, session in recording_sessions.items():
                                if session.get('is_active', False):
                                    # 为每个活跃会话缓存音频数据
                                    if session_id not in recording_audio_buffer:
                                        recording_audio_buffer[session_id] = deque()
                                        recording_timestamps[session_id] = deque()
                                    
                                    recording_audio_buffer[session_id].append(raw_audio_data)
                                    recording_timestamps[session_id].append(current_time)
                                    cached_sessions += 1
                            
                            # 调试信息：显示缓存状态
                            if cached_sessions > 0:
                                logger.debug(f"[recording] 音频缓存: {cached_sessions}个活跃会话, 时间戳: {current_time:.3f}, 数据大小: {len(raw_audio_data)} bytes")
                            else:
                                logger.debug(f"[recording] 录音会话已暂停，跳过音频缓存")

                        audio_buffer = np.append(
                            audio_buffer,
                            np.frombuffer(raw_audio_data, dtype=np.int16).astype(np.float32) / 32767.0
                        )
                        buffer = buffer[len(buffer) - (len(buffer) % 2):]

                        while len(audio_buffer) >= chunk_size:
                            chunk = audio_buffer[:chunk_size]
                            audio_buffer = audio_buffer[chunk_size:]
                            audio_vad = np.append(audio_vad, chunk)

                            res = model_vad.generate(input=chunk, cache=cache, is_final=False, chunk_size=config.chunk_size_ms)
                            if len(res[0]["value"]):
                                vad_segments = res[0]["value"]
                                for segment in vad_segments:
                                    if segment[0] > -1: last_vad_beg = segment[0]
                                    if segment[1] > -1: last_vad_end = segment[1]

                                    if last_vad_beg > -1 and last_vad_end > -1:
                                        # 修复：确保时间戳计算的正确性
                                        adjusted_beg = max(0, last_vad_beg - offset)  # 防止负值
                                        adjusted_end = max(0, last_vad_end - offset)  # 防止负值
                                        
                                        # 确保end > beg，防止无效音频段
                                        if adjusted_end <= adjusted_beg:
                                            logger.debug(f"跳过无效音频段: beg={adjusted_beg}, end={adjusted_end}")
                                            last_vad_beg = last_vad_end = -1
                                            continue
                                        
                                        offset += adjusted_end
                                        beg = int(adjusted_beg * config.sample_rate / 1000)
                                        end = int(adjusted_end * config.sample_rate / 1000)
                                        audio_len = end - beg
                                        logger.info(f"[vad segment] audio_len: {audio_len}")

                                        # 跳过空音频段或过短的音频段
                                        if audio_len <= 0:
                                            logger.debug("跳过空音频段")
                                            audio_vad = audio_vad[end:] if end > 0 else audio_vad
                                            last_vad_beg = last_vad_end = -1
                                            continue

                                        # 计算音频块的精确时间戳
                                        chunk_start_time = time.time()
                                        audio_chunk_offset = beg / config.sample_rate  # 音频块在总音频中的偏移时间
                                        
                                        result = asr(audio_vad[beg:end], lang.strip(), cache_asr, True)
                                        logger.debug(f"asr result: {result}")
                                        audio_vad = audio_vad[end:]
                                        last_vad_beg = last_vad_end = -1

                                        if result:
                                            asr_text = result[0]['text']
                                            
                                            formatted_text = format_str_v3(asr_text)
                                            def strip_asr_tags(text):
                                                import re
                                                text = re.sub(r'<\|.*?\|>', '', text)
                                                text = text.replace('withitn', '').replace('woitn', '')
                                                return text.strip()
                                            plain_text = strip_asr_tags(asr_text)
                                            info_text = clean_text_for_translate(plain_text)
                                            def extract_lang_from_asr(text):
                                                import re
                                                m = re.match(r"<\|([a-z]{2,3})\|>", text)
                                                if m:
                                                    return m.group(1)
                                                return "zh"  # 默认中文
                                            lang_map = {
                                                "zh": "zho_Hans",  # 中文简体
                                                "en": "eng_Latn",  # 英语
                                                "ja": "jpn_Jpan",  # 日语
                                                "ko": "kor_Hang",  # 韩语
                                                "ru": "rus_Cyrl",  # 俄语
                                                "fr": "fra_Latn",  # 法语
                                                "de": "deu_Latn",  # 德语
                                                "es": "spa_Latn",  # 西班牙语
                                                "ar": "ara_Arab",  # 阿拉伯语
                                                "vi": "vie_Latn",  # 越南语
                                                "th": "tha_Thai",  # 泰语
                                                "id": "ind_Latn",  # 印尼语
                                                "ms": "msa_Latn",  # 马来语
                                                "fil": "fil_Latn", # 菲律宾语
                                                "km": "khm_Khmr",  # 高棉语
                                                "my": "bur_Mymr",  # 缅甸语
                                                "tr": "tur_Latn",  # 土耳其语
                                                "it": "ita_Latn",  # 意大利语
                                                "pt": "por_Latn",  # 葡萄牙语
                                                "hi": "hin_Deva",  # 印地语
                                                "bn": "ben_Beng",  # 孟加拉语
                                                "ta": "tam_Taml",  # 泰米尔语
                                                "ur": "urd_Arab",  # 乌尔都语
                                            }
                                            asr_lang = extract_lang_from_asr(asr_text)
                                            src_lang = lang_map.get(asr_lang, "zho_Hans")
                                            plain_text = strip_asr_tags(asr_text)
                                            last_plain_text = plain_text
                                            last_info_text = info_text
                                            
                                            # 修复：原声字幕与翻译功能解耦，始终推送原声字幕
                                            if latest_subscriber and latest_subscriber in subscriber_langs:
                                                tgt_lang_sub = subscriber_langs[latest_subscriber]
                                                logger.info(f"推送字幕，当前目标语言: {tgt_lang_sub}")
                                                
                                                # 只有在翻译模型可用时才进行翻译
                                                translated = ""
                                                if translation_enabled and translator is not None and sp is not None:
                                                    try:
                                                        translated = translate_text(plain_text, src_lang=src_lang, tgt_lang=tgt_lang_sub)
                                                        logger.info(f"推送字幕内容 translated: {translated}")
                                                    except Exception as e:
                                                        logger.error(f"翻译失败: {e}")
                                                        translated = ""
                                                else:
                                                    logger.debug("翻译模型未加载，仅推送原声字幕")
                                                
                                                # 只在有有效内容时才发送，避免发送空字幕
                                                if plain_text and plain_text.strip():
                                                    # 计算精确的音频同步时间戳
                                                    audio_sync_timestamp = chunk_start_time
                                                    
                                                    # 如果正在录音，计算相对于录音开始的精确时间戳（使用音频数据时长）
                                                    recording_relative_time = None
                                                    if current_recording_start_time is not None:
                                                        # 尝试从音频采集器获取精确的音频时长
                                                        try:
                                                            # 获取音频采集器的精确音频时长
                                                            audio_duration = global_audio_handler.get_current_audio_duration() if hasattr(global_audio_handler, 'get_current_audio_duration') else None
                                                            
                                                            if audio_duration is not None:
                                                                # 使用基于音频数据的精确时长作为时间戳
                                                                recording_relative_time = audio_duration
                                                                logger.debug(f"[timestamp] 使用音频数据精确时长: {recording_relative_time:.3f}s")
                                                            else:
                                                                # 回退到原有逻辑：使用音频块的实际开始时间计算
                                                                # 修复：简化时间戳计算，直接使用当前时间与录音开始时间的差值
                                                                base_relative_time = chunk_start_time - current_recording_start_time
                                                                
                                                                # 从所有活跃录音会话中找到并扣除累积暂停时间
                                                                total_pause_time = 0
                                                                session_is_paused = False
                                                                for session_id, session in recording_sessions.items():
                                                                    if session.get('is_active', False):
                                                                        # 获取该会话的累积暂停时间
                                                                        total_pause_time = session.get('total_paused_time', 0)
                                                                        
                                                                        # 关键检查：如果当前正在暂停中，直接跳过这个字幕
                                                                        if session.get('pause_start'):
                                                                            session_is_paused = True
                                                                            logger.debug(f"[timestamp] 检测到会话{session_id}正在暂停中，跳过字幕记录")
                                                                            break
                                                                        
                                                                        break  # 只处理第一个活跃会话
                                                                
                                                                # 如果会话正在暂停，直接跳过后续处理
                                                                if session_is_paused:
                                                                    logger.debug(f"[subtitle] 录音会话暂停中，跳过字幕: '{plain_text[:20]}...'")
                                                                    continue
                                                                
                                                                # 计算去除暂停时间后的有效录音时间
                                                                recording_relative_time = max(0, base_relative_time - total_pause_time)
                                                                logger.debug(f"[timestamp] 修复后时间戳计算: 基础时间={base_relative_time:.3f}s, 暂停时间={total_pause_time:.3f}s, 有效时间={recording_relative_time:.3f}s")
                                                        except Exception as e:
                                                            logger.warning(f"[timestamp] 获取音频时长失败，使用最终回退计算: {e}")
                                                            # 最终回退到基础计算（简化版本）
                                                            recording_relative_time = max(0, chunk_start_time - current_recording_start_time)
                                                        
                                                        # 获取播放时间同步管理器并添加字幕
                                                        for session_id, session in recording_sessions.items():
                                                            if session.get('is_active', False):
                                                                # 字幕同步功能已迁移到双流音频服务
                                                                # sync_manager = get_playback_sync_manager(session_id)
                                                                # sync_manager.add_subtitle(plain_text, translated, chunk_start_time)
                                                                pass
                                                    
                                                    response = TranscriptionResponse(
                                                        code=0,
                                                        info=plain_text,  # 直接用原声
                                                        data=plain_text,  # 直接用原声
                                                        translated=translated  # 可能为空字符串
                                                    )
                                                    
                                                    # 添加精确时间戳到响应中
                                                    response_data = response.model_dump()
                                                    response_data['timestamp'] = chunk_start_time
                                                    response_data['audio_sync_time'] = audio_sync_timestamp  # 用于音频同步的精确时间戳
                                                    response_data['audio_chunk_offset'] = audio_chunk_offset  # 音频块在音频流中的偏移
                                                    
                                                    # 如果正在录音，添加相对时间戳和播放时间信息
                                                    if recording_relative_time is not None:
                                                        response_data['recording_relative_time'] = recording_relative_time
                                                        response_data['recording_start_time'] = current_recording_start_time
                                                        
                                                        # 添加播放时间信息
                                                        for session_id, session in recording_sessions.items():
                                                            if session.get('is_active', False):
                                                                # 播放时间同步功能已迁移到双流音频服务
                                                                # sync_manager = get_playback_sync_manager(session_id)
                                                                # playback_time = sync_manager._convert_to_playback_time(chunk_start_time)
                                                                # if playback_time is not None:
                                                                #     response_data['playback_time'] = playback_time
                                                                #     response_data['session_id'] = session_id
                                                                # break
                                                                pass
                                                    
                                                    await latest_subscriber.send_json(response_data)
                                                    
                                                    # 记录字幕时间戳用于调试
                                                    logger.debug(f"[subtitle] 发送字幕: '{plain_text[:20]}...', 时间戳: {chunk_start_time:.3f}")
                                                else:
                                                    logger.debug("跳过空字幕，不发送")
                    elif 'text' in msg:
                        # 处理JSON指令，如设备列表、切换等
                        try:
                            data = json.loads(msg['text'])
                            logger.info(f"[upload] 收到文本消息: {data}")
                            # 新增：收到设备列表时缓存并推送给所有订阅者
                            if isinstance(data, dict) and 'device_list' in data:
                                latest_device_list = data['device_list']
                                logger.info(f"[upload] 更新设备列表: {latest_device_list}")
                                # 推送给所有订阅者
                                for ws in list(subscribers):
                                    try:
                                        await ws.send_json({"device_list": latest_device_list})
                                    except Exception as e:
                                        logger.warning(f"[upload] 推送设备列表失败，移除无效连接: {e}")
                                        subscribers.discard(ws)
                                        subscriber_langs.pop(ws, None)
                            
                            # 新增：转发录音相关消息给订阅者
                            elif isinstance(data, dict) and ('recording_started' in data or 'recording_completed' in data):
                                logger.info(f"[upload] 转发录音消息给订阅者: {data}")
                                
                                # 如果是录音开始消息，保存录音开始时间用于时间戳同步
                                if 'recording_started' in data and 'start_time' in data:
                                    current_recording_start_time = data['start_time']
                                    logger.info(f"[upload] 录音开始时间已保存: {current_recording_start_time}")
                                # 如果是录音结束消息，清除录音开始时间
                                elif 'recording_completed' in data:
                                    current_recording_start_time = None
                                    logger.info(f"[upload] 录音开始时间已清除")
                                
                                # 推送给最新的订阅者
                                if latest_subscriber:
                                    try:
                                        await latest_subscriber.send_json(data)
                                        logger.debug(f"[upload] 录音消息已转发给订阅者")
                                    except Exception as e:
                                        logger.warning(f"[upload] 转发录音消息失败: {e}")
                                else:
                                    logger.warning("[upload] 没有订阅者在线，无法转发录音消息")
                            # ...existing code...
                        except Exception as e:
                            logger.error(f"[upload] 文本消息解析失败: {e}")
                else:
                    await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"[upload] 消息处理异常: {e}")
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        # 处理WebSocket正常断开连接
        if websocket == latest_uploader:
            latest_uploader = None
        logger.info("[upload] client disconnected")
    except Exception as e:
        logger.error(f"[upload] error: {e}\n{traceback.format_exc()}")
        # 不要主动关闭连接，让客户端处理重连
        if websocket == latest_uploader:
            latest_uploader = None
    finally:
        cache.clear()
        subscribers.clear()
        subscriber_langs.clear()
        latest_subscriber = None
        logger.info("[upload] Clean up completed")

def generate_wav_header(data_size, use_hq=False):
    """生成WAV文件头"""
    if use_hq:
        # 高质量录音参数
        return struct.pack('<4sL4s4sLHHLLHH4sL',
            b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16, 1, HQ_CHANNELS,
            HQ_SAMPLE_RATE, HQ_SAMPLE_RATE * HQ_CHANNELS * HQ_BYTES_PER_SAMPLE,
            HQ_CHANNELS * HQ_BYTES_PER_SAMPLE, HQ_BYTES_PER_SAMPLE * 8, b'data', data_size)
    else:
        # 标准ASR参数
        return struct.pack('<4sL4s4sLHHLLHH4sL',
            b'RIFF', 36 + data_size, b'WAVE', b'fmt ', 16, 1, CHANNELS,
            SAMPLE_RATE, SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE,
            CHANNELS * BYTES_PER_SAMPLE, 16, b'data', data_size)

def extract_audio_segment(session_id, use_hq=False):
    """从指定会话的缓存中提取音频数据"""
    logger.info(f"[recording] 开始提取音频数据: session_id={session_id}, use_hq={use_hq}")
    
    if session_id not in recording_audio_buffer:
        logger.warning(f"[recording] 未找到音频缓存: session_id={session_id}")
        logger.info(f"[recording] 当前缓存的会话: {list(recording_audio_buffer.keys())}")
        return None
        
    if session_id not in recording_timestamps:
        logger.warning(f"[recording] 未找到时间戳缓存: session_id={session_id}")
        return None
    
    audio_chunks = list(recording_audio_buffer[session_id])
    if not audio_chunks:
        logger.warning(f"[recording] 音频缓存为空: session_id={session_id}")
        return None
    
    logger.info(f"[recording] 找到 {len(audio_chunks)} 个音频块，总大小: {sum(len(chunk) for chunk in audio_chunks)} bytes")
    
    # 合并音频数据
    combined_data = b''.join(audio_chunks)
    logger.info(f"[recording] 合并后音频数据大小: {len(combined_data)} bytes")
    
    if use_hq:
        # 尝试提升音频质量 - 将单声道转为立体声
        try:
            import numpy as np
            # 将16位PCM数据转换为numpy数组
            audio_array = np.frombuffer(combined_data, dtype=np.int16)
            
            # 转换为立体声（复制声道）
            if HQ_CHANNELS == 2:
                # 创建立体声数组
                stereo_audio = np.zeros((len(audio_array) * 2,), dtype=np.int16)
                stereo_audio[0::2] = audio_array  # 左声道
                stereo_audio[1::2] = audio_array  # 右声道
                combined_data = stereo_audio.tobytes()
            
            # 生成高质量WAV文件头（16位立体声，16kHz）
            # 注意：这里保持16kHz采样率，因为重采样需要更复杂的处理
            wav_header = struct.pack('<4sL4s4sLHHLLHH4sL',
                b'RIFF', 36 + len(combined_data), b'WAVE', b'fmt ', 16, 1, HQ_CHANNELS,
                SAMPLE_RATE, SAMPLE_RATE * HQ_CHANNELS * BYTES_PER_SAMPLE,
                HQ_CHANNELS * BYTES_PER_SAMPLE, BYTES_PER_SAMPLE * 8, b'data', len(combined_data))
            
            logger.info(f"[recording] 生成高质量音频: {SAMPLE_RATE}Hz, {HQ_CHANNELS}声道, {BYTES_PER_SAMPLE*8}位, 最终大小: {len(wav_header) + len(combined_data)} bytes")
            
        except Exception as e:
            logger.warning(f"[recording] 高质量音频处理失败，回退到标准质量: {e}")
            # 回退到标准质量
            wav_header = generate_wav_header(len(combined_data), use_hq=False)
    else:
        # 生成标准质量WAV文件头
        wav_header = generate_wav_header(len(combined_data), use_hq=False)
        logger.info(f"[recording] 生成标准质量音频: {SAMPLE_RATE}Hz, {CHANNELS}声道, {BYTES_PER_SAMPLE*8}位, 最终大小: {len(wav_header) + len(combined_data)} bytes")
    
    return wav_header + combined_data

@app.websocket("/ws/recording")
async def recording_controller(websocket: WebSocket):
    """录音控制端点"""
    await websocket.accept()
    logger.info(f"[recording] new client: {websocket.client}")
    
    try:
        global recording_enabled
        while True:
            msg = await websocket.receive_text()
            logger.info(f"[recording] 收到消息: {msg}")
            
            try:
                data = json.loads(msg)
            except Exception as e:
                logger.warning(f"[recording] JSON解析失败: {e}")
                continue
            
            if "start_recording" in data:
                # 开始录音
                session_id = data.get("session_id", str(int(time.time())))
                start_time = time.time()
                filename = data.get("filename", f"recording_{session_id}.wav")
                
                # 创建录音会话
                recording_sessions[session_id] = {
                    "start_time": start_time,
                    "end_time": None,
                    "filename": filename,
                    "is_active": True,
                    "total_paused_time": 0,  # 累计暂停时间
                    "pause_start": None      # 当前暂停开始时间
                }
                
                # 启用全局录音缓存
                recording_enabled = True
                
                # 初始化此会话的音频缓存
                recording_audio_buffer[session_id] = deque()
                recording_timestamps[session_id] = deque()
                
                await websocket.send_json({
                    "success": True,
                    "message": "录音已开始，开始缓存音频数据",
                    "session_id": session_id,
                    "start_time": start_time,
                    "recording_started": True,  # 添加录音开始确认标志
                    "filename": filename
                })
                logger.info(f"[recording] 开始录音会话: {session_id}, 已启用音频缓存")
                
            elif "pause_recording" in data:
                # 暂停录音缓存
                session_id = data.get("session_id")
                if not session_id:
                    # 找到最新的活跃录音会话
                    active_sessions = {k: v for k, v in recording_sessions.items() if v.get('is_active', False)}
                    if active_sessions:
                        session_id = max(active_sessions.keys(), key=lambda k: active_sessions[k]["start_time"])
                
                if session_id in recording_sessions:
                    session = recording_sessions[session_id]
                    session["is_active"] = False  # 暂停缓存
                    session["pause_time"] = time.time()
                    session["pause_start"] = time.time()  # 记录当前暂停开始时间
                    
                    # 检查是否还有其他活跃会话
                    active_count = sum(1 for s in recording_sessions.values() if s.get('is_active', False))
                    if active_count == 0:
                        # 没有活跃会话了，关闭全局录音缓存
                        recording_enabled = False
                        logger.info("[recording] 所有录音会话已暂停，关闭音频缓存")
                    
                    await websocket.send_json({
                        "success": True,
                        "message": "录音缓存已暂停",
                        "session_id": session_id,
                        "pause_time": session["pause_time"]
                    })
                    logger.info(f"[recording] 录音会话已暂停: {session_id}")
                else:
                    await websocket.send_json({
                        "success": False,
                        "message": "未找到录音会话"
                    })
            
            elif "resume_recording" in data:
                # 恢复录音缓存
                session_id = data.get("session_id")
                if not session_id:
                    # 找到最新的录音会话
                    if recording_sessions:
                        session_id = max(recording_sessions.keys(), key=lambda k: recording_sessions[k]["start_time"])
                
                if session_id in recording_sessions:
                    session = recording_sessions[session_id]
                    
                    # 计算当前暂停时长并累加到总暂停时间
                    if session.get("pause_start"):
                        current_pause_duration = time.time() - session["pause_start"]
                        session["total_paused_time"] += current_pause_duration
                        logger.info(f"[recording] 会话{session_id}本次暂停时长: {current_pause_duration:.2f}s, 总暂停时长: {session['total_paused_time']:.2f}s")
                    
                    session["is_active"] = True  # 恢复缓存
                    session["resume_time"] = time.time()
                    session["pause_start"] = None  # 清除暂停开始时间
                    
                    # 启用全局录音缓存
                    recording_enabled = True
                    
                    await websocket.send_json({
                        "success": True,
                        "message": "录音缓存已恢复",
                        "session_id": session_id,
                        "resume_time": session["resume_time"]
                    })
                    logger.info(f"[recording] 录音会话已恢复: {session_id}, 重新启用音频缓存")
                else:
                    await websocket.send_json({
                        "success": False,
                        "message": "未找到录音会话"
                    })
            
            elif "stop_recording" in data:
                # 停止录音
                logger.info(f"[recording] 收到停止录音请求: {data}")
                session_id = data.get("session_id")
                if not session_id:
                    # 找到最新的活跃录音会话
                    active_sessions = {k: v for k, v in recording_sessions.items() if v.get('is_active', False)}
                    if active_sessions:
                        session_id = max(active_sessions.keys(), key=lambda k: active_sessions[k]["start_time"])
                        logger.info(f"[recording] 未指定session_id，使用最新活跃会话: {session_id}")
                    else:
                        logger.warning(f"[recording] 未找到活跃会话，检查所有会话...")
                        if recording_sessions:
                            session_id = max(recording_sessions.keys(), key=lambda k: recording_sessions[k]["start_time"])
                            logger.info(f"[recording] 使用最新会话: {session_id}")
                
                logger.info(f"[recording] 准备停止会话: {session_id}")
                logger.info(f"[recording] 当前所有会话: {list(recording_sessions.keys())}")
                logger.info(f"[recording] 当前音频缓存会话: {list(recording_audio_buffer.keys())}")
                
                if session_id in recording_sessions:
                    session = recording_sessions[session_id]
                    logger.info(f"[recording] 找到会话，当前状态: is_active={session.get('is_active', False)}")
                    
                    # 如果是从暂停状态停止，需要计算最后一次暂停的时长
                    if session.get("pause_start"):
                        final_pause_duration = time.time() - session["pause_start"]
                        session["total_paused_time"] += final_pause_duration
                        logger.info(f"[recording] 会话{session_id}最后暂停时长: {final_pause_duration:.2f}s, 总暂停时长: {session['total_paused_time']:.2f}s")
                    
                    session["end_time"] = time.time()
                    session["is_active"] = False
                    
                    # 检查是否还有其他活跃会话
                    active_count = sum(1 for s in recording_sessions.values() if s.get('is_active', False))
                    if active_count == 0:
                        # 没有活跃会话了，关闭全局录音缓存
                        recording_enabled = False
                        logger.info("[recording] 所有录音会话结束，已关闭音频缓存")
                    
                    # 提取音频数据（启用高质量音频）
                    audio_data = extract_audio_segment(session_id, use_hq=True)
                    
                    if audio_data:
                        # 保存到文件 - 统一使用相对于a4s目录的recordings路径
                        import os
                        recordings_dir = os.path.join(os.path.dirname(__file__), "recordings")
                        os.makedirs(recordings_dir, exist_ok=True)
                        
                        file_path = os.path.join(recordings_dir, session["filename"])
                        with open(file_path, "wb") as f:
                            f.write(audio_data)
                        
                        logger.info(f"[recording] 音频文件已保存到本地: {file_path}, 大小: {len(audio_data)} bytes")
                        
                        # 尝试发送给前端（如果连接正常）
                        try:
                            # 优化：先发送录音完成确认消息（不包含大数据），快速响应前端
                            await websocket.send_json({
                                "recording_completed": True,
                                "success": True,
                                "message": "录音已完成，正在准备下载",
                                "session_id": session_id,
                                "data": {
                                    "filename": session["filename"],
                                    "file_path": file_path,
                                    "duration": session["end_time"] - session["start_time"],
                                    "file_size": len(audio_data),
                                    "preparing_download": True
                                }
                            })
                            logger.info(f"[recording] 录音完成确认消息已发送")
                            
                            # 异步处理音频数据传输，避免阻塞主响应
                            try:
                                # 将音频数据转换为十六进制字符串用于传输
                                audio_hex = audio_data.hex()
                                
                                # 发送音频数据用于下载
                                await websocket.send_json({
                                    "audio_download_ready": True,
                                    "success": True,
                                    "session_id": session_id,
                                    "data": {
                                        "filename": session["filename"],
                                        "audio_data": audio_hex,
                                        "file_path": file_path,
                                        "duration": session["end_time"] - session["start_time"],
                                        "file_size": len(audio_data)
                                    }
                                })
                                logger.info(f"[recording] 音频下载数据已发送")
                            except Exception as download_error:
                                logger.warning(f"[recording] 音频下载数据发送失败: {download_error}")
                                # 发送下载失败通知，但录音已成功保存
                                try:
                                    await websocket.send_json({
                                        "audio_download_failed": True,
                                        "success": False,
                                        "message": f"音频文件已保存到本地，但下载失败: {download_error}",
                                        "session_id": session_id,
                                        "local_file": file_path
                                    })
                                except:
                                    logger.error(f"[recording] 无法发送下载失败通知")
                                    
                        except Exception as send_error:
                            logger.warning(f"[recording] 发送录音完成消息失败（连接可能断开）: {send_error}")
                            logger.info(f"[recording] 但音频文件已安全保存到: {file_path}")
                            
                            # 发送简单的成功响应（不包含音频数据）
                            try:
                                await websocket.send_json({
                                    "recording_completed": True,
                                    "success": True,
                                    "message": "录音已完成并保存到本地文件",
                                    "session_id": session_id,
                                    "local_file": file_path,
                                    "file_size": len(audio_data)
                                })
                            except:
                                logger.error(f"[recording] 无法发送任何响应，连接已断开。音频文件保存在: {file_path}")
                    else:
                        try:
                            await websocket.send_json({
                                "recording_completed": True,
                                "success": False,
                                "message": "未找到录音数据，可能录音时间太短或音频流中断"
                            })
                        except:
                            logger.error(f"[recording] 无法发送失败响应，连接已断开")
                    
                    # 清理会话缓存
                    if session_id in recording_audio_buffer:
                        del recording_audio_buffer[session_id]
                    if session_id in recording_timestamps:
                        del recording_timestamps[session_id]
                    del recording_sessions[session_id]
                    
                else:
                    await websocket.send_json({
                        "success": False,
                        "message": "未找到录音会话"
                    })
            
            elif "get_status" in data:
                # 获取录音状态
                active_sessions = {k: v for k, v in recording_sessions.items() if v.get('is_active', False)}
                total_buffer_size = sum(len(buf) for buf in recording_audio_buffer.values())
                
                await websocket.send_json({
                    "success": True,
                    "recording_enabled": recording_enabled,
                    "active_sessions": len(active_sessions),
                    "total_buffer_size": total_buffer_size,
                    "sessions": list(active_sessions.keys())
                })
                
    except WebSocketDisconnect:
        logger.info("[recording] client disconnected")
    except Exception as e:
        logger.error(f"[recording] error: {e}\n{traceback.format_exc()}")
        # 不要主动关闭连接，让客户端处理重连

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the FastAPI app with a specified port.")
    parser.add_argument('--port', type=int, default=27000, help='Port number to run the FastAPI app on.')
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)