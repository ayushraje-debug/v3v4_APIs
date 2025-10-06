from python_v3apis import *
import argparse

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

if __name__ == '__main__':
    

    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--total_vms", type=int, help="Enter total number of vms to fetch", default=2000)
    parser.add_argument("--page_size", type=int, help="keep default until specific usage is required", default=500)
    args = parser.parse_args()

    print(get_vms(args.total_vms, args.page_size))
    