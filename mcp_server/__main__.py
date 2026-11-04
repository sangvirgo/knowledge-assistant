import sys

from .server import mcp

if __name__ == "__main__":
    mcp.run("streamable-http" if "--http" in sys.argv else "stdio")
