import json
import logging
from uuid import uuid4
from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient, NewTopic
import app.core.config as consts

logger = logging.getLogger(__name__)

KAFKA_TOPIC = None

_producer = None
_created_topics = set()


def get_av_topic() -> str:
    """Topic for per-answer audio/visual clip analysis."""
    return consts.KAFKA_AV_TOPIC


def ensure_topic_exists(topic: str = None):
    global KAFKA_TOPIC
    if not KAFKA_TOPIC:
        KAFKA_TOPIC = consts.KAFKA_TOPIC

    topic = topic or KAFKA_TOPIC
    if not topic or topic in _created_topics:
        return
    try:
        admin_client = AdminClient({"bootstrap.servers": consts.KAFKA_HOST})
        topic_metadata = admin_client.list_topics(timeout=5)
        if topic not in topic_metadata.topics:
            new_topic = NewTopic(topic, num_partitions=1, replication_factor=1)
            admin_client.create_topics([new_topic])
            logger.info(f"Kafka topic '{topic}' creation requested.")
        _created_topics.add(topic)
    except Exception as e:
        logger.warning(
            f"Error ensuring Kafka topic '{topic}' exists (you may need to create it manually): {e}"
        )


def get_kafka_producer(topic: str = None) -> Producer:
    global _producer
    ensure_topic_exists(topic)
    if _producer is None:
        producer_conf = {
            "bootstrap.servers": consts.KAFKA_HOST,
            "message.max.bytes": 10485760,
        }
        _producer = Producer(producer_conf)
    return _producer


def get_kafka_consumer(topic: str = None, group_id: str = None) -> Consumer:
    """Build a consumer. `group_id` must differ per worker type, otherwise two
    workers subscribed to different topics would share offsets in one group."""
    ensure_topic_exists(topic)
    consumer_conf = {
        "bootstrap.servers": consts.KAFKA_HOST,
        "group.id": group_id or consts.KAFKA_GROUP_ID,
        "auto.offset.reset": "earliest",
        "fetch.message.max.bytes": 10485760,
        "allow.auto.create.topics": True,
    }
    return Consumer(consumer_conf)


def _send(topic: str, payload: dict, key: str, label: str) -> dict:
    try:
        producer = get_kafka_producer(topic)
        message_bytes = json.dumps(payload).encode("utf-8")
        producer.produce(topic=topic, value=message_bytes, key=key.encode("utf-8"))
        producer.poll(0)
        logger.info(f"Kafka: enqueued {label} task on '{topic}'")
        return {"success": True, "message_id": str(uuid4())}
    except Exception as e:
        logger.error(f"Kafka send failed: {e}")
        return {"success": False, "error": str(e)}


def send_analyze_image_task(
    payload: dict, message_group_id: str = "analyze-image"
) -> dict:
    ensure_topic_exists()
    return _send(KAFKA_TOPIC, payload, message_group_id, "analyze-image")


def send_av_analysis_task(
    payload: dict, message_group_id: str = "av-analysis"
) -> dict:
    """Enqueue one answer clip for audio/visual proctoring analysis.

    Only the MinIO object key travels through Kafka, never the media itself -
    a clip is orders of magnitude larger than the 10MB message ceiling.
    """
    return _send(get_av_topic(), payload, message_group_id, "av-analysis")


def close_kafka_producer():
    global _producer
    if _producer is not None:
        logger.info("Flushing and closing Kafka producer...")
        _producer.flush(timeout=5)
        _producer = None
