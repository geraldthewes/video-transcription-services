import os
import httpx
import redis
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi import status as http_status # Renamed for clarity
from http import HTTPStatus # Keep for direct status code usage if needed
from starlette.responses import FileResponse
import shutil
import uuid
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Multi-Step Transcriber Service", version="0.1.0")

# Configuration from environment variables
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
OLLAMA_HOST = os.getenv("OLLAMA_HOST") # e.g., http://localhost:11434
CACHE_DIR = "/app/cache" # Align with docker-compose volume
S3_STORAGE_BUCKET = os.getenv("S3_STORAGE_BUCKET")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_ENDPOINT = os.getenv("AWS_ENDPOINT")

# Ensure cache directory exists at startup
os.makedirs(CACHE_DIR, exist_ok=True)

# Attempt to connect to Redis at startup
# This is a global variable that will store the Redis client or None
redis_client = None
initial_redis_status = "uninitialized"

logger.info(f"Attempting to connect to Redis at {REDIS_HOST}:{REDIS_PORT}")
try:
    # Explicitly connect and decode responses
    redis_client_instance = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=1, decode_responses=True)
    redis_client_instance.ping()
    redis_client = redis_client_instance # Assign to global if successful
    initial_redis_status = "ok"
    logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    initial_redis_status = f"error: {str(e)}"
    logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT}: {e}")
    # redis_client remains None


@app.get("/health")
async def health_check():
    global redis_client # Reference the global redis_client
    global initial_redis_status # Reference the global initial_redis_status

    ollama_current_status = "unavailable" # Default to unavailable
    if OLLAMA_HOST:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client: # Added timeout
                response = await client.get(f"{OLLAMA_HOST}/api/tags")
                # Ollama typically returns 200 for /api/tags if running, even if no models are pulled.
                # We consider any 2xx/3xx as "ok" for reachability.
                if 200 <= response.status_code < 400:
                    ollama_current_status = "ok"
                else:
                    ollama_current_status = f"error_code_{response.status_code}"
        except httpx.RequestError as e:
            ollama_current_status = f"error: {type(e).__name__}" # More specific error
    else:
        ollama_current_status = "not_configured"

    # Check Redis status
    # If initial connection failed, redis_client will be None
    current_redis_status = initial_redis_status
    if redis_client:
        try:
            redis_client.ping()
            current_redis_status = "ok" # If ping succeeds, update status to ok
        except redis.exceptions.ConnectionError as e:
            current_redis_status = f"error: {str(e)}" # Update status with current error
            # Optionally, try to reconnect or set redis_client to None
            # For a health check, just reporting the current state is often enough.
    elif initial_redis_status.startswith("error"): # If it failed at startup
        current_redis_status = initial_redis_status # Report the startup error
    else: # If it was never initialized and somehow not caught by initial_redis_status
        current_redis_status = "error: not initialized"


    # Check Celery worker status
    celery_status = "not_available"
    if CELERY_AVAILABLE and transcribe_audio_task:
        try:
            # Try to get worker stats
            from celery import current_app
            inspect = current_app.control.inspect()
            active_workers = inspect.active()
            if active_workers:
                celery_status = "ok"
                logger.info(f"Celery workers active: {list(active_workers.keys())}")
            else:
                celery_status = "no_workers"
                logger.warning("No active Celery workers found")
        except Exception as e:
            celery_status = f"error: {str(e)}"
            logger.error(f"Error checking Celery worker status: {e}")
    else:
        celery_status = "not_imported"

    return {
        "fastapi": "ok",
        "redis": current_redis_status,
        "ollama": ollama_current_status,
        "celery": celery_status
    }

# Pydantic Model for /transcribe_url
class TranscribeUrlRequest(BaseModel):
    url: str
    s3_results_path: Optional[str] = None

# Pydantic Model for /transcribe_s3
class TranscribeS3Request(BaseModel):
    s3_input_path: str
    s3_results_path: Optional[str] = None

