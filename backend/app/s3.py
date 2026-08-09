from dataclasses import dataclass
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


def download_media(key: str, dest: Path) -> None:
    _client().download_file(settings.s3_bucket, key, str(dest))


def presign_get_url(key: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def presign_put_url(key: str, content_type: str, expires_in: int = 3600) -> str:
    # Single-shot upload for small files (ticket screenshots) — multipart
    # is overkill for anything under a few MB and would trip the daily
    # recording upload quota, which has nothing to do with bug reports.
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


@dataclass
class UploadedPart:
    part_number: int
    etag: str
    size: int


def create_multipart_upload(key: str, content_type: str) -> str:
    response = _client().create_multipart_upload(
        Bucket=settings.s3_bucket, Key=key, ContentType=content_type
    )
    return response["UploadId"]


def presign_upload_part_url(key: str, upload_id: str, part_number: int, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "UploadId": upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=expires_in,
    )


def list_uploaded_parts(key: str, upload_id: str) -> list[UploadedPart]:
    parts: list[UploadedPart] = []
    paginator = _client().get_paginator("list_parts")
    for page in paginator.paginate(Bucket=settings.s3_bucket, Key=key, UploadId=upload_id):
        for part in page.get("Parts", []):
            parts.append(UploadedPart(part_number=part["PartNumber"], etag=part["ETag"], size=part["Size"]))
    return parts


def complete_multipart_upload(key: str, upload_id: str, parts: list[UploadedPart]) -> None:
    _client().complete_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={
            "Parts": [{"PartNumber": p.part_number, "ETag": p.etag} for p in sorted(parts, key=lambda p: p.part_number)]
        },
    )


def abort_multipart_upload(key: str, upload_id: str) -> None:
    _client().abort_multipart_upload(Bucket=settings.s3_bucket, Key=key, UploadId=upload_id)


def delete_media(key: str) -> None:
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)
