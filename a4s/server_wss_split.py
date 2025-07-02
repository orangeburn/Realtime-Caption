# server_wss_split.py
# ✅ 基于 server_wss_original.py 重构，采用上传者/订阅者分离架构

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

# ===== 彻底移除 server_wss_original 依赖，直接在本文件定义所需变量和函数 =====
# 以下内容自动迁移自 server_wss_original.py，已适配本文件结构

class Config:
    chunk_size_ms = 300
    sample_rate = 16000
    bit_depth = 16
    channels = 1
    avg_logprob_thr = -0.25
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

# ASR与VAD模型加载
asr_pipeline = pipeline(
    task=Tasks.auto_speech_recognition,
    model='iic/SenseVoiceSmall',
    model_revision="master",
    device="cuda:0",
    disable_update=True
)
model_asr = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    remote_code="./model.py",    
    device="cuda:0",
    disable_update=True
)
model_vad = AutoModel(
    model="fsmn-vad",
    model_revision="v2.0.4",
    disable_pbar = True,
    max_end_silence_time=200,
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

TRANSLATE_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../nllb200_ct2'))
try:
    translator = ctranslate2.Translator(TRANSLATE_MODEL_PATH, device="cpu")
    logger.info(f"Loaded translation model from {TRANSLATE_MODEL_PATH} (cpu mode)")
    sp = spm.SentencePieceProcessor()
    sp.Load(os.path.join(TRANSLATE_MODEL_PATH, "sentencepiece.bpe.model"))
    logger.info("Loaded sentencepiece model for translation.")
except Exception as e:
    translator = None
    sp = None
    logger.error(f"Failed to load translation model: {e}")

def translate_text(text, src_lang="zh", tgt_lang="en"):
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

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

subscribers = set()
subscriber_langs = dict()  # 记录目标语言
latest_subscriber = None   # 只保留最新的订阅者
last_plain_text = None     # 最近一次的纯文本字幕
last_info_text = None     # 最近一次的 info 字幕
latest_device_list = []   # 新增：全局缓存最新设备列表
latest_uploader = None   # 新增：记录最新采集端连接

class TranscriptionResponse(BaseModel):
    code: int
    info: str
    data: str
    translated: str = ""

@app.websocket("/ws/subscribe")
async def subtitle_subscriber(websocket: WebSocket):
    global latest_subscriber, last_plain_text, last_info_text, latest_device_list, latest_uploader
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
    global latest_subscriber, last_plain_text, last_info_text, latest_device_list, latest_uploader
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
            msg = await websocket.receive()
            if msg['type'] == 'websocket.receive':
                if 'bytes' in msg:
                    data = msg['bytes']
                    buffer += data
                    if len(buffer) < 2:
                        continue

                    audio_buffer = np.append(
                        audio_buffer,
                        np.frombuffer(buffer[:len(buffer) - (len(buffer) % 2)], dtype=np.int16).astype(np.float32) / 32767.0
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
                                    last_vad_beg -= offset
                                    last_vad_end -= offset
                                    offset += last_vad_end
                                    beg = int(last_vad_beg * config.sample_rate / 1000)
                                    end = int(last_vad_end * config.sample_rate / 1000)
                                    logger.info(f"[vad segment] audio_len: {end - beg}")

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
                                        if latest_subscriber and latest_subscriber in subscriber_langs:
                                            tgt_lang_sub = subscriber_langs[latest_subscriber]
                                            logger.info(f"推送字幕，当前目标语言: {tgt_lang_sub}")
                                            try:
                                                translated = translate_text(plain_text, src_lang=src_lang, tgt_lang=tgt_lang_sub)
                                                logger.info(f"推送字幕内容 translated: {translated}")
                                            except Exception as e:
                                                logger.error(f"Translate error: {e}")
                                                translated = ""
                                            response = TranscriptionResponse(
                                                code=0,
                                                info=plain_text,  # 直接用原声
                                                data=plain_text,  # 直接用原声
                                                translated=translated
                                            )
                                            await latest_subscriber.send_json(response.model_dump())
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
                        # ...existing code...
                    except Exception as e:
                        logger.error(f"[upload] 文本消息解析失败: {e}")
            else:
                await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"[upload] error: {e}\n{traceback.format_exc()}")
        await websocket.close()
    finally:
        cache.clear()
        subscribers.clear()
        subscriber_langs.clear()
        latest_subscriber = None
        logger.info("[upload] Clean up completed")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the FastAPI app with a specified port.")
    parser.add_argument('--port', type=int, default=27000, help='Port number to run the FastAPI app on.')
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
