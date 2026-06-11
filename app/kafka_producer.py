# ============================================================
# WHAT IS THIS FILE?
# This file sends events to Apache Kafka.
#
# WHAT IS KAFKA?
# Kafka is a "message broker" — a system that lets different services
# communicate by passing messages through a central hub.
#
# Think of Kafka like a POST OFFICE:
#   - PRODUCER: drops a letter (message) into a mailbox (topic)
#   - KAFKA:    stores all the letters reliably
#   - CONSUMER: picks up letters and processes them
#
# WHY USE KAFKA instead of just writing to Redis directly?
# 1. DECOUPLING: The API doesn't need to know about analytics logic
# 2. RELIABILITY: If analytics service crashes, messages queue up
#    and get processed when it restarts. No data loss!
# 3. SCALABILITY: Multiple consumers can read the same topic
#    (e.g., one for analytics, one for fraud detection, one for billing)
# 4. This is how Netflix, Uber, LinkedIn all handle events!
# ============================================================

import json
import os
import logging
from typing import Optional

# kafka-python is the Python library for Kafka
# We use try/except because Kafka might not be running in dev/testing
try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Set up logging — always log in production code!
# This lets you see what's happening without print() statements
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION FROM ENVIRONMENT VARIABLES
# Again, no hardcoded values! The same code runs everywhere.
# ============================================================
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "url-clicks")   # Topic = like a category/channel

# Global producer instance — we create it ONCE and reuse it
# Creating a new connection on every request would be very slow
_producer: Optional[object] = None


def get_kafka_producer():
    """
    Returns a singleton Kafka producer.
    'Singleton' means only ONE instance exists for the whole application.
    
    We use a global variable to store it.
    Thread-safety note: In a real app, you'd want proper locking here.
    For this project, it's fine!
    """
    global _producer
    
    if not KAFKA_AVAILABLE:
        return None
    
    if _producer is None:
        try:
            _producer = KafkaProducer(
                # bootstrap_servers = the Kafka broker address(es)
                # In production, you'd list multiple brokers for redundancy:
                # "kafka1:9092,kafka2:9092,kafka3:9092"
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                
                # value_serializer = how to convert Python objects to bytes
                # Kafka only stores bytes, so we JSON-encode everything
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                
                # acks="all" = wait for ALL Kafka replicas to confirm receipt
                # Slower but guarantees NO data loss. "1" is faster but risky.
                acks="all",
                
                # retries = if sending fails, try again up to 3 times
                retries=3,
                
                # request_timeout_ms = give up if Kafka doesn't respond in 5 seconds
                request_timeout_ms=5000
            )
            logger.info(f"✅ Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.warning(f"⚠️  Could not connect to Kafka: {e}. Click events will be skipped.")
            _producer = None
    
    return _producer


def send_click_event(event_data: dict) -> bool:
    """
    Sends a click event to the Kafka topic.
    
    Returns True if sent successfully, False if Kafka is unavailable.
    
    IMPORTANT: This function is "fault-tolerant" — if Kafka is down,
    the URL redirect still works! We just lose the analytics for that click.
    In a real system, you'd buffer these in Redis as a fallback.
    """
    producer = get_kafka_producer()
    
    if producer is None:
        # Kafka not available — log a warning and continue
        # The URL redirect should NOT fail just because analytics is down!
        logger.warning(f"Kafka unavailable, skipping click event for {event_data.get('short_code')}")
        return False
    
    try:
        # producer.send(topic, value)
        # This is ASYNC by default — it returns a "future" immediately
        # The actual sending happens in a background thread
        future = producer.send(KAFKA_TOPIC, value=event_data)
        
        # .get(timeout=2) waits up to 2 seconds for confirmation
        # In very high-traffic systems, you'd skip this for speed
        record_metadata = future.get(timeout=2)
        
        logger.info(
            f"✅ Click event sent to Kafka | "
            f"topic={record_metadata.topic} | "
            f"partition={record_metadata.partition} | "   # Kafka splits data into partitions for scalability
            f"offset={record_metadata.offset}"            # Position in the partition log
        )
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send click event to Kafka: {e}")
        return False