# Helper function for S3 validation
def validate_s3_settings(s3_results_path: Optional[str]):
    if s3_results_path:
        if not (S3_STORAGE_BUCKET and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY):
            raise HTTPException(
                status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
                detail="S3 storage is not configured. Missing S3_STORAGE_BUCKET, AWS_ACCESS_KEY_ID, or AWS_SECRET_ACCESS_KEY."
            )
        if s3_results_path.startswith("/") or s3_results_path.endswith("/") or ".." in s3_results_path:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid s3_results_path format. It must not start/end with '/' or contain '..'."
            )

# Helper function to sanitize filenames
def sanitize_filename(filename: str, default: str = "audio.wav") -> str:
    safe_filename = "".join(c if c.isalnum() or c in ['.', '_'] else '_' for c in filename)
    safe_filename = (safe_filename[:100] if len(safe_filename) > 100 else safe_filename) or default
    return safe_filename

# Helper function to create S3 client
def create_s3_client():
    if not (S3_STORAGE_BUCKET and AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY):
        raise HTTPException(
            status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
            detail="S3 is not configured. Missing S3_STORAGE_BUCKET, AWS_ACCESS_KEY_ID, or AWS_SECRET_ACCESS_KEY."
        )
    
    s3_client_params = {
        "aws_access_key_id": AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
    }
    if AWS_REGION:
        s3_client_params["region_name"] = AWS_REGION
    if AWS_ENDPOINT: 
        s3_client_params["endpoint_url"] = AWS_ENDPOINT
    
    return boto3.client("s3", **s3_client_params)

# Helper function to create task metadata and dispatch transcription
async def create_and_dispatch_transcription(
    task_id: str,
    client_id: str,
    audio_file_path: str,
    s3_results_path: Optional[str],
    original_filename: str,
    task_type: str,
    additional_metadata: dict = None
):
    logger.info(f"Creating transcription task: task_id={task_id}, client_id={client_id}, task_type={task_type}, s3_results_path={s3_results_path}")
    
    if redis_client:
        metadata = {
            "client_id": client_id,
            "status": "PENDING_UPLOADED" if task_type == "file_upload" else "PENDING_DOWNLOADED",
            "s3_results_path": s3_results_path,
            "original_filename": original_filename,
            "saved_filename": os.path.basename(audio_file_path),
            "upload_time" if task_type == "file_upload" else "download_time": datetime.utcnow().isoformat(),
            "task_type": task_type
        }
        if additional_metadata:
            metadata.update(additional_metadata)
        
        try:
            redis_client.set(f"task:{task_id}", json.dumps(metadata))
            logger.info(f"Stored initial metadata in Redis for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to store metadata in Redis for task {task_id}: {e}")
    else:
        logger.warning(f"Redis client not available, cannot store metadata for task {task_id}")

    dispatch_result = dispatch_transcription_task(task_id=task_id, audio_path=audio_file_path, client_id=client_id, s3_results_path=s3_results_path, original_filename=original_filename)
    logger.info(f"Dispatch result for task {task_id}: {dispatch_result}")
    return {"task_id": task_id}

# Import Celery task
try:
    from ..tasks.transcription import transcribe_audio_task
    logger.info("Successfully imported Celery transcription task")
    CELERY_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import Celery transcription task: {e}")
    transcribe_audio_task = None
    CELERY_AVAILABLE = False

