#!/bin/bash
# Start Lavalink in the background with IPv4 stack preference
java -Djava.net.preferIPv4Stack=true -jar /app/Lavalink.jar &

# Wait for Lavalink to bind to port 2333 using python sockets
echo "Waiting for Lavalink to start on port 2333..."
python -c '
import socket
import time
while True:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("127.0.0.1", 2333))
        s.close()
        break
    except Exception:
        time.sleep(1)
'
echo "Lavalink is ready! Starting Discord bot..."

# Start the python Discord bot
exec python main.py
