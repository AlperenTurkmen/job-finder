"""Test with proper MCP protocol initialization."""
import asyncio
import json
import websockets
import os
from dotenv import load_dotenv

load_dotenv()

async def test_mcp_protocol():
    endpoint = os.getenv("BROWSERMCP_WS_ENDPOINT", "ws://localhost:9009")
    print(f"Connecting to: {endpoint}")
    
    try:
        async with websockets.connect(endpoint, ping_interval=None) as ws:
            print("✓ Connected!")
            
            # Step 1: Initialize
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {"listChanged": True},
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                }
            }
            
            print(f"\n→ Sending initialize")
            await ws.send(json.dumps(init_msg))
            
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            print(f"✓ Got response: {response[:200]}...")
            
            # Step 2: Send initialized notification
            initialized = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            
            print(f"\n→ Sending initialized notification")
            await ws.send(json.dumps(initialized))
            
            # Step 3: List tools
            list_tools = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list"
            }
            
            print(f"\n→ Sending tools/list")
            await ws.send(json.dumps(list_tools))
            
            response = await asyncio.wait_for(ws.recv(), timeout=5)
            result = json.loads(response)
            print(f"✓ Available tools: {json.dumps(result, indent=2)}")
            
            # Step 4: Call browser_navigate
            navigate = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "browser_navigate",
                    "arguments": {
                        "url": "https://example.com"
                    }
                }
            }
            
            print(f"\n→ Sending browser_navigate for https://example.com")
            await ws.send(json.dumps(navigate))
            
            print("⏳ Waiting for response...")
            response = await asyncio.wait_for(ws.recv(), timeout=30)
            result = json.loads(response)
            
            if "result" in result:
                content = result["result"]
                if isinstance(content, list) and len(content) > 0:
                    first_item = content[0]
                    if "text" in first_item:
                        text_preview = first_item["text"][:500]
                        print(f"\n✓ Got content ({len(first_item['text'])} chars):")
                        print(text_preview)
                    else:
                        print(f"\n✓ Result: {json.dumps(content, indent=2)[:500]}")
                else:
                    print(f"\n✓ Result: {json.dumps(result, indent=2)[:500]}")
            else:
                print(f"\n✓ Response: {json.dumps(result, indent=2)[:500]}")
                
    except asyncio.TimeoutError:
        print("✗ TIMEOUT")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_protocol())
