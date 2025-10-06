import requests
import openpyxl
import pandas as pd
from decouple import config
from requests.auth import HTTPBasicAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import urllib3
import sys
import logging

# --- Configuration ---
# Create a .env file in the same directory with these values
# NUTANIX_HOST=192.168.1.10
# NUTANIX_HOST_DR=192.168.1.11
# NUTANIX_USER=your_username
# NUTANIX_PASSWORD=your_password

 # Configure logging to write to a file and to the console
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
            logging.FileHandler("rp_management.log", mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )

try:
    PC_IP = config('NUTANIX_HOST')
    PC_IP_DR = config('NUTANIX_HOST_DR', default=PC_IP)
    USERNAME = config('NUTANIX_USER')
    PASSWORD = config('NUTANIX_PASSWORD')
except Exception as e:
    logging.critical(f"Failed to load configuration from .env file. Please ensure it exists and is correctly formatted. Details: {e}")
    sys.exit(1)


# --- Global Settings ---
BASE_URL = f"https://{PC_IP}:9440/api/nutanix/v3"
BASE_URL_DR = f"https://{PC_IP_DR}:9440/api/nutanix/v3"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# --- Helper Functions (with logging) ---

def get_vm_details(session: requests.Session, vm_uuid: str, vm_cache: dict) -> tuple:
    """
    Fetches VM name and status with specific logic, using a cache.
    """
    if vm_uuid in vm_cache:
        return vm_cache[vm_uuid]

    vm_detail_url = f"{BASE_URL}/vms/{vm_uuid}"
    vm_detail_url_dr = f"{BASE_URL_DR}/vms/{vm_uuid}"

    try:
        vm_resp = session.get(vm_detail_url)
        if vm_resp.status_code == 200:
            vm_name = vm_resp.json().get("status", {}).get("name", "Name Missing")
            status = "VM at Primary Site"
            vm_cache[vm_uuid] = (vm_name, status)
            return vm_name, status
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not connect to primary site for VM {vm_uuid}: {e}")

    try:
        vm_resp_dr = session.get(vm_detail_url_dr)
        if vm_resp_dr.status_code == 200:
            vm_name = vm_resp_dr.json().get("status", {}).get("name", "Name Missing")
            status = "VM Migrated"
            vm_cache[vm_uuid] = (vm_name, status)
            return vm_name, status
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not connect to DR site for VM {vm_uuid}: {e}")

    vm_name = "VM Deleted"
    status = "Deleted"
    vm_cache[vm_uuid] = (vm_name, status)
    return vm_name, status

def delete_rps_in_parallel(rp_uuids_to_delete: list):
    """
    Deletes a list of recovery points in parallel using a thread pool.
    """
    if not rp_uuids_to_delete:
        logging.info("No recovery point UUIDs provided for deletion.")
        return

    logging.info(f"Preparing to delete {len(rp_uuids_to_delete)} recovery points...")
    
    with requests.Session() as session:
        session.auth = HTTPBasicAuth(USERNAME, PASSWORD)
        session.verify = False
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_rp = {
                executor.submit(session.delete, f"{BASE_URL}/vm_recovery_points/{rp_uuid}"): rp_uuid
                for rp_uuid in rp_uuids_to_delete
            }
            
            for future in tqdm(as_completed(future_to_rp), total=len(rp_uuids_to_delete), desc="Deleting RPs"):
                rp_uuid = future_to_rp[future]
                try:
                    response = future.result()
                    if response.status_code not in [200, 202, 204]:
                        logging.error(f"Deletion failed for {rp_uuid}: Status {response.status_code} - {response.text}")
                except Exception as exc:
                    logging.error(f"An error occurred while deleting {rp_uuid}: {exc}")


# --- Main Logic ---

