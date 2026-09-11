import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.core.config import settings


class ObjectStorage:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
        self.bucket = settings.s3_bucket

    def ensure_bucket(self):
        buckets = {b["Name"] for b in self.client.list_buckets().get("Buckets", [])}
        if self.bucket not in buckets:
            self.client.create_bucket(Bucket=self.bucket)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def put_immutable(self, key: str, data: bytes, content_type: str):
        if self.exists(key):
            raise FileExistsError(f"Immutable object already exists: {key}")
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_many(self, keys: list[str]) -> None:
        """Delete a bounded document object set in one storage request."""
        unique_keys = list(dict.fromkeys(key for key in keys if key))
        if not unique_keys:
            return
        response = self.client.delete_objects(
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": key} for key in unique_keys], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"Object cleanup failed for {len(errors)} item(s)")

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()


storage = ObjectStorage()
