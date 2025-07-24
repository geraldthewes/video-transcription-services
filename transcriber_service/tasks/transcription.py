import os
import json
import time # Keep time import for potential future use, though not directly used in this snippet
from datetime import datetime, timezone # Added timezone for UTC consistency
import redis
from celery import Celery
from celery.utils.log import get_task_logger

# Assuming multistep_transcriber is installed and importable
from mst import VideoTranscriber 
from treeseg import Embeddings, ollama_embeddings

# For S3
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from typing import Optional, Dict, Any # Added for type hinting

# --- Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
# Fallback to a default if CACHE_DIR is not in env, though it should be set by Docker.
CACHE_DIR = os.getenv("CACHE_DIR", "/app/cache") 

# S3 Config from environment (ensure these are available to the Celery worker)
S3_STORAGE_BUCKET = os.getenv("S3_STORAGE_BUCKET")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_ENDPOINT = os.getenv("AWS_ENDPOINT") # For MinIO/local S3

# --- Celery Application Setup ---
celery_app = Celery(
    "transcription_tasks",
    broker=f"redis://{REDIS_HOST}:{REDIS_PORT}/0",
    backend=f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC", # Using string "UTC"
    enable_utc=True,
    worker_prefetch_multiplier=1, # Process one task at a time per worker
    task_acks_late=True, # Acknowledge after task completion/failure
    task_reject_on_worker_lost=True # Requeue if worker is lost
)

logger = get_task_logger(__name__)

# --- Redis Client for Metadata ---
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
    redis_client.ping() # Verify connection at startup
    logger.info(f"Successfully connected to Redis for metadata at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis for metadata at {REDIS_HOST}:{REDIS_PORT}: {e}")
    redis_client = None # Set to None if connection fails

# --- Helper function to update task metadata in Redis ---
def update_redis_metadata(task_id: str, updates: Dict[str, Any]):
    if not redis_client:
        logger.error(f"Redis client not available. Cannot update metadata for task {task_id}.")
        return

    task_key = f"task:{task_id}"
    try:
        raw_metadata = redis_client.get(task_key)
        if raw_metadata:
            metadata = json.loads(raw_metadata)
        else:
            logger.warning(f"No existing metadata found for task {task_id} in Redis. Creating new entry for update.")
            metadata = {} 
        
        metadata.update(updates)
        metadata["last_updated_time"] = datetime.now(timezone.utc).isoformat()
        redis_client.set(task_key, json.dumps(metadata))
        logger.debug(f"Task {task_id}: Successfully updated Redis metadata with keys: {list(updates.keys())}")
    except redis.exceptions.RedisError as e:
        logger.error(f"Task {task_id}: RedisError updating metadata: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Task {task_id}: JSONDecodeError for raw metadata '{raw_metadata}': {e}")
    except Exception as e:
        logger.error(f"Task {task_id}: Generic error updating metadata: {e}", exc_info=True)


# --- S3 Upload Helper ---
def upload_to_s3(local_file_path: str, client_id: str, s3_object_path_suffix: str, content_type: str ='application/octet-stream') -> Optional[str]:
    if not (S3_STORAGE_BUCKET and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY):
        logger.error(f"S3 credentials/bucket not configured for client {client_id}. Cannot upload {local_file_path}.")
        return None

    # Sanitize client_id and s3_object_path_suffix before creating the key
    safe_client_id = "".join(c if c.isalnum() or c in ['_', '-'] else '_' for c in client_id)
    safe_s3_object_path_suffix = "".join(c if c.isalnum() or c in ['/', '.', '_', '-'] else '_' for c in s3_object_path_suffix)
    s3_key = f"transcriber/{safe_client_id}/{safe_s3_object_path_suffix}"
    
    s3_client_params = {
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
    }
    if AWS_REGION:
        s3_client_params["region_name"] = AWS_REGION
    if AWS_ENDPOINT: 
        s3_client_params["endpoint_url"] = AWS_ENDPOINT

    try:
        s3_client = boto3.client("s3", **s3_client_params)
        s3_client.upload_file(local_file_path, S3_STORAGE_BUCKET, s3_key, ExtraArgs={'ContentType': content_type})
        s3_url = f"s3://{S3_STORAGE_BUCKET}/{s3_key}"
        logger.info(f"Successfully uploaded {local_file_path} to {s3_url} for client {client_id}")
        return s3_url
    except FileNotFoundError:
        logger.error(f"S3 Upload: Local file {local_file_path} not found for client {client_id}.")
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error(f"S3 Upload: Credentials error for client {client_id}: {e}")
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', 'No message')
        logger.error(f"S3 Upload: ClientError for client {client_id} (Code: {error_code}): {error_message} while uploading {local_file_path} to {s3_key}")
    except Exception as e:
        logger.error(f"S3 Upload: An unexpected error occurred for client {client_id} uploading {local_file_path}: {e}", exc_info=True)
    return None


