import json, os, time, urllib.request, pathlib, sys

MATRIX_TOKEN = os.environ.get("MATRIX_TOKEN", "")
MATRIX_SERVER = "https://human.tech"
ROOM_ID = "!VcEuZFypPvYyYsRDIG:human.tech"

report = pathlib.Path("/tmp/daily-report.txt").read_text()
txn_id = str(int(time.time() * 1000))
room_encoded = ROOM_ID.replace("!", "%21").replace(":", "%3A")
url = f"{MATRIX_SERVER}/_matrix/client/v3/rooms/{room_encoded}/send/m.room.message/{txn_id}"

payload = json.dumps({"msgtype": "m.text", "body": report}).encode("utf-8")
req = urllib.request.Request(
    url,
    data=payload,
    headers={"Authorization": f"Bearer {MATRIX_TOKEN}", "Content-Type": "application/json"},
    method="PUT",
)

try:
    resp = urllib.request.urlopen(req)
    print("Matrix delivery SUCCESS:", resp.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"Matrix delivery FAILED: HTTP {e.code} — {body}", file=sys.stderr)
    sys.exit(1)
