# ------------------- Imports -------------------
import requests
from decouple import config
import pandas as pd
import logging
import sys
import os
from base64 import b64encode
import urllib3
import argparse
from tqdm import tqdm

# ------------------- Configure Logging -------------------
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("category_management.log", mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------- Get VMs -------------------
def get_vms(session, base_url, total_vms=2000, page_size=500):
    """Fetches all VMs from the cluster using pagination."""
    all_vms = []
    request_url = f"{base_url}/vms/list"
    logging.info("Starting to fetch all VMs from the cluster...")
    for offset in range(0, total_vms, page_size):
        payload = {"kind": "vm", "length": page_size, "offset": offset}
        try:
            logging.info(f"Fetching VMs: offset={offset}, length={page_size}")
            response = session.post(url=request_url, json=payload)
            response.raise_for_status()
            entities = response.json().get("entities", [])
            logging.info(f"Successfully retrieved {len(entities)} VMs in this batch.")
            all_vms.extend(entities)
            if len(entities) < page_size:
                break
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch VMs at offset {offset}: {e}")
            break
    logging.info(f"Total unique VMs fetched: {len(all_vms)}")
    return all_vms

# ------------------- Filter VMs by Name -------------------
def filter_vms_on_name(session, base_url, vm_names=[]):
    """Filters the full list of VMs against a list of names."""
    try:
        all_vms = get_vms(session, base_url)
        filtered_vms = [vm for vm in all_vms if vm.get('status', {}).get('name') in vm_names]
        logging.info(f"Matched {len(filtered_vms)} VMs from the provided list.")
        return filtered_vms
    except Exception as e:
        logging.error(f"An unexpected error occurred while filtering VMs: {e}")
        return []

# ------------------- Read VM Category Mapping File -------------------
def get_vm_category_mapping_from_file(filepath):
    """Reads a CSV or Excel file to get VM-to-category mappings."""
    try:
        _, ext = os.path.splitext(filepath)
        if ext.lower() == ".csv":
            df = pd.read_csv(filepath)
        elif ext.lower() in [".xls", ".xlsx"]:
            df = pd.read_excel(filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        if not all(col in df.columns for col in ['name', 'category', 'value']):
            logging.error("Input file must contain 'name', 'category', and 'value' columns.")
            return [], {}
        
        vm_names = list(df['name'])
        vm_category_dict = {
            row['name']: {'category': row['category'], 'value': row['value']}
            for _, row in df.iterrows()
        }
        logging.info(f"Successfully loaded category mapping for {len(vm_names)} VMs from file.")
        return vm_names, vm_category_dict
    except FileNotFoundError:
        logging.error(f"File not found: {filepath}")
    except Exception as e:
        logging.error(f"Unexpected error reading file: {e}")
    return [], {}

# ------------------- Assign Categories -------------------
def apply_categories_to_vms(session, base_url, vms_to_update=[], vm_category_mapping={}):
    """Applies categories to a given list of VM objects with a progress bar."""
    success_count, skipped_count, error_count = 0, 0, 0

    for vm in tqdm(vms_to_update, desc="Applying Categories", unit="VM", ncols=100):
        try:
            vm_name = vm['status']['name']
            metadata = vm.get('metadata', {})
            categories = metadata.get('categories', {})
            category = vm_category_mapping[vm_name]['category']
            value = vm_category_mapping[vm_name]['value']
            
            if category in categories and categories[category] == value:
                logging.info(f"Skipping VM '{vm_name}': already has category '{category}={value}'.")
                skipped_count += 1
                continue
            
            logging.info(f"Applying category '{category}={value}' to VM '{vm_name}'.")
            metadata.setdefault('categories', {})[category] = value
            
            request_url = f"{base_url}/vms/{metadata['uuid']}"
            payload = {"metadata": metadata, "spec": vm['spec']}
            
            response = session.put(url=request_url, json=payload)
            if response.ok:
                logging.info(f"Successfully updated VM '{vm_name}'.")
                success_count += 1
            else:
                logging.error(f"Failed to update VM '{vm_name}': {response.status_code} - {response.text}")
                error_count += 1
        except KeyError as e:
            logging.error(f"Missing data for VM '{vm.get('status', {}).get('name', 'UNKNOWN')}': {e}")
            error_count += 1
        except Exception as e:
            logging.error(f"Unexpected error updating VM '{vm.get('status', {}).get('name', 'UNKNOWN')}': {e}")
            error_count += 1
            
    summary = (f"Final Summary -> Successful: {success_count}, Skipped: {skipped_count}, Failed: {error_count}")
    return summary

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Add VMs to Categories based on a file. Reads from .env file if args are not provided."
    )
    parser.add_argument("--file", type=str, required=True, help="Path to the CSV or Excel file with VM category mappings.")
    parser.add_argument("--pc_ip", type=str, default=config('NUTANIX_HOST', default=None), help="Prism Central IP address.")
    parser.add_argument("--username", type=str, default=config('NUTANIX_USER', default=None), help="Prism Central username.")
    parser.add_argument("--password", type=str, default=config('NUTANIX_PASSWORD', default=None), help="Prism Central password.")
    args = parser.parse_args()

    if not all([args.pc_ip, args.username, args.password]):
        logging.critical("PC IP, Username, and Password are required. Provide them via command-line or in a .env file.")
        sys.exit(1)
        
    base_url = f"https://{args.pc_ip}:9440/api/nutanix/v3"
    encoded_credentials = b64encode(bytes(f'{args.username}:{args.password}', 'ascii')).decode('ascii')
    auth_header = f'Basic {encoded_credentials}'
    
    session = requests.Session()
    session.verify = False
    session.headers.update({
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': auth_header,
        'cache-control': 'no-cache',
    })

    vm_names, vm_category_mapping = get_vm_category_mapping_from_file(args.file)
    if not vm_names or not vm_category_mapping:
        logging.critical("No valid VM names or mappings found in the file. Exiting.")
        sys.exit(1)

    logging.info("Step 1: Identifying VMs to be updated...")
    vms_to_update = filter_vms_on_name(session, base_url, vm_names=vm_names)

    if not vms_to_update:
        logging.info("No VMs matching the names in the file were found on the cluster. Nothing to do.")
        sys.exit(0)

    # --- Confirmation Step ---
    print("\n" + "="*70)
    logging.info(f"Found {len(vms_to_update)} VMs that will be affected by this operation.")
    print(f"\nFound {len(vms_to_update)} VMs to update. Please review the logs above.")
    confirm = input("Type 'YES' to proceed with applying categories: ")
    print("="*70 + "\n")

    if confirm == 'YES':
        logging.info("User confirmed. Step 2: Applying categories...")
        result_summary = apply_categories_to_vms(session, base_url, vms_to_update=vms_to_update, vm_category_mapping=vm_category_mapping)
        logging.info(result_summary)
    else:
        logging.info("Operation cancelled by the user.")