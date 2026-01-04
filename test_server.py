
from server_unified import start_unified_server
import time
import logging

# Configure logging to see output
logging.basicConfig(level=logging.INFO)

print("Starting server...")
t = start_unified_server()
print("Server started. Press Ctrl+C to stop.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
