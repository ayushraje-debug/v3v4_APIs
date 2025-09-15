import urllib3
import requests
import os
from decouple import config
from base64 import b64encode
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def set_headers():
    if len(config('AUTH_HEADER')) < 1:
        username = config('NUTANIX_USER')
        password = config('NUTANIX_PASSWORD')
        encoded_credentials = b64encode(bytes(f'{username}:{password}',
                            encoding='ascii')).decode('ascii')
        
        auth_header = f'Basic {encoded_credentials}'
        os.environ['AUTH_HEADER'] = auth_header
    else:
        pass


        