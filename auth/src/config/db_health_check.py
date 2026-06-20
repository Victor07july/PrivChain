import os
import re
import socket
import time

from dotenv import load_dotenv

load_dotenv()
env_path = os.path.join(os.getcwd(), "src/config/.env")

if os.path.exists(env_path):
    service_name = os.environ.get("DB_SERVICE_NAME", None)
    ip = os.environ.get("DB_HOST", None)
    port = os.environ.get("DB_PORT", None)
    if None not in (service_name, ip, port):
        while True:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((ip, int(port)))
            if result == 0:
                print("{0} port is open! Bye!".format(service_name))
                break
            else:
                print("{0} port is not open! I'll check it soon!".format(service_name))
                time.sleep(10)
    else:
        raise Exception("Database URL not found")