def dispatch_transcription_task(task_id: str, audio_path: str, client_id: str, s3_results_path: Optional[str] = None, original_filename: Optional[str] = None):
    logger.info(f"Dispatching transcription task: task_id={task_id}, audio_path={audio_path}, client_id={client_id}, s3_results_path={s3_results_path}, original_filename={original_filename}")
    
    if not CELERY_AVAILABLE or transcribe_audio_task is None:
        logger.error(f"Celery task not available for task {task_id}")
        if redis_client:
            metadata_key = f"task:{task_id}"
            raw_metadata = redis_client.get(metadata_key)
            if raw_metadata:
                metadata = json.loads(raw_metadata)
                metadata["status"] = "FAILED"
                metadata["error_message"] = "Celery worker not available"
                metadata["celery_dispatch_time"] = datetime.utcnow().isoformat()
                redis_client.set(metadata_key, json.dumps(metadata))
        return {"task_id": task_id, "status": "FAILED", "error": "Celery worker not available"}
    
    try:
        # Dispatch actual Celery task
        celery_result = transcribe_audio_task.delay(
            task_id=task_id,
            audio_path_in_cache=audio_path,
            client_id=client_id,
            s3_path_suffix=s3_results_path,
            original_filename=original_filename
        )
        
        logger.info(f"Successfully dispatched Celery task {celery_result.id} for task {task_id}")
        
        # Update Redis with Celery task ID
        if redis_client:
            metadata_key = f"task:{task_id}"
            raw_metadata = redis_client.get(metadata_key)
            if raw_metadata:
                metadata = json.loads(raw_metadata)
                metadata["status"] = "PENDING_CELERY_DISPATCH"
                metadata["celery_task_id"] = celery_result.id
                metadata["celery_dispatch_time"] = datetime.utcnow().isoformat()
                redis_client.set(metadata_key, json.dumps(metadata))
                logger.info(f"Updated Redis metadata for task {task_id} with Celery task ID {celery_result.id}")
            else:
                logger.warning(f"No initial metadata found in Redis for task {task_id} during dispatch")
        
        return {"task_id": task_id, "celery_task_id": celery_result.id, "status": "DISPATCHED"}
        
    except Exception as e:
        logger.error(f"Failed to dispatch Celery task for {task_id}: {e}", exc_info=True)
        if redis_client:
            metadata_key = f"task:{task_id}"
            raw_metadata = redis_client.get(metadata_key)
            if raw_metadata:
                metadata = json.loads(raw_metadata)
                metadata["status"] = "FAILED"
                metadata["error_message"] = f"Failed to dispatch Celery task: {str(e)}"
                metadata["celery_dispatch_time"] = datetime.utcnow().isoformat()
                redis_client.set(metadata_key, json.dumps(metadata))
        return {"task_id": task_id, "status": "FAILED", "error": str(e)}


