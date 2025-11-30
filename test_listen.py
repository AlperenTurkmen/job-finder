"""Listen to see what BrowserMCP sends."""
import asyncio
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

async def listen_browsermcp():
    endpoint = os.getenv("BROWSERMCP_WS_ENDPOINT", "ws://localhost:9009")
    print(f"Connecting to: {endpoint}")
    
    try:
        async with websockets.connect(endpoint) as ws:
            print("✓ Connected! Listening for any messages for 5 seconds...")
            
            try:
                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=5)
                    print(f"\n📨 Received: {message}")
            except asyncio.TimeoutError:
                print("\n⏱️  No messages received in 5 seconds")
                
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(listen_browsermcp())
