import json
import logging
from uuid import uuid4
import boto3
from app.core import config as consts

logger = logging.getLogger(__name__)


def get_sqs_client():
    return boto3.client(
        "sqs",
        region_name=consts.AWS_REGION,
        aws_access_key_id=consts.AWS_ACCESS_KEY,
        aws_secret_access_key=consts.AWS_SECRET_KEY,
    )


def send_analyze_image_task(
    payload: dict, message_group_id: str = "analyze-image"
) -> dict:
    try:
        client = get_sqs_client()
        dedup_id = str(uuid4())

        response = client.send_message(
            QueueUrl=consts.SQS_ANALYZE_IMAGE_QUEUE_URL,
            MessageBody=json.dumps(payload),
            MessageGroupId=message_group_id,
            MessageDeduplicationId=dedup_id,
        )
        logger.info(
            f"SQS: enqueued analyze-image task, MessageId={response['MessageId']}"
        )
        return {"success": True, "message_id": response["MessageId"]}
    except Exception as e:
        logger.error(f"SQS send failed: {e}")
        return {"success": False, "error": str(e)}


def receive_messages(max_messages: int = 10, wait_seconds: int = 20) -> list[dict]:
    try:
        client = get_sqs_client()
        response = client.receive_message(
            QueueUrl=consts.SQS_ANALYZE_IMAGE_QUEUE_URL,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
            AttributeNames=["All"],
            MessageAttributeNames=["All"],
        )
        messages = []
        for msg in response.get("Messages", []):
            try:
                body = json.loads(msg["Body"])
            except json.JSONDecodeError:
                logger.warning(
                    f"SQS: could not parse message body: {msg['Body'][:200]}"
                )
                body = {}
            messages.append(
                {
                    "body": body,
                    "receipt_handle": msg["ReceiptHandle"],
                    "message_id": msg["MessageId"],
                }
            )
        return messages
    except Exception as e:
        logger.error(f"SQS receive failed: {e}")
        return []


def delete_message(receipt_handle: str) -> None:
    try:
        client = get_sqs_client()
        client.delete_message(
            QueueUrl=consts.SQS_ANALYZE_IMAGE_QUEUE_URL,
            ReceiptHandle=receipt_handle,
        )
    except Exception as e:
        logger.error(f"SQS delete failed: {e}")
