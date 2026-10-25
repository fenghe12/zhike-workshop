"""Create a private, expiring OBS multipart plan without publishing credentials."""
import argparse
import json
import os
from pathlib import Path

from obs import ObsClient

parser = argparse.ArgumentParser()
parser.add_argument('--bucket', required=True)
parser.add_argument('--endpoint', required=True)
parser.add_argument('--object', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--parts', type=int, default=768)
parser.add_argument('--expires', type=int, default=10800)
args = parser.parse_args()
client = ObsClient(access_key_id=os.environ['OBS_ACCESS_KEY_ID'],
                   secret_access_key=os.environ['OBS_SECRET_ACCESS_KEY'],
                   server=args.endpoint, timeout=20, max_retry_count=1)
try:
    response = client.initiateMultipartUpload(args.bucket, args.object, acl='private')
    if response.status >= 300:
        raise RuntimeError('Cannot initiate private checkpoint upload')
    identifier = response.body.uploadId
    def signed(method, query=None):
        return client.createSignedUrl(method, args.bucket, args.object,
                                      expires=args.expires, queryParams=query or {}).signedUrl
    plan = {'object': args.object, 'part_bytes': 64 * 1024 * 1024,
            'part_urls': [signed('PUT', {'uploadId': identifier, 'partNumber': str(index)})
                          for index in range(1, args.parts + 1)],
            'complete_url': signed('POST', {'uploadId': identifier}),
            'head_url': signed('HEAD'), 'read_url': signed('GET')}
    path = Path(args.output).expanduser().resolve()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(plan, stream)
finally:
    client.close()
print('Private checkpoint plan created. Keep it outside version control.')
