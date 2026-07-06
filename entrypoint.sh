#!/bin/bash
# Check if Lavalink is disabled via environment variable
if [ "${DISABLE_LAVALINK}" = "true" ] || [ "${START_LAVALINK}" = "false" ]; then
    echo "Lavalink server launch skipped (DISABLE_LAVALINK=true or START_LAVALINK=false)."
else
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
fi

# Start the python Discord bot
exec python main.py
