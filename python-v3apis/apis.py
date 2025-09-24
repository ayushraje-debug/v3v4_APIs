from get_set_auth_header import set_headers
import requests
from decouple import config
import pandas as pd
import logging
import sys
import os
import subprocess
from getpass import getpass
import paramiko

# ------------------- Configure Logging -------------------
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
# ------------------- Get VMs -------------------
def get_vms(total_vms=2000, page_size=500):
    all_vms = []
    request_url = f"{config('BASE_URL')}/vms/list"
    for offset in range(0, total_vms, page_size):
        payload = {
            "kind": "vm",
            "length": page_size,
            "offset": offset,
            "sort_attribute": "",
            "sort_order": "ASCENDING"
        }
        try:
            logging.info(f"[INFO] Fetching VMs: offset={offset}, length={page_size}")
            response = session.post(url=request_url, json=payload)
            response.raise_for_status()
            entities = response.json().get("entities", [])
            logging.info(f"[SUCCESS] Retrieved {len(entities)} VMs at offset {offset}")
            all_vms.extend(entities)
            # If fewer than page_size results are returned, you're done
            if len(entities) < page_size:
                break
        except requests.exceptions.RequestException as e:
            logging.error(f"[ERROR] Failed to fetch VMs at offset {offset}: {e}")
            break
    logging.info(f"[INFO] Total VMs fetched: {len(all_vms)}")
    return all_vms
# ------------------- Filter VMs by Name -------------------
def filter_vms_on_name(vm_names=[]):
    try:
        all_vms = get_vms()
        logging.info(f"Total VMs fetched: {len(all_vms)}")
        filtered_vms = []
        for vm in all_vms:
            is_capital = False
            if vm.get('status', {}).get('name') in vm_names:
                logging.info(f"Matched VM UUID: {vm['metadata'].get('uuid')}")
                filtered_vms.append(vm)                 
        
    except Exception as e:
        logging.error(f"Error while filtering VMs: {e}")
        return []
    return filtered_vms
