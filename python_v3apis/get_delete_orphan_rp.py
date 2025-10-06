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
import argparse

# --- Global Settings ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# --- Helper Functions (Updated to accept URLs and session) ---

def get_vm_details(session: requests.Session, vm_uuid: str, vm_cache: dict, base_url: str, base_url_dr: str) -> tuple:
    """
    Fetches VM name and status with specific logic, using a cache.
    """
    if vm_uuid in vm_cache:
        return vm_cache[vm_uuid]

    vm_detail_url = f"{base_url}/vms/{vm_uuid}"
    vm_detail_url_dr = f"{base_url_dr}/vms/{vm_uuid}"

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

def delete_rps_in_parallel(rp_uuids_to_delete: list, session: requests.Session, base_url: str):
    """
    Deletes a list of recovery points in parallel using a passed session.
    """
    if not rp_uuids_to_delete:
        logging.info("No recovery point UUIDs provided for deletion.")
        return

    logging.info(f"Preparing to delete {len(rp_uuids_to_delete)} recovery points...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_rp = {
            executor.submit(session.delete, f"{base_url}/vm_recovery_points/{rp_uuid}"): rp_uuid
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

def fetch_all_rps(session: requests.Session, base_url: str, base_url_dr: str) -> pd.DataFrame:
    """
    Fetches all recovery points and their details, returning them as a pandas DataFrame.
    """
    headers = ["Recovery Point Name", "RP UUID", "VM Name", "Status"]
    data_rows = []
    vm_details_cache = {}
    offset = 0
    page_length = 500

    logging.info("Fetching all recovery points...")
    while True:
        list_payload = {"kind": "vm_recovery_point", "offset": offset, "length": page_length}
        try:
            list_url = f"{base_url}/vm_recovery_points/list"
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
                detail_url = f"{base_url}/vm_recovery_points/{rp_uuid}"
                rp_detail_resp = session.get(detail_url)
                if rp_detail_resp.status_code != 200:
                    continue
                
                rp_data = rp_detail_resp.json()
                rp_name = rp_data.get("status", {}).get("name", "Name not assigned")
                vm_uuid = rp_data.get("spec", {}).get("resources", {}).get("parent_vm_reference", {}).get("uuid")

                if not vm_uuid:
                    continue

                vm_name, status = get_vm_details(session, vm_uuid, vm_details_cache, base_url, base_url_dr)
                data_rows.append([rp_name, rp_uuid, vm_name, status])

            except Exception as e:
                logging.error(f"An error occurred processing RP {rp_uuid}: {e}")

        offset += page_length
    
    if not data_rows:
        return pd.DataFrame(columns=headers)
    
    return pd.DataFrame(data_rows, columns=headers)


def main():
    """Main function to run the script with argument parsing and interactive workflow."""
    
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Manage Nutanix VM Recovery Points. Reads from .env file if args are not provided."
    )
    parser.add_argument('--pc_ip', help="Primary Prism Central IP address.",
                        default=config('NUTANIX_HOST', default=None))
    parser.add_argument('--pc_ip_dr', help="DR Prism Central IP address. Defaults to primary if not set.",
                        default=config('NUTANIX_HOST_DR', default=None))
    parser.add_argument('--username', help="Nutanix username.",
                        default=config('NUTANIX_USER', default=None))
    parser.add_argument('--password', help="Nutanix password.",
                        default=config('NUTANIX_PASSWORD', default=None))
    args = parser.parse_args()

    # --- Logging Setup ---
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("rp_management.log", mode='a'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info("--- Script started ---")

    # --- Validate credentials and IPs ---
    if not all([args.pc_ip, args.username, args.password]):
        logging.critical("Error: PC IP, Username, and Password are required. "
                         "Provide them as command-line arguments or in a .env file.")
        sys.exit(1)

    pc_ip_dr = args.pc_ip_dr if args.pc_ip_dr else args.pc_ip
    base_url = f"https://{args.pc_ip}:9440/api/nutanix/v3"
    base_url_dr = f"https://{pc_ip_dr}:9440/api/nutanix/v3"

    # --- Create a shared session for all API calls ---
    session = requests.Session()
    session.auth = HTTPBasicAuth(args.username, args.password)
    session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    session.verify = False

    # --- Part 1: Fetch data and create the report ---
    logging.info(f"Step 1: Fetching all recovery point data from the cluster at {args.pc_ip}...")
    all_rps_df = fetch_all_rps(session, base_url, base_url_dr)

    if all_rps_df.empty:
        logging.info("No recovery points were found on the cluster. Exiting.")
        return

    excel_file = "recovery_points.xlsx"
    all_rps_df.to_excel(excel_file, index=False, engine='openpyxl')
    logging.info(f"Step 2: Report complete. All VM recovery points can be found at '{excel_file}'")

    # --- Part 2: Deletion Workflow ---
    print("\n--- Recovery Point Deletion Menu ---")
    print("Select which recovery points to delete based on their status:")
    print("  1. RPs of 'Deleted' VMs")
    print("  2. RPs of VMs that are 'at Primary Site'")
    print("  3. RPs of VMs that are 'Migrated'")
    print("  4. RPs for a custom list of VMs from an Excel file")

    choice = input("Enter your choice (1-4): ")
    
    # ... (rest of the interactive menu logic is unchanged)
    
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

    print("\n\n!! CAUTION !!")
    print(f"You are about to permanently delete {len(rp_uuid_list)} recovery points.")
    print(f"Please review '{final_list_path}' carefully before proceeding.")

    confirm = input("\nType 'YES' to confirm and proceed with the deletion: ")
    if confirm == "YES":
        delete_rps_in_parallel(rp_uuid_list, session, base_url)
        logging.info("Deletion process completed.")
    else:
        logging.info("Deletion cancelled by user.")
    
    logging.info("--- Script finished ---")


if __name__ == '__main__':
    main()