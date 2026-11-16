import os
from .database import DATA

def s3():
    import boto3
    return boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'], aws_access_key_id=os.environ['S3_ACCESS_KEY'], aws_secret_access_key=os.environ['S3_SECRET_KEY'])

def put(key, data):
    if os.getenv('S3_ENDPOINT'):
        s3().put_object(Bucket=os.getenv('S3_BUCKET','knowledge'), Key=key, Body=data)
    else:
        p = DATA / 'files' / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

def get(key):
    if os.getenv('S3_ENDPOINT'):
        return s3().get_object(Bucket=os.getenv('S3_BUCKET','knowledge'), Key=key)['Body'].read()
    return (DATA / 'files' / key).read_bytes()

def entries(prefix):
    """(key, last-modified epoch seconds) of every stored object whose key starts with prefix (a folder ending in '/')."""
    if os.getenv('S3_ENDPOINT'):
        for page in s3().get_paginator('list_objects_v2').paginate(Bucket=os.getenv('S3_BUCKET','knowledge'), Prefix=prefix):
            for item in page.get('Contents', []): yield item['Key'], item['LastModified'].timestamp()
    else:
        root = DATA / 'files'
        folder = root / prefix
        if folder.is_dir():
            for path in folder.rglob('*'):
                if path.is_file(): yield path.relative_to(root).as_posix(), path.stat().st_mtime

def remove(key):
    if os.getenv('S3_ENDPOINT'): s3().delete_object(Bucket=os.getenv('S3_BUCKET','knowledge'),Key=key)
    else: (DATA / 'files' / key).unlink(missing_ok=True)
