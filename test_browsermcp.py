"""Quick test script to debug BrowserMCP WebSocket communication."""
import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

async def test_browsermcp():
    endpoint = os.getenv("BROWSERMCP_WS_ENDPOINT", "ws://localhost:9009")
    print(f"Connecting to: {endpoint}")
    
    try:
        async with websockets.connect(endpoint) as ws:
            print("✓ Connected successfully!")
            
            # First, try MCP initialization handshake
            init_request = {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "job-scraper-agent",
                        "version": "1.0.0"
                    }
                }
            }
            
            print(f"\n→ Sending initialize: {json.dumps(init_request, indent=2)}")
            await ws.send(json.dumps(init_request))
            
            print("⏳ Waiting for initialize response (5s timeout)...")
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=5)
                print(f"✓ Initialize response: {response}")
                
                # Send initialized notification
                initialized_notif = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }
                await ws.send(json.dumps(initialized_notif))
                print("✓ Sent initialized notification")
                
            except asyncio.TimeoutError:
                print("✗ No initialize response, trying without handshake...")
            
            # Try to list available tools
            list_tools_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
            
            print(f"\n→ Sending: {json.dumps(list_tools_request, indent=2)}")
            await ws.send(json.dumps(list_tools_request))
            
            print("⏳ Waiting for response (10s timeout)...")
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10)
                print(f"\n✓ Got response ({len(response)} bytes):")
                print(json.dumps(json.loads(response), indent=2))
            except asyncio.TimeoutError:
                print("✗ TIMEOUT: No response from server")
            
            # Now try browser_navigate with a simple page
            print("\n" + "="*60)
            navigate_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "browser_navigate",
                    "arguments": {
                        "url": "https://example.com",
                        "wait_for": "load"
                    }
                }
            }
            
            print(f"→ Sending: {json.dumps(navigate_request, indent=2)}")
            await ws.send(json.dumps(navigate_request))
            
            print("⏳ Waiting for response (15s timeout)...")
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(response)
                print(f"\n✓ Got response ({len(response)} bytes)")
                
                # Print result structure
                if "result" in data:
                    result = data["result"]
                    if isinstance(result, dict):
                        print(f"Result keys: {list(result.keys())}")
                        for key in ["content", "markdown", "text", "html"][:3]:
                            if key in result:
                                value = result[key]
                                preview = str(value)[:200] if value else "(empty)"
                                print(f"\n{key}: {preview}...")
                    else:
                        print(f"Result type: {type(result)}")
                        print(f"Result preview: {str(result)[:500]}")
                else:
                    print(f"Full response: {json.dumps(data, indent=2)[:1000]}")
                    
            except asyncio.TimeoutError:
                print("✗ TIMEOUT: No response from server")
                
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_browsermcp())
