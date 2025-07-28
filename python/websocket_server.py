import asyncio
import websockets

async def handler(websocket):
    print("客户端已连接")
    try:
        async for message in websocket:
            print(f"收到音频数据字节数: {len(message)}")
    except websockets.exceptions.ConnectionClosed:
        print("客户端断开连接")

async def main():
    print("WebSocket 服务已启动，监听端口 27000")
    async with websockets.serve(handler, "localhost", 27000):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
