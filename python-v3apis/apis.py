from get_set_auth_header import set_headers
import requests
from decouple import config
import pandas as pd
import logging
import sys

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
def get_vms():
    payload = """{
        "kind": "vm",
        "length": 100,
        "offset": 0,
        "sort_attribute": "",
        "sort_order": "ASCENDING"
    }"""

    request_url = f"{config('BASE_URL')}/vms/list"
    try:
        response = session.post(url=request_url, data=payload)
        response.raise_for_status()
        logging.info("Fetched VMs successfully.")
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching VMs: {e}")
        return {"entities": []}


# ------------------- Filter VMs by Name -------------------
def filter_vms_on_name(vm_names=[]):
    try:
        all_vms = get_vms().get('entities', [])
        logging.info(f"Total VMs fetched: {len(all_vms)}")
        filtered_vms = []
        for vm in all_vms:
            if vm.get('status', {}).get('name') in vm_names:
                logging.info(f"Matched VM UUID: {vm['metadata'].get('uuid')}")
                filtered_vms.append(vm)
        return filtered_vms
    except Exception as e:
        logging.error(f"Error while filtering VMs: {e}")
        return []


# ------------------- Read VM Category Mapping File -------------------
def get_vm_category_mapping_from_file(filepath):
    """
    CSV file structure:
    name, category, value
    <vm_name>, <category_name>, <category_value>
    """
    try:
        df = pd.read_csv(filepath_or_buffer=filepath)
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




# ------------------- Example Usage -------------------
if __name__ == "__main__":
    file_path = r"/Users/ayush.raje/Documents/Book1.csv"
    vm_names, vm_category_mapping = get_vm_category_mapping_from_file(filepath=file_path)

    if vm_names and vm_category_mapping:
        result = add_vms_to_categories(vm_names=vm_names, vm_category_mapping=vm_category_mapping)
        logging.info(result)
    else:
        logging.warning("No VM category mapping loaded; skipping category assignment.")
