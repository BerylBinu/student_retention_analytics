"""Cloud Run function entry point for the dashboard API.

Google Cloud calls handle_http() for every web request. This file only deals with HTTP details
(CORS, JSON); the routes and logic live in app.py so they can be tested without Google Cloud.
"""

import json
import os

import functions_framework

from app import handle_request

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
CORS_HEADERS = {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Admin-Token",
    "Access-Control-Max-Age": "600",
}


@functions_framework.http
def handle_http(request):
    # Browsers send an OPTIONS "preflight" request before a cross-site POST. Answer it with the CORS rules.
    if request.method == "OPTIONS":
        return "", 204, CORS_HEADERS

    status, body = handle_request(
        method=request.method,
        path=request.path,
        params=request.args.to_dict(),
        body_text=request.get_data(as_text=True),
        headers=dict(request.headers),
    )
    headers = {**CORS_HEADERS, "Content-Type": "application/json"}
    return json.dumps(body, ensure_ascii=False, default=str), status, headers
