import requests
import urllib3
import datetime
import json
import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

# --- Setup ---
# Disable insecure request warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("rp_management.log", mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)

def filter_and_print_jobs(data, hours):
    """
    Filters jobs, prints them in a specific format, and returns the filtered list.
    """
    # --- Filtering Logic ---
    now_utc = datetime.now(timezone.utc)
    time_ago = now_utc - timedelta(hours=hours)
    filtered_jobs = []

    for job in data.get('entities', []):
        action_type = job.get('status', {}).get('resources', {}).get('execution_parameters', {}).get('action_type')
        start_time_str = job.get('status', {}).get('start_time')
        
        if action_type == 'MIGRATE' and start_time_str:
            job_start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if job_start_time >= time_ago:
                filtered_jobs.append(job)

    # --- Display the Results to Console (using print for clean formatting) ---
    print(f"\nFound {len(filtered_jobs)} matching failover jobs from the last {hours} hours:\n")

    if not filtered_jobs:
        print("No jobs matched your criteria.")
    else:
        # Sort by start time, newest first
        sorted_list = sorted(filtered_jobs, key=lambda j: j.get('status', {}).get('start_time'), reverse=True)
        
        for job in sorted_list:
            status = job['status']['execution_status']['status']
            name = job['status']['name']
            start_time = job['status']['start_time']
            uuid = job['metadata']['uuid']
            
            print(f"  Name: {name}")
            print(f"  UUID: {uuid}")
            print(f"  Status: {status}")
            print(f"  Start Time: {start_time}")
            
            print("  Affected Entities:")
            affected_entities = set()
            warnings = job.get('status',{}).get('validation_information',{}).get('warnings_list',[])
            
            for warning in warnings:
                for entity in warning.get('affected_any_reference_list', []):
                    entity_name = entity.get('name', 'N/A')
                    entity_kind = entity.get('kind', 'N/A')
                    affected_entities.add(f"- {entity_name} (Type: {entity_kind})")
            
            if affected_entities:
                for entity_str in sorted(list(affected_entities)):
                    print(f"    {entity_str}")
            else:
                print("    - No affected entities listed in warnings.")

            print("  Recovery Plan Specs:")
            spec = job.get('status', {}).get('recovery_plan_specification')
            if spec:
                description = spec.get('description') or "None"
                stage_count = len(spec.get('resources', {}).get('stage_list', []))
                print(f"    - Plan Name: {spec.get('name', 'N/A')}")
                print(f"    - Description: {description}")
                print(f"    - Number of Stages: {stage_count}")
            else:
                print("    - No specification data found.")

            print("-" * 40)
            
    # Return the list for saving
    return filtered_jobs

def get_all_recovery_plan_jobs(pc_ip, username, password):
    """
    Retrieves all recovery plan jobs by looping through paginated API results.
    """
    endpoint = f"https://{pc_ip}:9440/api/nutanix/v3/recovery_plan_jobs/list"
    all_jobs = []
    offset = 0
    page_length = 50
    logging.info(f"Starting to fetch all recovery plan jobs from {pc_ip}...")

    while True:
        payload = {
            "length": page_length, "offset": offset, "sort_order": "DESCENDING", "sort_attribute": "creation_time",
        }
        try:
            response = requests.post(
                endpoint, auth=(username, password), json=payload, verify=False, timeout=30
            )
            response.raise_for_status()
            data = response.json()
            entities = data.get('entities', [])
            all_jobs.extend(entities)
            if len(entities) < page_length:
                logging.info(f"Successfully fetched all jobs. Total found: {len(all_jobs)}.")
                break
            offset += page_length
        except requests.exceptions.RequestException as e:
            logging.error(f"API Error: Could not retrieve jobs. Reason: {e}")
            return {"entities": []}
            
    return {"entities": all_jobs}

def save_filtered_json(filtered_data, filename):
    """Saves the provided filtered data to a JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(filtered_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Filtered output for {len(filtered_data)} jobs saved to '{filename}'")
    except IOError as e:
        logging.error(f"Failed to write filtered JSON to file '{filename}': {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch, display, and save filtered Nutanix Recovery Plan Jobs.",
        formatter_class=argparse.HelpFormatter
    )
    parser.add_argument("--ip", required=True, help="IP address of the Prism Central.")
    parser.add_argument("--user", required=True, help="Username for Prism Central.")
    parser.add_argument("--password", required=True, help="Password for the user.")
    parser.add_argument(
        "--hours", type=int, default=24, help="Time window in hours to filter jobs (default: 24)."
    )
    args = parser.parse_args()

    # --- Main Execution Logic ---
    all_job_data = get_all_recovery_plan_jobs(args.ip, args.user, args.password)
    
    if all_job_data and all_job_data.get('entities') is not None:
        filtered_job_list = filter_and_print_jobs(all_job_data, args.hours)
        
        if filtered_job_list:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"rp_jobs_last_{args.hours}_hr_{timestamp}.json"
            save_filtered_json(filtered_job_list, filename)
    else:
        logging.warning("No recovery plan jobs were found on the system or the API call failed.")