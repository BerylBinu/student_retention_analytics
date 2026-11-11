"""Cloud Run function entry point for the processor.

Google Cloud calls handle_upload() every time a file is created in the raw bucket.
All the real work lives in app.py, so it can be tested without Google Cloud.
"""

import functions_framework

from app import handle_storage_event


@functions_framework.cloud_event
def handle_upload(cloud_event):
    handle_storage_event(cloud_event.data or {})
