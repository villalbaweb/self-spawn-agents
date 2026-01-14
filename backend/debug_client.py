import requests
import json
import sys

URL = "http://localhost:8000/api/run"
TASK = "Test connectivity and flux"

def debug_stream():
    print(f"Connecting to {URL}...")
    try:
        response = requests.post(URL, json={"task": TASK}, stream=True)
        print(f"Response Status: {response.status_code}")
        
        if response.status_code != 200:
            print(response.text)
            return

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    try:
                        data = json.loads(json_str)
                        print(f"EVENT: {data['type']}")
                        if data['type'] == 'start':
                            print(f"  -> Run ID: {data.get('run_id')}")
                        elif data['type'] == 'blueprint':
                            print(f"  -> Blueprint ID: {data.get('id')}")
                        elif data['type'] == 'error':
                            print(f"  -> ERROR: {data.get('message')}")
                    except json.JSONDecodeError:
                        print(f"RAW: {decoded_line}")
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")

if __name__ == "__main__":
    debug_stream()