def fetch_all_rps() -> pd.DataFrame:
    """
    Fetches all recovery points and their details, returning them as a pandas DataFrame.
    """
    headers = ["Recovery Point Name", "RP UUID", "VM Name", "Status"]
    data_rows = []
    vm_details_cache = {}
    offset = 0
    page_length = 500

    with requests.Session() as session:
        session.auth = HTTPBasicAuth(USERNAME, PASSWORD)
        session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
        session.verify = False

        logging.info("Fetching all recovery points...")
        while True:
            list_payload = {"kind": "vm_recovery_point", "offset": offset, "length": page_length}
            try:
                list_url = f"{BASE_URL}/vm_recovery_points/list"
                resp = session.post(list_url, json=list_payload)
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to fetch RP list: {e}")
                break

            rps_list = resp.json().get("entities", [])
            if not rps_list:
                break

            logging.info(f"Processing {len(rps_list)} recovery points (total fetched so far: {offset + len(rps_list)})...")
            
            for rp_summary in tqdm(rps_list, desc="Processing batch", leave=False):
                rp_uuid = rp_summary.get("metadata", {}).get("uuid")
                if not rp_uuid:
                    continue

                try:
                    detail_url = f"{BASE_URL}/vm_recovery_points/{rp_uuid}"
                    rp_detail_resp = session.get(detail_url)
                    if rp_detail_resp.status_code != 200:
                        continue
                    
                    rp_data = rp_detail_resp.json()
                    rp_name = rp_data.get("status", {}).get("name", "Name not assigned")
                    vm_uuid = rp_data.get("spec", {}).get("resources", {}).get("parent_vm_reference", {}).get("uuid")

                    if not vm_uuid:
                        continue

                    vm_name, status = get_vm_details(session, vm_uuid, vm_details_cache)
                    data_rows.append([rp_name, rp_uuid, vm_name, status])

                except Exception as e:
                    logging.error(f"An error occurred processing RP {rp_uuid}: {e}")

            offset += page_length
    
    if not data_rows:
        return pd.DataFrame(columns=headers)
    
    return pd.DataFrame(data_rows, columns=headers)


def main():
    """Main function to run the script with the new interactive workflow."""
    
    logging.info("--- Script started ---")
    
    # --- Part 1: Fetch data and create the report ---
    logging.info("Step 1: Fetching all recovery point data from the cluster...")
    all_rps_df = fetch_all_rps()

    if all_rps_df.empty:
        logging.info("No recovery points were found on the cluster. Exiting.")
        return

    excel_file = "recovery_points.xlsx"
    all_rps_df.to_excel(excel_file, index=False, engine='openpyxl')
    logging.info(f"Step 2: Report complete. All VM recovery points can be found at '{excel_file}'")

    # --- Part 2: New Deletion Workflow (using print for clean user interaction) ---
    print("\n--- Recovery Point Deletion Menu ---")
    print("Select which recovery points to delete based on their status:")
    print("  1. RPs of 'Deleted' VMs")
    print("  2. RPs of VMs that are 'at Primary Site'")
    print("  3. RPs of VMs that are 'Migrated'")
    print("  4. RPs for a custom list of VMs from an Excel file")

    choice = input("Enter your choice (1-4): ")

    filtered_rps = pd.DataFrame()
    status_map = {
        '1': 'Deleted',
        '2': 'VM at Primary Site',
        '3': 'VM Migrated'
    }

    if choice in status_map:
        chosen_status = status_map[choice]
        logging.info(f"Filtering for RPs with status: '{chosen_status}'")
        filtered_rps = all_rps_df[all_rps_df['Status'] == chosen_status]
    
    elif choice == '4':
        try:
            vm_file = input("Enter the path to the Excel file containing VM names: ")
            df_vms_to_delete = pd.read_excel(vm_file)
            vm_list_to_delete = df_vms_to_delete["VM Name"].dropna().astype(str).str.strip().tolist()
            logging.info(f"Filtering for RPs belonging to {len(vm_list_to_delete)} VMs from '{vm_file}'")
            filtered_rps = all_rps_df[all_rps_df["VM Name"].astype(str).str.strip().isin(vm_list_to_delete)]
        except FileNotFoundError:
            logging.error(f"The file '{vm_file}' was not found. Please check the path and try again.")
            return
        except Exception as e:
            logging.error(f"An error occurred while processing the Excel file: {e}")
            return
    else:
        logging.warning("Invalid choice. Exiting.")
        return

    # --- Part 3: Confirmation and Deletion ---
    if filtered_rps.empty:
        logging.info("No recovery points found matching your criteria. Nothing to delete.")
        return

    final_list_path = "final_rps_for_deletion.xlsx"
    filtered_rps.to_excel(final_list_path, index=False)
    logging.info(f"A list of all RPs that will be deleted has been saved to '{final_list_path}'.")

    rp_uuid_list = filtered_rps["RP UUID"].dropna().astype(str).tolist()

    # Use print for the CAUTION message to make it stand out
    print("\n\n!! CAUTION !!")
    print(f"You are about to permanently delete {len(rp_uuid_list)} recovery points.")
    print(f"Please review '{final_list_path}' carefully before proceeding.")

    confirm = input("\nType 'YES' to confirm and proceed with the deletion: ")
    if confirm == "YES":
        delete_rps_in_parallel(rp_uuid_list)
        logging.info("Deletion process completed.")
    else:
        logging.info("Deletion cancelled by user.")
    
    logging.info("--- Script finished ---")


if __name__ == '__main__':
    main()