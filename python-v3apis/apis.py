
from get_set_auth_header import set_headers
import requests
from decouple import config
import pandas as pd
set_headers()
headers = {
    'Accept': 'application/json', 
    'Content-Type': 'application/json',
    'Authorization': f'{config('AUTH_HEADER')}', 
    'cache-control': 'no-cache',
    
}
session = requests.Session()
session.verify = False
session.headers.update(headers)

def get_vms():
    payload =  """{
        "kind": "vm",
        "length": 100,
        "offset": 0,
        "sort_attribute": "",
        "sort_order": "ASCENDING"
    }"""

    request_url = f"{config('BASE_URL')}/vms/list"
    response = session.post(url=request_url,data=payload)

    return response.json()

def filter_vms_on_name(vm_names = []):
    all_vms = get_vms()['entities']
    print(len(all_vms))
    filtered_vms = []
    for vm in all_vms:
        if vm['status']['name'] in vm_names:
            print(vm['metadata']['uuid'])
            print("___________________")
            filtered_vms.append(vm)
    return filtered_vms

# print(filter_vms_on_name(["Windows_1_v2","Windows_1_v3"]))

def get_vm_category_mapping_from_file(filepath):
    """
    

    """

    df = pd.read_csv(filepath_or_buffer= filepath)
    vm_names = list(df['name'])

    vm_category_dict = {}
    for index, i in df.iterrows():
        vm_category_dict[i['name']] = {
            'category': i['category'],
            'value': i['value']
        }

    return vm_names,vm_category_dict


def add_vms_to_categories(vm_names = [],vm_category_mapping = {}):
    """
    vm_category_mapping = {
        <vm_name> : {
            <category_name> : <category_value>
        },
        ...
    }
    vm_names = [<vm_name_1>,<vm_name_2>,....]
    """

    filtered_vms = filter_vms_on_name(vm_names=vm_names)
    
    for vm in filtered_vms:
        if vm_category_mapping[vm['status']['name']]['category'] in vm['metadata']['categories']:
            continue
        else:
            print(vm_category_mapping[vm['status']['name']]['category'])
            print(vm['metadata']['categories'])
            print("__________________")
            vm['metadata']['categories'][vm_category_mapping[vm['status']['name']]['category']] = vm_category_mapping[vm['status']['name']]['value']
            print(vm['metadata']['categories'][vm_category_mapping[vm['status']['name']]['category']])
            request_url = f"{config('BASE_URL')}/vms/{vm['metadata']['uuid']}"
            print("_____________________")
            print(request_url)
            
            payload = {
                "metadata" : vm['metadata'],
                "spec" : vm['spec']
            }
            print(payload)
            
            response = session.put(url=request_url,json=payload)
            print(response.json())
    return "Successful"


# print(session.get(url="https://10.38.81.7:9440/api/nutanix/v3/vms/735e5f09-4bb8-46cf-bf39-d6d7d50931df").json())
# print(add_vms_to_categories())
file_path = r"/Users/ayush.raje/Documents/Book1.csv"
print(get_vm_category_mapping_from_file(filepath=file_path))

        