@app.post("/transcribe")
async def transcribe_file(
    client_id: Optional[str] = Header(None, alias="client_id"),
    file: UploadFile = File(...),
    s3_results_path: Optional[str] = Form(None)
):
    if not client_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="client_id header is required.")
    
    # Basic file size validation (100MB limit)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    if hasattr(file, 'size') and file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size exceeds 100MB limit.")
    
    if file.content_type not in ["audio/wav", "audio/x-wav"]:
        raise HTTPException(status_code=http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported file type. Only WAV files are accepted.")

    validate_s3_settings(s3_results_path)

    task_id = str(uuid.uuid4())
    safe_filename = sanitize_filename(file.filename, "uploaded_audio.wav")
    audio_file_path = os.path.join(CACHE_DIR, f"{task_id}_{safe_filename}")

    try:
        with open(audio_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        print(f"Error saving uploaded file: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not save uploaded file.")
    finally:
        file.file.close()

    return await create_and_dispatch_transcription(
        task_id=task_id,
        client_id=client_id,
        audio_file_path=audio_file_path,
        s3_results_path=s3_results_path,
        original_filename=file.filename,
        task_type="file_upload"
    )


@app.post("/transcribe_url")
async def transcribe_url_endpoint(
    request_data: TranscribeUrlRequest,
    client_id: Optional[str] = Header(None, alias="client_id")
):
    if not client_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="client_id header is required.")

    validate_s3_settings(request_data.s3_results_path)
    
    task_id = str(uuid.uuid4())
    url_filename = request_data.url.split("/")[-1] if request_data.url else ""
    safe_filename = sanitize_filename(url_filename, "downloaded_audio.wav")
    audio_file_path = os.path.join(CACHE_DIR, f"{task_id}_{safe_filename}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(request_data.url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "").lower()
            is_wav_content_type = "audio/wav" in content_type or "audio/x-wav" in content_type
            is_wav_extension = request_data.url.lower().endswith(".wav")

            if not (is_wav_content_type or is_wav_extension):
                 raise HTTPException(status_code=http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"Unsupported content type '{content_type}' and URL does not end with .wav. Only WAV audio is supported.")

            with open(audio_file_path, "wb") as f:
                f.write(response.content)
    except httpx.TimeoutException:
        raise HTTPException(status_code=http_status.HTTP_408_REQUEST_TIMEOUT, detail="Timeout downloading audio from URL.")
    except httpx.HTTPStatusError as e:
        print(f"HTTP error downloading audio from URL {request_data.url}: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Error downloading audio from URL.")
    except httpx.RequestError as e:
        print(f"Request error downloading audio from URL {request_data.url}: {e}")
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Could not connect to or download from URL.")
    except Exception as e:
        print(f"Error processing URL download {request_data.url}: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not download or save audio from URL.")

    return await create_and_dispatch_transcription(
        task_id=task_id,
        client_id=client_id,
        audio_file_path=audio_file_path,
        s3_results_path=request_data.s3_results_path,
        original_filename=safe_filename,
        task_type="url_download",
        additional_metadata={"original_url": request_data.url}
    )


@app.post("/transcribe_s3")
async def transcribe_s3_endpoint(
    request_data: TranscribeS3Request,
    client_id: Optional[str] = Header(None, alias="client_id")
):
    logger.info(f"Received S3 transcription request: client_id={client_id}, s3_input_path={request_data.s3_input_path}, s3_results_path={request_data.s3_results_path}")
    
    if not client_id:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="client_id header is required.")

    validate_s3_settings(request_data.s3_results_path)
    
    # Create S3 client for downloading the input file
    logger.info(f"Creating S3 client for downloading {request_data.s3_input_path}")
    s3_client = create_s3_client()
    
    task_id = str(uuid.uuid4())
    s3_filename = request_data.s3_input_path.split("/")[-1] if request_data.s3_input_path else ""
    safe_filename = sanitize_filename(s3_filename, "s3_audio.wav")
    audio_file_path = os.path.join(CACHE_DIR, f"{task_id}_{safe_filename}")
    
    logger.info(f"Generated task_id={task_id}, local_path={audio_file_path}")

    try:
        # Download file from S3 to local cache
        logger.info(f"Downloading S3 file: bucket={S3_STORAGE_BUCKET}, key={request_data.s3_input_path}, local_path={audio_file_path}")
        s3_client.download_file(S3_STORAGE_BUCKET, request_data.s3_input_path, audio_file_path)
        logger.info(f"Successfully downloaded S3 file to {audio_file_path}")
        
        # Check file size
        file_size = os.path.getsize(audio_file_path)
        logger.info(f"Downloaded file size: {file_size} bytes")
        
        # Validate it's a WAV file by checking extension (basic validation)
        if not request_data.s3_input_path.lower().endswith('.wav'):
            logger.warning(f"Invalid file extension for S3 key: {request_data.s3_input_path}")
            os.remove(audio_file_path)  # Clean up downloaded file
            raise HTTPException(
                status_code=http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 
                detail=f"Unsupported file type. S3 input path must end with .wav extension."
            )
            
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'NoSuchKey':
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"S3 input path '{request_data.s3_input_path}' not found in bucket '{S3_STORAGE_BUCKET}'."
            )
        elif error_code == 'NoSuchBucket':
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"S3 bucket '{S3_STORAGE_BUCKET}' not found."
            )
        else:
            print(f"S3 ClientError downloading {request_data.s3_input_path}: {e}")
            raise HTTPException(
                status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Error downloading file from S3: {error_code}"
            )
    except (NoCredentialsError, PartialCredentialsError) as e:
        print(f"S3 credentials error: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 credentials error."
        )
    except Exception as e:
        print(f"Error downloading S3 file {request_data.s3_input_path}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not download file from S3."
        )

    return await create_and_dispatch_transcription(
        task_id=task_id,
        client_id=client_id,
        audio_file_path=audio_file_path,
        s3_results_path=request_data.s3_results_path,
        original_filename=safe_filename,
        task_type="s3_download",
        additional_metadata={"original_s3_input_path": request_data.s3_input_path}
    )


