import os
import json
import firebase_admin
from firebase_admin import credentials, firestore as _firestore, storage
from google.cloud.firestore import Client as FirestoreClient

def init_firebase() -> None:
    try:
        firebase_admin.get_app()
    except ValueError:
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if not sa_json:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not set")
        cred = credentials.Certificate(json.loads(sa_json))
        bucket = os.getenv("FIREBASE_STORAGE_BUCKET")
        if bucket:
            firebase_admin.initialize_app(cred, {
                "storageBucket": bucket
            })
        else:
            firebase_admin.initialize_app(cred)

def get_db() -> FirestoreClient:
    """
    Return a Firestore client.
    """
    return _firestore.client()

def get_storage_bucket():
    """
    Return the default Storage bucket.
    """
    return storage.bucket()