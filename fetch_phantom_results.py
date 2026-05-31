import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import urllib.request
import urllib.error
import csv

PHANTOM_API_KEY = "XceHVJ04vbODSP26xqltTlMtcUWmG4yRwoJXDeG845g"
AGENT_ID = "950568112893709"
S3_FOLDER = "4IcQxOVDThFpVMKnrjLSpA"
OUTPUT_FILE = r"C:\Users\Shaul\Documents\job-search\phantom_recruiters.csv"


def api_get(url):
    req = urllib.request.Request(url, headers={"X-Phantombuster-Key": PHANTOM_API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def try_url(url):
    try:
        req = urllib.request.Request(url, headers={"X-Phantombuster-Key": PHANTOM_API_KEY})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {url}")
        return None
    except Exception as e:
        print(f"  Error: {e}: {url}")
        return None


def main():
    # Get last container (run) for this agent
    print("Fetching containers...")
    containers = api_get(f"https://api.phantombuster.com/api/v2/containers/fetch-all?agentId={AGENT_ID}")
    print(f"Found {len(containers)} containers")

    if not containers:
        print("No containers found")
        return

    # Use the most recent container
    last = containers[0]
    container_id = last.get("id")
    print(f"Last container ID: {container_id}")
    print(f"Status: {last.get('lastEndType')}, ended: {last.get('lastEndTime')}")

    # Try to get result object from S3
    candidate_urls = [
        f"https://phantombuster.s3.amazonaws.com/{S3_FOLDER}/{container_id}/result_object.json",
        f"https://phantombuster.s3.amazonaws.com/{S3_FOLDER}/{AGENT_ID}/result_object.json",
        f"https://cache1.phantombooster.com/{S3_FOLDER}/{container_id}/result_object.json",
    ]

    for url in candidate_urls:
        print(f"\nTrying: {url}")
        data = try_url(url)
        if data:
            print(f"  Got {len(data)} bytes")
            try:
                profiles = json.loads(data)
                if isinstance(profiles, list):
                    print(f"  Parsed {len(profiles)} profiles!")
                    save_profiles(profiles)
                    return
                else:
                    print(f"  Not a list: {type(profiles)}")
                    print(str(profiles)[:300])
            except Exception as e:
                print(f"  JSON parse error: {e}")
                print(data[:300])

    # Try fetch-result-object with container id
    print("\nTrying containers/fetch-result-object...")
    try:
        result = api_get(f"https://api.phantombuster.com/api/v2/containers/fetch-result-object?id={container_id}")
        print("Keys:", list(result.keys()) if isinstance(result, dict) else type(result))
        if isinstance(result, list):
            print(f"Got {len(result)} profiles!")
            save_profiles(result)
            return
        if isinstance(result, dict):
            for k, v in result.items():
                val_str = str(v)[:200]
                print(f"  {k}: {val_str}")
    except Exception as e:
        print(f"  Error: {e}")


def save_profiles(profiles):
    fields = ["firstName", "lastName", "companyName", "linkedinProfileUrl", "linkedinJobTitle", "location"]
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for p in profiles:
            writer.writerow({k: p.get(k, "") for k in fields})
    print(f"\nSaved {len(profiles)} profiles to phantom_recruiters.csv")


if __name__ == "__main__":
    main()
