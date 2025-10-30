#!/usr/bin/env python3
"""Debug QuickMiner API raw response."""

import socket
import json

print("Testing raw connection to QuickMiner's excavator...")
print()

try:
    # Connect to IPv6 localhost on port 18000
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(("::1", 18000))
    
    # Send info command
    cmd = {"id": 1, "method": "info", "params": []}
    message = json.dumps(cmd) + "\n"
    print(f"Sending: {message.strip()}")
    
    sock.sendall(message.encode())
    
    # Receive response
    response = b""
    while True:
        chunk = sock.recv(1024)
        if not chunk or b"\n" in chunk:
            response += chunk
            break
        response += chunk
    
    sock.close()
    
    print(f"Raw response: {response}")
    print()
    print(f"Decoded: {response.decode('utf-8', errors='ignore')}")
    print()
    
    # Try to parse as JSON
    try:
        data = json.loads(response.decode())
        print(f"Parsed JSON:")
        print(json.dumps(data, indent=2))
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
