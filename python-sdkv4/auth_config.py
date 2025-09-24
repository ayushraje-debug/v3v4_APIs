from ntnx_vmm_py_client import * 
from decouple import config
import os

nutanix_config = Configuration()
nutanix_config.host = config('NUTANIX_HOST', os.environ.get('NUTANIX_HOST',''))
nutanix_config.port = config('NUTANIX_PORT',os.environ.get('NUTANIX_PORT',''))
nutanix_config.username = config('NUTANIX_USER',os.environ.get('NUTANIX_USER',''))
nutanix_config.password = config('NUTANIX_PASSWORD',os.environ.get('NUTANIX_PASSWORD',''))
nutanix_config.verify_ssl = False

api_client = ApiClient(configuration=nutanix_config)

def list_all_vms(api_client):

    response = VmApi(api_client).list_vms(0,5)
    return response

def assign_cat_to_vm(api_client):

    response = VmApi(api_client=api_client).associate_categories(extId="fa80e4a9-1825-4eb1-a910-f489ef99533a")

if __name__=='__main__':
    print(list_all_vms(api_client=api_client))