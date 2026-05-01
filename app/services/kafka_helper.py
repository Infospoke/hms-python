import json
import logging
from uuid import uuid4
from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient, NewTopic
import app.core.config as consts

logger = logging.getLogger(__name__)

KAFKA_TOPIC = None

_producer = None
_topic_created = False


def ensure_topic_exists():
    global _topic_created
    if _topic_created:
        return
    try:
        global KAFKA_TOPIC
        if not KAFKA_TOPIC:
            KAFKA_TOPIC = consts.KAFKA_TOPIC

        admin_client = AdminClient({"bootstrap.servers": consts.KAFKA_HOST})
        topic_metadata = admin_client.list_topics(timeout=5)
        if KAFKA_TOPIC not in topic_metadata.topics:
            new_topic = NewTopic(KAFKA_TOPIC, num_partitions=1, replication_factor=1)
            admin_client.create_topics([new_topic])
            logger.info(f"Kafka topic '{KAFKA_TOPIC}' creation requested.")
        _topic_created = True
    except Exception as e:
        logger.warning(
            f"Error ensuring Kafka topic exists (you may need to create it manually): {e}"
        )


def get_kafka_producer() -> Producer:
    global _producer
    ensure_topic_exists()
    if _producer is None:
        producer_conf = {
            "bootstrap.servers": consts.KAFKA_HOST,
            "message.max.bytes": 10485760,
        }
        _producer = Producer(producer_conf)
    return _producer


def get_kafka_consumer() -> Consumer:
    ensure_topic_exists()
    consumer_conf = {
        "bootstrap.servers": consts.KAFKA_HOST,
        "group.id": consts.KAFKA_GROUP_ID,
        "auto.offset.reset": "earliest",
        "fetch.message.max.bytes": 10485760,
        "allow.auto.create.topics": True,
    }
    return Consumer(consumer_conf)


def send_analyze_image_task(
    payload: dict, message_group_id: str = "analyze-image"
) -> dict:
    try:
        producer = get_kafka_producer()
        message_bytes = json.dumps(payload).encode("utf-8")
        producer.produce(
            topic=KAFKA_TOPIC, value=message_bytes, key=message_group_id.encode("utf-8")
        )
        producer.poll(0)
        logger.info("Kafka: enqueued analyze-image task")
        return {"success": True, "message_id": str(uuid4())}
    except Exception as e:
        logger.error(f"Kafka send failed: {e}")
        return {"success": False, "error": str(e)}


def close_kafka_producer():
    global _producer
    if _producer is not None:
        logger.info("Flushing and closing Kafka producer...")
        _producer.flush(timeout=5)
        _producer = None
