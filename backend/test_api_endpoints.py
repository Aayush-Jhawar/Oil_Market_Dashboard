import os
import sys
from fastapi.testclient import TestClient
sys.path.insert(0, os.path.abspath("backend"))
from main import app
import json

client = TestClient(app)
paths = [
    '/api/prices/all',
    '/api/prices/instruments',
    '/api/eia/weekly',
    '/api/eia/weekly-history',
    '/api/eia/weekly-anchor',
    '/api/analytics/forward-curve',
    '/api/analytics/correlations',
    '/api/signals/composite',
    '/api/signals/enhanced',
    '/api/news/enhanced',
    '/api/news/sentiment-summary',
    '/api/alerts/active',
]
for path in paths:
    try:
        response = client.get(path)
        out = {
            'path': path,
            'status_code': response.status_code,
            'status': response.json().get('status'),
            'count': response.json().get('count', 'n/a'),
            'timestamp': response.json().get('timestamp', 'n/a'),
        }
        print(json.dumps(out))
    except Exception as e:
        print(json.dumps({'path': path, 'error': str(e)}))
