from pathlib import Path

import boto3
from botocore.config import Config

from app.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def presign_put_url(key: str, content_type: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def download_media(key: str, dest: Path) -> None:
    _client().download_file(settings.s3_bucket, key, str(dest))
