# asr_server.py

from fastapi import FastAPI, WebSocket
import uvicorn

app = FastAPI()

@app.websocket("/ws/asr")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket 客户端已连接")

    try:
        while True:
            audio_data = await websocket.receive_bytes()
            print(f"收到音频数据，长度: {len(audio_data)} 字节")

            # 模拟返回识别结果（实际应集成语音识别模型）
            fake_text = "（模拟字幕）你好，这是测试字幕"
            await websocket.send_text(fake_text)

    except Exception as e:
        print("❌ WebSocket 连接关闭:", e)
    finally:
        await websocket.close()
        print("🔌 客户端断开连接")

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)
