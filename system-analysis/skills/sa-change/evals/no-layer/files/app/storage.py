import os
import boto3

s3 = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT"))
BUCKET = os.environ["S3_BUCKET"]


def put(key: str, data: bytes) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=data)


def presigned(key: str) -> str:
    return s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600)
