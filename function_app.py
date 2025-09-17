import os
import json
import logging
from typing import Dict, Any, Optional

import azure.functions as func
import requests

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# --- Autotask connection details ---
AT_BASE = os.environ["AT_BASE"].rstrip("/")
AT_API_INTEGRATION_CODE = os.environ["AT_API_INTEGRATION_CODE"]
AT_API_USERNAME = os.environ["AT_API_USERNAME"]
AT_API_SECRET = os.environ["AT_API_SECRET"]

HEADERS = {
    "Content-Type": "application/json",
    "ApiIntegrationCode": AT_API_INTEGRATION_CODE,
    "UserName": AT_API_USERNAME,
    "Secret": AT_API_SECRET,
}

# ---------- Helpers ----------
def _http_post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
    if r.status_code != 200:
        logging.error("POST %s -> %s\n%s", url, r.status_code, r.text[:1000])
    r.raise_for_status()
    return r.json()

def _collect_companies() -> list[Dict[str, Any]]:
    """
    Query all companies from Autotask, following pagination until exhausted.
    """
    url = f"{AT_BASE}/Companies/query"
    payload = {
        "MaxRecords": 500,
        "IncludeFields": ["id", "companyName"],
        "Filter": [
            {"op": "gte", "field": "id", "value": 1}
        ]
    }

    results = []
    # first page
    data = _http_post(url, payload)
    results.extend(data.get("items", []))

    # follow pagination using nextPageUrl
    next_url = data.get("pageDetails", {}).get("nextPageUrl")
    while next_url:
        r = requests.get(next_url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        d = r.json()
        results.extend(d.get("items", []))
        next_url = d.get("pageDetails", {}).get("nextPageUrl")

    shaped = [{"CompanyID": c["id"], "CompanyName": c["companyName"]} for c in results]
    return shaped

# ---------- HTTP Trigger ----------
@app.function_name(name="autotask_companies")
@app.route(route="autotask/companies", auth_level=func.AuthLevel.FUNCTION)
def autotask_companies(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/autotask/companies
    Returns a JSON array of {CompanyID, CompanyName}
    """
    try:
        companies = _collect_companies()
        body = json.dumps(companies, ensure_ascii=False, indent=2)
        return func.HttpResponse(body=body, mimetype="application/json", status_code=200)

    except requests.HTTPError as e:
        return func.HttpResponse(f"Upstream API error: {e}", status_code=502)
    except Exception as e:
        logging.exception("Unhandled error")
        return func.HttpResponse(f"Error: {e}", status_code=500)