import logging
import base64
from io import BytesIO
from minio import Minio
import app.core.config as consts

logger = logging.getLogger(__name__)

# Minio Configuration
_minio_client = None


def get_minio_client():
    global _minio_client
    if _minio_client is not None:
        return _minio_client

    if consts.MINIO_HOST:
        try:
            _minio_client = Minio(
                endpoint=consts.MINIO_HOST,
                access_key=consts.MINIO_ACCESS_KEY,
                secret_key=consts.MINIO_SECRET_KEY,
                secure=consts.MINIO_SECURE,
            )
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
    return _minio_client


def ensure_bucket_exists(bucket_name):
    try:
        minio_client = get_minio_client()
        if not minio_client:
            return

        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"MinIO: bucket '{bucket_name}' created.")
        else:
            logger.debug(f"MinIO: bucket '{bucket_name}' already exists.")
    except Exception as e:
        logger.error(f"MinIO: error checking/creating bucket '{bucket_name}': {e}")


def fetch_resume(resume_name):
    logger.info(f"MinIO: fetching resume '{resume_name}'")
    try:
        minio_client = get_minio_client()
        bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
        response = minio_client.get_object(bucket_name, resume_name)
        file_content = response.read()
        file_stream = BytesIO(file_content)
        file_size_mb = len(file_content) / (1024 * 1024)
        file_extension = "." + resume_name.split(".")[-1] if "." in resume_name else ""
        file_name = str(resume_name.split("/")[-1])
        logger.info(
            f"MinIO: successfully fetched '{resume_name}' ({file_size_mb:.2f} MB)"
        )
        return {
            "success": True,
            "file_stream": file_stream,
            "file_size_mb": file_size_mb,
            "resume_name": resume_name,
            "file_name": file_name,
            "file_extension": file_extension,
        }
    except Exception as e:
        logger.error(f"MinIO: fetch error for '{resume_name}': {e}")
        return {"success": False, "error": f"Failed to fetch resume from MinIO: {e}"}


def upload_file(file_path, object_name=None):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    if object_name is None:
        object_name = file_path.split("/")[-1]

    ensure_bucket_exists(bucket_name)
    logger.info(f"MinIO: uploading file '{file_path}' as '{object_name}'")
    try:
        minio_client = get_minio_client()
        minio_client.fput_object(bucket_name, object_name, file_path)
        minio_url = f"http://{consts.MINIO_HOST}/{bucket_name}/{object_name}"
        logger.info(f"MinIO: successfully uploaded file to {minio_url}")
        return {
            "success": True,
            "s3_url": minio_url,
        }
    except Exception as e:
        logger.error(f"MinIO: error uploading file '{file_path}': {e}")
        return {"success": False, "error": f"Failed to upload file to MinIO: {e}"}


def upload_image(image_content, object_name):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    ensure_bucket_exists(bucket_name)
    logger.info(f"MinIO: uploading image content as '{object_name}'")
    try:
        minio_client = get_minio_client()
        minio_client.put_object(
            bucket_name,
            object_name,
            data=BytesIO(image_content),
            length=len(image_content),
            content_type="image/jpeg",
        )
        minio_url = f"http://{consts.MINIO_HOST}/{bucket_name}/{object_name}"
        logger.info(f"MinIO: successfully uploaded image to {minio_url}")
        return {
            "success": True,
            "s3_url": minio_url,
        }
    except Exception as e:
        logger.error(f"MinIO: error uploading image '{object_name}': {e}")
        return {"success": False, "error": f"Failed to upload image to MinIO: {e}"}

def upload_pdf(pdf_content, object_name):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    ensure_bucket_exists(bucket_name)
    logger.info(f"MinIO: uploading PDF content as '{object_name}'")
    try:
        minio_client = get_minio_client()
        minio_client.put_object(
            bucket_name,
            object_name,
            data=BytesIO(pdf_content),
            length=len(pdf_content),
            content_type="application/pdf",
        )
        minio_url = f"http://{consts.MINIO_HOST}/{bucket_name}/{object_name}"
        logger.info(f"MinIO: successfully uploaded PDF to {minio_url}")
        return {
            "success": True,
            "s3_url": minio_url,
        }
    except Exception as e:
        logger.error(f"MinIO: error uploading PDF '{object_name}': {e}")
        return {"success": False, "error": f"Failed to upload PDF to MinIO: {e}"}