@app.get("/status/{task_id}")
async def get_task_status(task_id: str, client_id: Optional[str] = Header(None, alias="client_id")):
    if not redis_client:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis service not available.")
    
    task_key = f"task:{task_id}"
    raw_metadata = redis_client.get(task_key)
    if not raw_metadata:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found.")
    
    metadata = json.loads(raw_metadata)
    
    if client_id and metadata.get("client_id") != client_id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Access denied. Client ID does not match task owner.")
        
    return {"task_id": task_id, "status": metadata.get("status", "UNKNOWN"), "details": metadata}


@app.get("/download/{task_id}")
async def download_transcription_file(
    task_id: str,
    fmt: str = "json", # Query parameter, default "json"
    client_id: Optional[str] = Header(None, alias="client_id")
):
    if not redis_client:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis service not available.")
    if fmt not in ["json", "md"]:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid format. Must be 'json' or 'md'.")

    task_key = f"task:{task_id}"
    raw_metadata = redis_client.get(task_key)
    if not raw_metadata:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found.")
    
    metadata = json.loads(raw_metadata)

    if client_id and metadata.get("client_id") != client_id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Access denied. Client ID does not match task owner.")
    
    if metadata.get("s3_results_path"):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Files processed with s3_results_path must be downloaded directly from S3.")
    
    if metadata.get("status") != "COMPLETED": # Assuming "COMPLETED" is the success status from Celery
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"Task status is '{metadata.get('status')}'. Download is only available for COMPLETED tasks.")
    
    output_filename_key = f"transcribed_{fmt}_file" # e.g. transcribed_json_file
    relative_file_path = metadata.get(output_filename_key)

    if not relative_file_path:
        print(f"Warning: Task {task_id} metadata does not contain key '{output_filename_key}'. Metadata: {metadata}")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Transcription file path for format '{fmt}' not found in task metadata.")

    file_path = os.path.join(CACHE_DIR, relative_file_path)

    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found for task {task_id}, though metadata references it.")
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=f"Transcription file for format '{fmt}' not found on server.")
    
    metadata["last_download_time"] = datetime.utcnow().isoformat()
    redis_client.set(task_key, json.dumps(metadata))
    
    # Determine media type based on format
    media_type = "application/json" if fmt == "json" else "text/markdown"
    
    return FileResponse(path=file_path, filename=os.path.basename(file_path), media_type=media_type)


