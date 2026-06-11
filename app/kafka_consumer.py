# ============================================================
# WHAT IS THIS FILE?
# This is the Kafka CONSUMER — it reads click events from Kafka
# and stores them in Redis for the analytics endpoint to read.
#
# This runs as a SEPARATE PROCESS from the main FastAPI server.
# In Docker, it's a separate container ("worker" service in docker-compose).
#
# HOW IT WORKS:
# 1. FastAPI server receives a click → sends event to Kafka (producer)
# 2. THIS consumer is always running in the background
# 3. It reads events from Kafka one by one
# 4. Stores them in Redis as a list (for "recent clicks" in analytics)
#
# This is the "event-driven architecture" pattern — very common at
# companies like Swiggy, Zomato, Flipkart, Amazon!
# ============================================================

import json
import os
import time
import logging
import signal
import sys

from app.database import get_db_connection

try:
    from kafka import KafkaConsumer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Set up logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",  # e.g. "2024-01-15 10:30:00 [INFO] message"
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "url-clicks")

# How many recent events to keep per URL in Redis
# Keeping only last 100 prevents Redis from running out of memory
MAX_EVENTS_PER_URL = 100


def process_click_event(redis, event: dict):
    """
    Processes a single click event:
    1. Stores it in a Redis List for the analytics endpoint
    2. Updates per-day click counters (for charts/graphs)
    
    Redis data structures used:
    - LPUSH: adds to LEFT of list (newest first)
    - LTRIM: keeps only first N elements (evicts old data)
    - INCR: increments a counter
    """
    short_code = event.get("short_code")
    if not short_code:
        return
    
    # Store the event in a Redis List
    # Key: "events:aB3xY"
    # Value: JSON string of the event
    event_key = f"events:{short_code}"
    redis.lpush(event_key, json.dumps(event))    # LPUSH = add to left (newest first)
    redis.ltrim(event_key, 0, MAX_EVENTS_PER_URL - 1)  # Keep only last 100
    
    # Set expiry on the events list (30 days, same as the URL)
    redis.expire(event_key, 30 * 24 * 60 * 60)
    
    # Track daily click counts (for trend charts)
    # Key format: "daily:aB3xY:2024-01-15"
    # This lets you show a graph of clicks per day!
    date_str = time.strftime("%Y-%m-%d", time.gmtime(event.get("timestamp", time.time())))
    daily_key = f"daily:{short_code}:{date_str}"
    redis.incr(daily_key)
    redis.expire(daily_key, 90 * 24 * 60 * 60)  # Keep daily stats for 90 days
    
    logger.info(f"📊 Processed click for /{short_code} from {event.get('ip_address', 'unknown')}")


def run_consumer():
    """
    Main consumer loop — runs forever, reading from Kafka.
    
    group_id = "analytics-group"
    WHY? Kafka uses "consumer groups" for scalability.
    If you run 3 instances of this consumer with the same group_id,
    Kafka automatically splits the work between them.
    This is horizontal scaling!
    """
    if not KAFKA_AVAILABLE:
        logger.error("kafka-python not installed. Install with: pip install kafka-python")
        sys.exit(1)
    
    redis = get_db_connection()
    
    logger.info(f"🚀 Starting Kafka consumer | broker={KAFKA_BOOTSTRAP_SERVERS} | topic={KAFKA_TOPIC}")
    
    # Handle Ctrl+C gracefully
    def shutdown(sig, frame):
        logger.info("👋 Shutting down consumer...")
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Retry loop — if Kafka is temporarily down, keep trying
    while True:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                group_id="analytics-group",       # Consumer group for load balancing
                auto_offset_reset="earliest",      # If new group: read from beginning of topic
                                                   # "latest" would skip old messages
                enable_auto_commit=True,           # Auto-commit offset after processing
                auto_commit_interval_ms=1000,      # Commit every 1 second
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),  # Bytes → dict
                session_timeout_ms=30000,          # Consider consumer dead after 30s silence
                heartbeat_interval_ms=10000        # Send heartbeat every 10s to stay in group
            )
            
            logger.info("✅ Connected to Kafka! Waiting for click events...")
            
            # Main loop: poll Kafka for new messages
            # This is a BLOCKING call — it waits for messages
            for message in consumer:
                # message.value = the dict we sent (already deserialized above)
                event = message.value
                
                # Process the event
                process_click_event(redis, event)
                
        except Exception as e:
            logger.error(f"❌ Consumer error: {e}")
            logger.info("🔄 Retrying in 5 seconds...")
            time.sleep(5)  # Wait before retrying


if __name__ == "__main__":
    run_consumer()