# --- Transcription Celery Task ---
@celery_app.task(bind=True, name="transcribe_audio_task")
def transcribe_audio_task(self, task_id: str, audio_path_in_cache: str, client_id: str, s3_path_suffix: Optional[str] = None, original_filename: Optional[str] = None):
    logger.info(f"Task {self.request.id} (App Task ID: {task_id}) received by worker {self.request.hostname} for audio: {audio_path_in_cache}, original: {original_filename}, client: {client_id}")
    update_redis_metadata(task_id, {
        "status": "PROCESSING", 
        "celery_task_id": self.request.id, 
        "processing_start_time": datetime.now(timezone.utc).isoformat(),
        "worker_node": self.request.hostname
    })

    # Ensure cache directory for outputs exists
    task_output_cache_dir = os.path.join(CACHE_DIR, task_id) # Store task-specific files in a subfolder
    os.makedirs(task_output_cache_dir, exist_ok=True)
    
    safe_original_filename_part = "".join(c if c.isalnum() or c in ['.', '_', '-'] else '_' for c in (original_filename or "transcription"))[:100]
    base_output_filename = f"{task_id}_{safe_original_filename_part}" # This is okay, but files will go into task_output_cache_dir
    
    # Paths for generated files within the task's specific cache folder
    output_json_filename_relative = os.path.join(task_id, f"{base_output_filename}.json")
    output_md_filename_relative = os.path.join(task_id, f"{base_output_filename}.md")
    
    local_json_path = os.path.join(CACHE_DIR, output_json_filename_relative)
    local_md_path = os.path.join(CACHE_DIR, output_md_filename_relative)

    embeddings_config = Embeddings(
        embeddings_func=ollama_embeddings, # openai_embeddings
        headers={}, # forOpenAI
        model="nomic-embed-text",  # or "text-embedding-ada-002" for openai         
        endpoint=os.getenv("OLLAMA_HOST", "")   # "https://api.openai.com/v1/embeddings"
    )
    config = {
        "MIN_SEGMENT_SIZE": 10,
        "LAMBDA_BALANCE": 0,
        "UTTERANCE_EXPANSION_WIDTH": 3,
        "EMBEDDINGS": embeddings_config,
        "TEXT_KEY": "transcript"
    }

    
    try:
        models_cache = os.path.join(CACHE_DIR, "multistep_transcriber_models")
        os.makedirs(models_cache, exist_ok=True)
        
        transcriber = VideoTranscriber(config)

        # Ensure the input audio file actually exists before calling transcribe
        if not os.path.exists(audio_path_in_cache):
            logger.error(f"Task {task_id}: Input audio file {audio_path_in_cache} does not exist.")
            raise FileNotFoundError(f"Input audio file {audio_path_in_cache} not found for task {task_id}")

        logger.info(f"Task {task_id}: Starting transcription for {audio_path_in_cache}")
        
        result, nouns_list = transcriber.transcribe_video(audio_path_in_cache)
        print(f'Break into topics {audio_path_in_cache}')
        # Fix max topics
        result, headlines, summary = transcriber.topics(audio_path_in_cache, result, 25)    
        transcriber.format_transcript(audio_path_in_cache, result, nouns_list, headlines, summary)

        # Should add some error check
        json_content = transcriber.retrieve_json(audio_path_in_cache)
        md_content = transcriber.retrieve_markdown(audio_path_in_cache)

        with open(local_json_path, "w", encoding='utf-8') as f_json:
            json.dump(json_content, f_json, indent=2, ensure_ascii=False)
        logger.info(f"Task {task_id}: Saved JSON transcript to {local_json_path}")

        with open(local_md_path, "w", encoding='utf-8') as f_md:
            f_md.write(md_content)
        logger.info(f"Task {task_id}: Saved Markdown transcript to {local_md_path}")

        update_redis_metadata(task_id, {
            "transcribed_json_file": output_json_filename_relative, # Relative to CACHE_DIR
            "transcribed_md_file": output_md_filename_relative,   # Relative to CACHE_DIR
        })

        s3_json_url, s3_md_url = None, None
        if s3_path_suffix:
            logger.info(f"Task {task_id}: s3_path_suffix '{s3_path_suffix}' provided. Uploading results to S3.")
            s3_json_url = upload_to_s3(local_json_path, client_id, f"{s3_path_suffix}.json", 'application/json; charset=utf-8')
            s3_md_url = upload_to_s3(local_md_path, client_id, f"{s3_path_suffix}.md", 'text/markdown; charset=utf-8')
            update_redis_metadata(task_id, {"s3_json_url": s3_json_url, "s3_md_url": s3_md_url})
        
        final_status = "COMPLETED"
        if s3_path_suffix and not (s3_json_url and s3_md_url):
            final_status = "COMPLETED_WITH_S3_UPLOAD_FAILURES"
            logger.warning(f"Task {task_id}: Completed transcription but one or both S3 uploads failed (JSON: {s3_json_url}, MD: {s3_md_url}).")

        update_redis_metadata(task_id, {"status": final_status, "processing_end_time": datetime.now(timezone.utc).isoformat()})
        logger.info(f"Task {task_id} ({self.request.id}) finished with status: {final_status}.")
        return {"status": final_status, "json_file": output_json_filename_relative, "md_file": output_md_filename_relative, "s3_json_url": s3_json_url, "s3_md_url": s3_md_url}

    except FileNotFoundError as fnf_error: # Specific handling for file not found before transcription
        logger.error(f"Task {task_id} ({self.request.id}) failed: {fnf_error}", exc_info=True)
        update_redis_metadata(task_id, {"status": "FAILED", "error_message": str(fnf_error), "processing_end_time": datetime.now(timezone.utc).isoformat()})
        raise
    except Exception as e:
        logger.error(f"Task {task_id} ({self.request.id}) failed during transcription for audio {audio_path_in_cache}: {e}", exc_info=True)
        try:
            update_redis_metadata(task_id, {
                "status": "FAILED", 
                "error_message": str(e), 
                "processing_end_time": datetime.now(timezone.utc).isoformat()
            })
        except Exception as meta_e: 
            logger.critical(f"Task {task_id}: CRITICAL - Failed to update Redis with FAILED status after primary error: {meta_e}", exc_info=True)
        raise # Re-raise the exception to mark the task as FAILED in Celery backend


