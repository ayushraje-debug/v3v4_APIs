# ------------------- Configure Logging -------------------
import logging
import sys
import requests
from .get_set_auth_header import set_headers
from decouple import config

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# ------------------- Set Auth Headers -------------------
try:
    set_headers()
except Exception as e:
    logging.error(f"Failed to set headers: {e}")
    sys.exit(1)
headers = {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Authorization': f"{config('AUTH_HEADER')}",
    'cache-control': 'no-cache',
}
session = requests.Session()
session.verify = False
session.headers.update(headers)