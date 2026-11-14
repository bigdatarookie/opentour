"""Read-only, masked projection probe for the PR24 disposable Espo instance."""
import argparse
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--private-directory', required=True, type=Path)
parser.add_argument('--expect', required=True, choices=['exposed', 'hidden'])
args = parser.parse_args()
ROOT = args.private_directory.resolve()
if ROOT != Path('/private/tmp/opentour-pr24-qa-8fd750743b215cd4'):
    parser.error('only the existing QA-owned disposable project is allowed')
SECRETS = ROOT / "secrets"
BASE = "http://127.0.0.1:60601/api/v1"
FIELD = "cOpenTourControlTitle"
USERNAME = "qa-system-reader"

password = (SECRETS / "synthetic-user-password").read_text().strip()
writer = json.loads((SECRETS / "writer-reference.json").read_text())
contact_id = writer["contactId"]


def request(path, auth_header, auth_value):
    req = urllib.request.Request(
        BASE + path,
        headers={auth_header: auth_value},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        # Inspect the denial body too: a failure status must not hide returned data.
        raw = error.read().decode('utf-8', errors='replace')
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {'_nonJsonBody': raw}
        return error.code, body if isinstance(body, dict) else {'_body': body}


credentials = base64.b64encode(f"{USERNAME}:{password}".encode()).decode()
login_status, identity = request("/App/user", "Espo-Authorization", credentials)
if login_status != 200 or not identity.get("token"):
    print(json.dumps({"loginStatus": login_status, "projectionChecks": "NOT RUN"}))
    raise SystemExit(1)

user_auth = base64.b64encode(
    f"{USERNAME}:{identity['token']}".encode()
).decode()
list_status, listing = request("/Contact?maxSize=20", "Espo-Authorization", user_auth)
detail_status, detail = request(
    "/Contact/" + urllib.parse.quote(contact_id), "Espo-Authorization", user_auth
)
query = urllib.parse.urlencode({"select": f"id,{FIELD}", "maxSize": "20"})
selected_status, selected = request(
    "/Contact?" + query, "Espo-Authorization", user_auth
)
control_status, control = request(
    "/OpenTourControlTitle",
    "X-OpenTour-Control",
    writer["token"],
)

list_row = next(
    (row for row in listing.get("list", []) if row.get("id") == contact_id), {}
)
selected_row = next(
    (row for row in selected.get("list", []) if row.get("id") == contact_id), {}
)
control_value = control.get("title") if control_status == 200 else None

result = {
    "loginStatus": login_status,
    "defaultListStatus": list_status,
    "defaultListContainsControlField": FIELD in list_row,
    "defaultListMatchesScopedValue": FIELD in list_row
    and list_row.get(FIELD) == control_value,
    "detailStatus": detail_status,
    "detailContainsControlField": FIELD in detail,
    "detailMatchesScopedValue": FIELD in detail
    and detail.get(FIELD) == control_value,
    "explicitSelectStatus": selected_status,
    "explicitSelectContainsControlField": FIELD in selected_row,
    "explicitSelectMatchesScopedValue": FIELD in selected_row
    and selected_row.get(FIELD) == control_value,
    "scopedReadStatus": control_status,
    "scopedReadNamesControlField": control.get("field") == FIELD,
    "onlySyntheticContactReturned": all(
        row.get("id") == contact_id for row in listing.get("list", [])
    ),
}
def filtered(attribute, value):
    # PHP parses this supported nested-array shape into where[0], not a scalar.
    query = urllib.parse.urlencode({
        'where[0][type]': 'equals',
        'where[0][attribute]': attribute,
        'where[0][value]': value,
        'maxSize': '20',
    })
    return request('/Contact?' + query, 'Espo-Authorization', user_auth)


first_name = detail.get('firstName')
normal_status, normal_data = filtered('firstName', first_name or '')
normal_rows = normal_data.get('list', [])
normal_filter_passed = (
    bool(first_name) and normal_status == 200 and len(normal_rows) == 1
    and normal_rows[0].get('id') == contact_id
    and normal_rows[0].get('firstName') == first_name
)
filter_status, filter_data = filtered(FIELD, control_value or '')
filter_body = json.dumps(filter_data, ensure_ascii=False)
filter_no_records = (
    not filter_data.get('list') and not filter_data.get('total')
    and contact_id not in filter_body
)
filter_no_value = bool(control_value) and control_value not in filter_body
filter_denied = filter_status in (400, 403) and filter_no_records and filter_no_value
result['normalFirstNameFilterStatus'] = normal_status
result['normalFirstNameFilterPassed'] = normal_filter_passed
result['controlFieldFilterStatus'] = filter_status
result['controlFieldFilterHasNoRecords'] = filter_no_records
result['controlFieldFilterHasNoValue'] = filter_no_value
result['controlFieldFilterDenied'] = filter_denied
projections = [(list_status, list_row), (detail_status, detail), (selected_status, selected_row)]
positive = control_status == 200 and control.get('field') == FIELD and bool(control_value)
if args.expect == 'exposed':
    passed = positive and normal_filter_passed and all(status == 200 and FIELD in row and row[FIELD] == control_value for status, row in projections)
else:
    passed = positive and normal_filter_passed and list_status == detail_status == 200 and bool(list_row) and bool(detail) and all(status in (200, 403) and FIELD not in row for status, row in projections) and filter_denied
result['expectedBoundary'] = args.expect
result['passed'] = passed
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if passed else 1)