# --- Cache Cleanup Celery Beat Task ---
# Ensure CACHE_EXPIRY is defined (it should be from the top of the file, but double-check)
CACHE_EXPIRY_SECONDS = int(os.getenv("CACHE_EXPIRY", "604800")) # 7 days default
# Import timedelta if not already at the top (it should be with datetime)
from datetime import timedelta 

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Add the cleanup task to the Celery beat schedule
    # Defaulting to daily at 3 AM UTC.
    # For testing, a shorter interval like CACHE_EXPIRY_SECONDS / 2 might be used.
    sender.add_periodic_task(
        # timedelta(seconds=CACHE_EXPIRY_SECONDS / 2), # Example: Run more frequently than expiry
        # celery.schedules.crontab(hour=3, minute=0), # Run daily at 3 AM UTC
        timedelta(days=1), # Run daily
        cleanup_expired_tasks.s(),
        name="cleanup_expired_transcription_cache",
    )

@celery_app.task(name="cleanup_expired_tasks")
def cleanup_expired_tasks():
    logger.info("Running daily cache cleanup task...")
    if not redis_client:
        logger.error("Cache Cleanup: Redis client not available. Aborting cleanup.")
        return

    cleaned_tasks_count = 0
    
    task_keys_bytes = []
    try:
        task_keys_bytes = redis_client.keys("task:*")
    except redis.exceptions.RedisError as e:
        logger.error(f"Cache Cleanup: Could not fetch task keys from Redis: {e}")
        return

    if not task_keys_bytes:
        logger.info("Cache Cleanup: No task keys found in Redis. Nothing to clean up.")
        return

    logger.info(f"Cache Cleanup: Found {len(task_keys_bytes)} task keys to check.")

    for task_key_byte in task_keys_bytes:
        task_key = task_key_byte.decode('utf-8')
        current_task_failed_deletions = 0 # Reset for each task
        try:
            raw_metadata = redis_client.get(task_key)
            if not raw_metadata:
                logger.warning(f"Cache Cleanup: Task key {task_key} disappeared before processing.")
                continue
            
            metadata = json.loads(raw_metadata)
            # Ensure task_id is derived correctly from the key string
            task_id_from_key = task_key.split(":", 1)[1] 

            # Determine the relevant timestamp for expiry check
            timestamp_str = None
            status = metadata.get("status")

            if status == "FAILED":
                timestamp_str = metadata.get("processing_end_time") or metadata.get("last_updated_time")
            elif status in ["COMPLETED", "COMPLETED_WITH_S3_UPLOAD_FAILURES"]:
                timestamp_str = metadata.get("last_download_time") or metadata.get("processing_end_time") or metadata.get("last_updated_time")
            else: # PENDING states or stuck in PROCESSING
                timestamp_str = metadata.get("upload_time") or metadata.get("download_time") or metadata.get("celery_dispatch_time") or metadata.get("last_updated_time")


            if not timestamp_str:
                logger.warning(f"Cache Cleanup: Task {task_id_from_key} (key: {task_key}) has no suitable timestamp for expiry check. Metadata: {metadata}. Skipping.")
                continue

            try:
                task_timestamp = datetime.fromisoformat(timestamp_str)
                if task_timestamp.tzinfo is None: # Ensure offset-aware
                    task_timestamp = task_timestamp.replace(tzinfo=timezone.utc) 
            except ValueError:
                logger.error(f"Cache Cleanup: Task {task_id_from_key} has invalid timestamp format '{timestamp_str}'. Skipping.")
                continue
            
            if datetime.now(timezone.utc) - task_timestamp > timedelta(seconds=CACHE_EXPIRY_SECONDS):
                logger.info(f"Cache Cleanup: Task {task_id_from_key} expired (timestamp: {timestamp_str}). Proceeding with cleanup.")
                
                files_to_attempt_delete = []
                
                # Original audio file (metadata["saved_filename"] is like "taskid_safefilename.wav")
                # It's stored directly in CACHE_DIR as per FastAPI logic.
                if not metadata.get("s3_path") and metadata.get("saved_filename"):
                    original_audio_path = os.path.join(CACHE_DIR, metadata["saved_filename"])
                    files_to_attempt_delete.append(original_audio_path)

                # Transcribed files (paths are relative to CACHE_DIR, e.g., "taskid/taskid_safefilename.json")
                if metadata.get("transcribed_json_file"):
                    files_to_attempt_delete.append(os.path.join(CACHE_DIR, metadata["transcribed_json_file"]))
                if metadata.get("transcribed_md_file"):
                    files_to_attempt_delete.append(os.path.join(CACHE_DIR, metadata["transcribed_md_file"]))

                for file_path in files_to_attempt_delete:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Cache Cleanup: Deleted expired file {file_path} for task {task_id_from_key}.")
                        else:
                            logger.warning(f"Cache Cleanup: Expired file {file_path} for task {task_id_from_key} not found.")
                    except OSError as e:
                        logger.error(f"Cache Cleanup: Error deleting file {file_path} for task {task_id_from_key}: {e}")
                        current_task_failed_deletions += 1
                
                # Try to remove the task-specific directory if it exists (e.g., CACHE_DIR/task_id/)
                task_specific_dir = os.path.join(CACHE_DIR, task_id_from_key)
                if os.path.exists(task_specific_dir):
                    try:
                        # Only remove if all known files within it were targeted and successfully deleted or not found
                        # This is a basic check; if other unexpected files are in task_specific_dir, it won't be empty.
                        if not os.listdir(task_specific_dir): 
                            os.rmdir(task_specific_dir)
                            logger.info(f"Cache Cleanup: Removed empty task directory {task_specific_dir} for task {task_id_from_key}.")
                        else:
                            # Check if remaining files are only those that failed deletion
                            remaining_files_after_attempt = [f for f in os.listdir(task_specific_dir) if os.path.join(task_specific_dir, f) in files_to_attempt_delete]
                            if not remaining_files_after_attempt: # All targeted files are gone (or were never there)
                                 logger.info(f"Cache Cleanup: Task directory {task_specific_dir} for task {task_id_from_key} is empty or only contains files that were already handled/missing. Removing.")
                                 os.rmdir(task_specific_dir) # Try removing again if logic allows
                            else:
                                logger.warning(f"Cache Cleanup: Task directory {task_specific_dir} for task {task_id_from_key} is not empty after deleting known files. Contains: {os.listdir(task_specific_dir)}. Manual check may be needed.")
                    except OSError as e:
                        logger.error(f"Cache Cleanup: Error removing task directory {task_specific_dir} for task {task_id_from_key}: {e}")
                        current_task_failed_deletions +=1 # Count this as a deletion failure for the task

                if current_task_failed_deletions == 0:
                    redis_client.delete(task_key)
                    logger.info(f"Cache Cleanup: Deleted Redis key {task_key} for expired task {task_id_from_key}.")
                    cleaned_tasks_count += 1
                else:
                    logger.warning(f"Cache Cleanup: Did not delete Redis key {task_key} for task {task_id_from_key} due to {current_task_failed_deletions} file/directory deletion issues.")

        except json.JSONDecodeError as e:
            logger.error(f"Cache Cleanup: Could not decode JSON metadata for key {task_key}: {e}. Skipping.")
        except redis.exceptions.RedisError as e: # Catch Redis errors during GET for a specific key
            logger.error(f"Cache Cleanup: Redis error processing key {task_key}: {e}. Skipping.")
        except Exception as e: 
            logger.error(f"Cache Cleanup: Unexpected error processing key {task_key}: {e}", exc_info=True)
            
    total_failed_deletions = sum(1 for task_key_byte in task_keys_bytes if redis_client.exists(task_key_byte.decode('utf-8')))
    logger.info(f"Cache Cleanup: Finished. Cleaned {cleaned_tasks_count} tasks. Tasks remaining due to deletion issues (approx): {total_failed_deletions - (len(task_keys_bytes) - cleaned_tasks_count) }.") # This logic needs refinement
    # A simpler summary:
    logger.info(f"Cache Cleanup: Finished. Successfully cleaned and removed Redis keys for {cleaned_tasks_count} tasks.")
    # To get a count of tasks that had issues and whose Redis keys were NOT deleted:
    # This would require iterating again or tracking keys that had current_task_failed_deletions > 0.
    # For now, the log messages per task are the primary indicators of issues.
    return {"cleaned_tasks_redis_keys_removed": cleaned_tasks_count}