@app.delete("/release/{task_id}")
async def release_task_resources(task_id: str, client_id: Optional[str] = Header(None, alias="client_id")):
    if not redis_client:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis service not available.")

    task_key = f"task:{task_id}"
    raw_metadata = redis_client.get(task_key)
    if not raw_metadata:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found.")
    
    metadata = json.loads(raw_metadata)

    if client_id and metadata.get("client_id") != client_id:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Access denied. Client ID does not match task owner.")

    files_to_delete = []
    # Original audio file saved in cache (not from S3)
    if metadata.get("saved_filename") and not metadata.get("s3_results_path"): # Check it's not an S3 task for original audio
        files_to_delete.append(os.path.join(CACHE_DIR, metadata["saved_filename"]))
    
    # Transcribed output files (always in cache)
    if metadata.get("transcribed_json_file"): 
        files_to_delete.append(os.path.join(CACHE_DIR, metadata["transcribed_json_file"]))
    if metadata.get("transcribed_md_file"):
        files_to_delete.append(os.path.join(CACHE_DIR, metadata["transcribed_md_file"]))
    
    deleted_files_count = 0
    not_found_files_count = 0
    errors_deleting_files = []

    for file_path in files_to_delete:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_files_count += 1
            else:
                not_found_files_count +=1
                print(f"Info: File {file_path} for task {task_id} was not found during release.")
        except OSError as e:
            print(f"Error deleting file {file_path} for task {task_id}: {e}")
            errors_deleting_files.append(file_path)


    if not errors_deleting_files:
        redis_client.delete(task_key)
        redis_key_deleted = True
    else:
        # If there were errors deleting files, we might choose not to delete the Redis key
        # to allow for manual cleanup or investigation.
        print(f"Warning: Errors occurred while deleting files for task {task_id}. Redis key not deleted.")
        redis_key_deleted = False
    
    return {
        "message": "Task resources release processed.",
        "deleted_cache_files": deleted_files_count,
        "files_not_found_in_cache": not_found_files_count,
        "redis_key_deleted": redis_key_deleted,
        "errors_deleting_files": errors_deleting_files if errors_deleting_files else None
    }


@app.get("/queue")
async def get_queue_status():
    if not redis_client:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis service not available.")
    
    queued_tasks = 0
    task_keys = []
    try:
        task_keys = redis_client.keys("task:*")
    except redis.exceptions.RedisError as e:
        print(f"Error accessing Redis for keys: {e}")
        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not query Redis for task keys.")

    active_states = [
        "PENDING_UPLOADED", 
        "PENDING_DOWNLOADED", 
        "PENDING_CELERY_DISPATCH", 
        "PROCESSING",
        "RETRYING" # Assuming Celery might set such a state
    ] 
    
    for task_key in task_keys: # Keys are already strings
        raw_metadata = None
        try:
            raw_metadata = redis_client.get(task_key) # Use decoded key
        except redis.exceptions.RedisError as e:
            print(f"Error fetching metadata for key {task_key}: {e}")
            continue # Skip this key if there's an error

        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
                if metadata.get("status") in active_states:
                    queued_tasks += 1
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for task key {task_key}: {e}")
                # Optionally count as an error or inconsistent state
    
    return {"active_tasks_in_queue": queued_tasks, "total_tracked_tasks": len(task_keys)}


@app.get("/debug/task/{task_id}")
async def debug_task_info(task_id: str, client_id: Optional[str] = Header(None, alias="client_id")):
    """Debug endpoint to get detailed task information"""
    if not redis_client:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis service not available.")
    
    task_key = f"task:{task_id}"
    raw_metadata = redis_client.get(task_key)
    if not raw_metadata:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Task not found.")
    
    metadata = json.loads(raw_metadata)
    
    # Add Celery task status if available
    celery_info = {}
    if CELERY_AVAILABLE and transcribe_audio_task and metadata.get("celery_task_id"):
        try:
            from celery.result import AsyncResult
            celery_result = AsyncResult(metadata["celery_task_id"])
            celery_info = {
                "celery_task_id": metadata["celery_task_id"],
                "celery_status": celery_result.status,
                "celery_result": str(celery_result.result) if celery_result.result else None,
                "celery_traceback": celery_result.traceback if celery_result.failed() else None
            }
        except Exception as e:
            celery_info = {"celery_error": str(e)}
    
    # Check if file exists
    file_info = {}
    if metadata.get("saved_filename"):
        file_path = os.path.join(CACHE_DIR, metadata["saved_filename"])
        file_info = {
            "file_exists": os.path.exists(file_path),
            "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else None
        }
    
    return {
        "task_id": task_id,
        "metadata": metadata,
        "celery_info": celery_info,
        "file_info": file_info,
        "cache_dir": CACHE_DIR
    }


if __name__ == "__main__":
    import uvicorn
    # This is for local development/testing directly with Python
    # In Docker, Uvicorn is run as specified in the Dockerfile CMD
    uvicorn.run(app, host="0.0.0.0", port=8000)
