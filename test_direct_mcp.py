"""Direct test of Browser MCP stdio connection."""
import asyncio
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp import ClientSession

async def test_direct():
    server_params = StdioServerParameters(
        command="/Users/alperenturkmen/.nvm/versions/node/v22.21.1/bin/mcp-server-browsermcp",
        args=[],
        env=None
    )
    
    print("Starting Browser MCP server...")
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        print("✓ Server started")
        
        async with ClientSession(read_stream, write_stream) as session:
            print("✓ Session created")
            
            # Initialize
            await session.initialize()
            print("✓ Session initialized")
            
            # List tools
            tools_result = await session.list_tools()
            print(f"\n✓ Available tools:")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Try to call browser_navigate
            print(f"\n→ Calling browser_navigate for https://example.com")
            try:
                result = await session.call_tool("browser_navigate", {"url": "https://example.com"})
                
                print(f"\n✓ Result type: {type(result)}")
                print(f"✓ Result attributes: {dir(result)}")
                
                if hasattr(result, 'content'):
                    print(f"\n✓ Content type: {type(result.content)}")
                    for i, item in enumerate(result.content):
                        print(f"\n  Content item {i}:")
                        print(f"    Type: {type(item)}")
                        if hasattr(item, 'text'):
                            print(f"    Text preview: {item.text[:200]}")
                
                if hasattr(result, 'isError'):
                    print(f"\n✓ isError: {result.isError}")
                    
            except Exception as e:
                print(f"\n✗ Error: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct())