# ------------------- Read VM Category Mapping File -------------------
def get_vm_category_mapping_from_file(filepath):
    """
    CSV file structure:
    name, category, value
    <vm_name>, <category_name>, <category_value>
    """
    try:
        _, ext = os.path.splitext(filepath)

        if ext.lower() == ".csv":
            df = pd.read_csv(filepath)
        elif ext.lower() in [".xls", ".xlsx"]:
            df = pd.read_excel(filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        if not all(col in df.columns for col in ['name', 'category', 'value']):
            logging.error("CSV file must contain 'name', 'category', and 'value' columns.")
            return [], {}
        vm_names = list(df['name'])
        vm_category_dict = {
            row['name']: {'category': row['category'], 'value': row['value']}
            for _, row in df.iterrows()
        }
        logging.info(f"[SUCCESS] Loaded category mapping for {len(vm_names)} VMs from file.")
        return vm_names, vm_category_dict
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
    except pd.errors.ParserError as e:
        logging.error(f"CSV parsing error: {e}")
    except Exception as e:
        logging.error(f"Unexpected error reading file: {e}")
    return [], {}
# ------------------- Assign Categories -------------------
def add_vms_to_categories(vm_names=[], vm_category_mapping={}):
    """
    vm_category_mapping = {
        <vm_name>: {
            'category': <category_name>,
            'value': <category_value>
        },
        ...
    }
    """
    filtered_vms = filter_vms_on_name(vm_names=vm_names)
    print(len(filtered_vms))
    print(len(vm_names))
    for vm in filtered_vms:
        try:
            vm_name = vm['status']['name']
            metadata = vm.get('metadata', {})
            categories = metadata.get('categories', {})
            category = vm_category_mapping[vm_name]['category']
            value = vm_category_mapping[vm_name]['value']
            if category in categories and categories[category] == value:
                logging.info(f"[SKIP] VM '{vm_name}' already has category '{category}={value}'")
                continue
            logging.info(f"Updating VM '{vm_name}' with category '{category}={value}'")
            categories[category] = value
            request_url = f"{config('BASE_URL')}/vms/{metadata['uuid']}"
            payload = {
                "metadata": metadata,
                "spec": vm['spec']
            }
            response = session.put(url=request_url, json=payload)
            if response.ok:
                logging.info(f"[SUCCESS] VM '{vm_name}' updated with category '{category}={value}'")
            else:
                logging.error(f"[ERROR] Failed to update VM '{vm_name}': {response.status_code} - {response.text}")
        except KeyError as e:
            logging.error(f"[ERROR] Missing expected key: {e}")
        except Exception as e:
            logging.error(f"[ERROR] Unexpected error updating VM '{vm.get('status', {}).get('name', 'UNKNOWN')}': {e}")
    return "[SUCCESS] Category assignment process completed."

def parse_recovery_points(text):
    """
    Parses text protobuf from polaris_cli list_recovery_points output.
    Extracts:
      - VM name (from live_entity_list)
      - Recovery point UUID (from recovery_point_list.properties)
      - VM recovery point UUID (from vm_recovery_point_list.properties)
    """
    recovery_points = []
    current = {}
    context_stack = []

    for line in text.splitlines():
        line = line.strip()

        # skip headers
        if line.startswith(">>>") or line.startswith("ListRecoveryPoints returned"):
            continue

        if line.endswith("{"):
            context_stack.append(line.split()[0])
        elif line == "}":
            if context_stack:
                context_stack.pop()
            if not context_stack and current:
                recovery_points.append(current)
                current = {}
        elif line.startswith("uuid:"):
            uuid_val = line.split("uuid:")[1].strip().strip('"')
            if context_stack[-1] == "properties":
                if len(context_stack) >= 2 and context_stack[-2] == "recovery_point_list":
                    current["recovery_point_uuid"] = uuid_val
                elif len(context_stack) >= 2 and context_stack[-2] == "vm_recovery_point_list":
                    current["vm_recovery_point_uuid"] = uuid_val
        elif line.startswith("name:"):
            name_val = line.split("name:")[1].strip().strip('"')
            if context_stack and context_stack[-1] == "live_entity_list":
                current["vm_name"] = name_val
        elif line.startswith("status:"):
            current["status"] = line.split("status:")[1].strip()
        elif line.startswith("total_user_written_bytes:"):
            current["total_user_written_bytes"] = int(line.split(":")[1].strip())
        elif line.startswith("total_exclusive_usage_bytes:"):
            current["total_exclusive_usage_bytes"] = int(line.split(":")[1].strip())

    return recovery_points




def remove_orphan_recovery_points(filepath):
    


    host = config("CVM_IP")
    username = "nutanix"
    password = config("CVM_PASSWORD")  

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # for first-time hosts
    ssh.connect(hostname=host, username=username, password=password, look_for_keys=False)
    stdin, stdout, stderr = ssh.exec_command("/home/nutanix/bin/polaris_cli list_recovery_points")
    json_rp = parse_recovery_points(stdout.read().decode())
    print(len(json_rp))

    # with open("recovery_point_list.json" ,"w+") as file:
    #     file.write(stdout.read().decode())
    # print(stdout.read().decode())
    # print(stderr.read())
    print(json_rp)
    ssh.close()

# ------------------- Example Usage -------------------
if __name__ == "__main__":


    # file_path = r"C:\Automation\VM_Category\v3v4_APIs\python-v3apis\test_csv.csv"
    # vm_names, vm_category_mapping = get_vm_category_mapping_from_file(filepath=file_path)
    # if vm_names and vm_category_mapping:
    #     result = add_vms_to_categories(vm_names=vm_names, vm_category_mapping=vm_category_mapping)
    #     logging.info(result)
    # else:
    #     logging.warning("No VM category mapping loaded; skipping category assignment.")
    remove_orphan_recovery_points("None")