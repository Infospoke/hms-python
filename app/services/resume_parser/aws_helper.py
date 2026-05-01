import logging
import base64
from io import BytesIO
import boto3
from botocore.exceptions import ClientError
import app.core.config as consts

logger = logging.getLogger(__name__)

# S3 Configuration
_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    try:
        if consts.AWS_REGION and consts.AWS_ACCESS_KEY and consts.AWS_SECRET_KEY:
            _s3_client = boto3.client(
                "s3",
                region_name=consts.AWS_REGION,
                aws_access_key_id=consts.AWS_ACCESS_KEY,
                aws_secret_access_key=consts.AWS_SECRET_KEY,
            )
        else:
            logger.warning(
                "AWS credentials not fully provided. Falling back to default boto3 session."
            )
            _s3_client = boto3.client("s3")
    except Exception as e:
        logger.error(f"Failed to initialize S3 client: {e}")
    return _s3_client


def fetch_resume(resume_name):
    logger.info(f"S3: fetching resume '{resume_name}'")
    try:
        s3_client = get_s3_client()
        bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
        response = s3_client.get_object(Bucket=bucket_name, Key=resume_name)
        file_content = response["Body"].read()
        file_stream = BytesIO(file_content)
        file_size_mb = len(file_content) / (1024 * 1024)
        file_extension = "." + resume_name.split(".")[-1] if "." in resume_name else ""
        file_name = str(resume_name.split("/")[-1])
        logger.info(f"S3: successfully fetched '{resume_name}' ({file_size_mb:.2f} MB)")
        return {
            "success": True,
            "file_stream": file_stream,
            "file_size_mb": file_size_mb,
            "resume_name": resume_name,
            "file_name": file_name,
            "file_extension": file_extension,
        }
    except Exception as e:
        logger.error(f"S3: fetch error for '{resume_name}': {e}")
        return {"success": False, "error": f"Failed to fetch resume from S3: {e}"}


def upload_file_to_s3(file_path, object_name=None):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    if object_name is None:
        object_name = file_path.split("/")[-1]

    logger.info(f"S3: uploading file '{file_path}' as '{object_name}'")
    try:
        s3_client = get_s3_client()
        s3_client.upload_file(file_path, bucket_name, object_name)
        s3_url = (
            f"https://{bucket_name}.s3.{consts.AWS_REGION}.amazonaws.com/{object_name}"
        )
        logger.info(f"S3: successfully uploaded file to {s3_url}")
        return {
            "success": True,
            "s3_url": s3_url,
        }
    except Exception as e:
        logger.error(f"S3: error uploading file '{file_path}': {e}")
        return {"success": False, "error": f"Failed to upload file to S3: {e}"}


def upload_image_to_s3(image_content, object_name):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    logger.info(f"S3: uploading image content as '{object_name}'")
    try:
        s3_client = get_s3_client()
        s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=image_content,
            ContentType="image/jpeg",
        )
        s3_url = (
            f"https://{bucket_name}.s3.{consts.AWS_REGION}.amazonaws.com/{object_name}"
        )
        logger.info(f"S3: successfully uploaded image to {s3_url}")
        return {
            "success": True,
            "s3_url": s3_url,
        }
    except Exception as e:
        logger.error(f"S3: error uploading image '{object_name}': {e}")
        return {"success": False, "error": f"Failed to upload image to S3: {e}"}


def list_proctoring_images(interview_session_id=None):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    prefix = "ai-interviews/proctoring/"
    if interview_session_id:
        prefix += f"{interview_session_id}/"

    logger.info(f"S3: listing objects with prefix '{prefix}'")
    try:
        s3_client = get_s3_client()
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

        images = []
        for page in pages:
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    image_name = key.split("/")[-1]
                    s3_url = f"https://{bucket_name}.s3.{consts.AWS_REGION}.amazonaws.com/{key}"
                    images.append(
                        {
                            "image_name": image_name,
                            "s3_key": key,
                            "s3_url": s3_url,
                            "last_modified": obj["LastModified"].isoformat(),
                            "size": obj["Size"],
                        }
                    )
        logger.info(f"S3: found {len(images)} images")
        return {"success": True, "images": images}
    except Exception as e:
        logger.error(f"S3: error listing objects: {e}")
        return {"success": False, "error": f"Failed to list S3 objects: {e}"}


def extract_s3_key(image_key: str):
    if "amazonaws.com/" in image_key:
        return image_key.split("amazonaws.com/")[1]
    if "localhost:9000/" in image_key:
        parts = image_key.split("localhost:9000/")
        if len(parts) > 1:
            key_part = parts[1]
            bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
            if key_part.startswith(f"{bucket_name}/"):
                return key_part[len(f"{bucket_name}/") :]
            return key_part
    return image_key


def get_s3_image_base64(image_key: str):
    logger.info(f"S3: retrieving base64 for key '{image_key}'")
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    try:
        if "amazonaws.com/" in image_key:
            image_key = image_key.split("amazonaws.com/")[1]

        image_key = (
            image_key.split(f"/{bucket_name}/")[-1]
            if f"/{bucket_name}/" in image_key
            else image_key
        )
        image_key = image_key.lstrip("/")

        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=bucket_name, Key=image_key)
        image_bytes = response["Body"].read()
        content_type = response.get("ContentType", "image/jpeg")
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info(f"S3: successfully retrieved and encoded image '{image_key}'")
        return f"data:{content_type};base64,{base64_image}"
    except Exception as e:
        logger.error(f"S3: unexpected error in get_image_base64 for '{image_key}': {e}")
        return None


def upload_audio_to_s3(audio_bytes: bytes, s3_key: str) -> dict:
    """Upload raw WAV bytes directly to S3. Returns dict with success/s3_key."""
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    logger.info(f"S3: uploading audio ({len(audio_bytes)} bytes) as '{s3_key}'")
    try:
        s3_client = get_s3_client()
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=audio_bytes,
            ContentType="audio/wav",
        )
        logger.info(f"S3: audio uploaded successfully → {s3_key}")
        return {"success": True, "s3_key": s3_key}
    except Exception as e:
        logger.error(f"S3: error uploading audio '{s3_key}': {e}")
        return {"success": False, "error": str(e)}


def get_audio_bytes_from_s3(s3_key: str) -> dict:
    """Fetch audio bytes from S3 in memory — no local disk write at all."""
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    logger.info(f"S3: fetching audio bytes for '{s3_key}'")
    try:
        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        audio_bytes = response["Body"].read()
        logger.info(f"S3: fetched {len(audio_bytes)} bytes for '{s3_key}'")
        return {"success": True, "audio_bytes": audio_bytes}
    except Exception as e:
        logger.error(f"S3: error fetching audio '{s3_key}': {e}")
        return {"success": False, "error": str(e)}


def delete_s3_object(s3_key: str) -> bool:
    """Delete an object from S3. Returns True on success."""
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    try:
        s3_client = get_s3_client()
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        logger.info(f"S3: deleted object '{s3_key}'")
        return True
    except Exception as e:
        logger.warning(f"S3: failed to delete '{s3_key}': {e}")
        return False