def list_proctoring_images(interview_session_id=None):
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    prefix = "ai-interviews/proctoring/"
    if interview_session_id:
        prefix += f"{interview_session_id}/"

    logger.info(f"MinIO: listing objects with prefix '{prefix}'")
    try:
        minio_client = get_minio_client()
        objects = minio_client.list_objects(bucket_name, prefix=prefix, recursive=True)
        images = []
        for obj in objects:
            key = obj.object_name
            image_name = key.split("/")[-1]
            minio_url = f"http://{consts.MINIO_HOST}/{bucket_name}/{key}"
            images.append(
                {
                    "image_name": image_name,
                    "s3_key": key,
                    "s3_url": minio_url,
                    "last_modified": obj.last_modified.isoformat(),
                    "size": obj.size,
                }
            )
        logger.info(f"MinIO: found {len(images)} images")
        return {"success": True, "images": images}
    except Exception as e:
        logger.error(f"MinIO: error listing objects: {e}")
        return {"success": False, "error": f"Failed to list MinIO objects: {e}"}


def get_image_base64(image_key):
    logger.info(f"MinIO: retrieving base64 for key '{image_key}'")
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    try:
        image_key = (
            image_key.split(f"/{bucket_name}/")[-1]
            if f"/{bucket_name}/" in image_key
            else image_key
        )
        image_key = image_key.lstrip("/")

        minio_client = get_minio_client()
        response = minio_client.get_object(bucket_name, image_key)
        image_bytes = response.read()
        content_type = response.headers.get("content-type", "image/jpeg")
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        logger.info(f"MinIO: successfully retrieved and encoded image '{image_key}'")
        return f"data:{content_type};base64,{base64_image}"
    except Exception as e:
        logger.error(
            f"MinIO: unexpected error in get_image_base64 for '{image_key}': {e}"
        )
        return None


def upload_audio(audio_bytes, object_name):
    """Upload raw audio bytes to MinIO."""
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    ensure_bucket_exists(bucket_name)
    logger.info(f"MinIO: uploading audio as '{object_name}'")
    try:
        minio_client = get_minio_client()
        minio_client.put_object(
            bucket_name,
            object_name,
            data=BytesIO(audio_bytes),
            length=len(audio_bytes),
            content_type="audio/wav",
        )
        minio_url = f"http://{consts.MINIO_HOST}/{bucket_name}/{object_name}"
        logger.info(f"MinIO: successfully uploaded audio to {minio_url}")
        return {"success": True, "s3_url": minio_url}
    except Exception as e:
        logger.error(f"MinIO: error uploading audio '{object_name}': {e}")
        return {"success": False, "error": f"Failed to upload audio to MinIO: {e}"}


def get_audio_bytes(object_name):
    """Retrieve audio bytes from MinIO."""
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    logger.info(f"MinIO: fetching audio '{object_name}'")
    try:
        minio_client = get_minio_client()
        response = minio_client.get_object(bucket_name, object_name)
        audio_bytes = response.read()
        logger.info(f"MinIO: successfully fetched audio '{object_name}'")
        return {"success": True, "audio_bytes": audio_bytes}
    except Exception as e:
        logger.error(f"MinIO: error fetching audio '{object_name}': {e}")
        return {"success": False, "error": f"Failed to fetch audio from MinIO: {e}"}


def delete_object(object_name):
    """Delete an object from MinIO."""
    bucket_name = consts.INFOSPOKE_S3_BUCKET_NAME
    logger.info(f"MinIO: deleting object '{object_name}'")
    try:
        minio_client = get_minio_client()
        minio_client.remove_object(bucket_name, object_name)
        logger.info(f"MinIO: successfully deleted '{object_name}'")
        return {"success": True}
    except Exception as e:
        logger.error(f"MinIO: error deleting '{object_name}': {e}")
        return {"success": False, "error": f"Failed to delete object from MinIO: {e}"}


def upload_image_to_s3(image_bytes, object_name):
    return upload_image(image_bytes, object_name)


def upload_audio_to_s3(audio_bytes, object_name):
    return upload_audio(audio_bytes, object_name)


def get_audio_bytes_from_s3(object_name):
    return get_audio_bytes(object_name)


def delete_s3_object(object_name):
    return delete_object(object_name)


def get_s3_image_base64(image_key):
    return get_image_base64(image_key)
