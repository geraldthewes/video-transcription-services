# Video Transcription Services

A microservice for audio/video transcription using AI-powered topic segmentation and embeddings. The service processes WAV files asynchronously and generates structured transcripts in JSON and Markdown formats.

## Features

- **Asynchronous Processing**: Uses Celery workers for background transcription
- **Multiple Input Methods**: Upload files directly, provide URLs, or specify S3 keys
- **Structured Output**: Generates JSON and Markdown transcripts with topic segmentation
- **S3 Integration**: Optional storage of results in AWS S3 or compatible storage
- **Task Management**: Track processing status and manage file lifecycle
- **AI-Powered**: Uses Ollama for embeddings and topic analysis

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Ollama server running (for AI processing)

### 1. Setup Environment

Copy the environment template and configure:

```bash
cp env.template .env
```

Edit `.env` with your settings:

```bash
# Required: Ollama server for AI processing
OLLAMA_HOST=http://ollama:11434

# Optional: AWS S3 integration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_STORAGE_BUCKET=your_bucket_name
AWS_ENDPOINT=  # For MinIO or custom S3 endpoints
```

### 2. Start Services

```bash
# Build and start all services
docker compose build
docker compose up

# Or run in background
docker compose up -d
```

This starts:
- **API Server** (port 8000): FastAPI web service
- **Worker**: Celery worker for transcription processing  
- **Redis**: Task queue and metadata storage

### 3. Verify Setup

Check service health:

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "fastapi": "ok",
  "redis": "ok", 
  "ollama": "ok",
  "celery": "ok"
}
```

### 4. Access Interactive API Documentation

FastAPI automatically provides interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These interfaces allow you to:
- Browse all available endpoints
- View request/response schemas
- Test API calls directly from the browser
- Download OpenAPI specifications

## API Usage

### Upload File for Transcription

```bash
curl -X POST "http://localhost:8000/transcribe" \
  -H "client_id: your-client-id" \
  -F "file=@audio.wav"
```

Response:
```json
{
  "task_id": "uuid-task-id"
}
```

### Transcribe from URL

Transcribe audio files from any publicly accessible URL:

```bash
curl -X POST "http://localhost:8000/transcribe_url" \
  -H "client_id: your-client-id" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/path/to/audio.wav"
  }'
```

With S3 storage for results:

```bash
curl -X POST "http://localhost:8000/transcribe_url" \
  -H "client_id: your-client-id" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/path/to/audio.wav",
    "s3_path": "optional/path/for/results"
  }'
```

**Note**: The URL must be publicly accessible or use authentication mechanisms supported by standard HTTP clients (like presigned URLs for S3).

### Transcribe from S3

Transcribe audio files directly from S3 using the configured S3 credentials:

```bash
curl -X POST "http://localhost:8000/transcribe_s3" \
  -H "client_id: your-client-id" \
  -H "Content-Type: application/json" \
  -d '{
    "s3_key": "path/to/audio.wav"
  }'
```

With S3 storage for results:

```bash
curl -X POST "http://localhost:8000/transcribe_s3" \
  -H "client_id: your-client-id" \
  -H "Content-Type: application/json" \
  -d '{
    "s3_key": "path/to/audio.wav",
    "s3_path": "transcribed/results"
  }'
```

**Note**: Requires S3 credentials to be configured in environment variables. The input file is downloaded from the configured S3 bucket to local cache for processing.

### Check Status

```bash
curl -H "client_id: your-client-id" \
  "http://localhost:8000/status/uuid-task-id"
```

Response:
```json
{
  "task_id": "uuid-task-id",
  "status": "COMPLETED",
  "details": {
    "client_id": "your-client-id",
    "upload_time": "2024-01-01T00:00:00",
    "processing_end_time": "2024-01-01T00:05:00"
  }
}
```

Status values: `PENDING_UPLOADED`, `PROCESSING`, `COMPLETED`, `FAILED`

### Download Results

```bash
# Download JSON format
curl -H "client_id: your-client-id" \
  "http://localhost:8000/download/uuid-task-id?fmt=json" \
  -o transcript.json

# Download Markdown format  
curl -H "client_id: your-client-id" \
  "http://localhost:8000/download/uuid-task-id?fmt=md" \
  -o transcript.md
```

### Clean Up Resources

```bash
curl -X DELETE -H "client_id: your-client-id" \
  "http://localhost:8000/release/uuid-task-id"
```

### Monitor Queue

```bash
curl "http://localhost:8000/queue"
```

Response:
```json
{
  "active_tasks_in_queue": 2,
  "total_tracked_tasks": 15
}
```

### Debug Task Issues

Get detailed information about a specific task for troubleshooting:

```bash
curl -H "client_id: your-client-id" \
  "http://localhost:8000/debug/task/uuid-task-id"
```

Response includes:
```json
{
  "task_id": "uuid-task-id",
  "metadata": {
    "client_id": "your-client-id",
    "status": "PROCESSING",
    "celery_task_id": "celery-uuid",
    "file_exists": true
  },
  "celery_info": {
    "celery_status": "PENDING",
    "celery_result": null
  },
  "file_info": {
    "file_exists": true,
    "file_size": 1048576
  }
}
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OLLAMA_HOST` | Yes | Ollama server URL for AI processing |
| `REDIS_HOST` | No | Redis hostname (default: localhost) |
| `REDIS_PORT` | No | Redis port (default: 6379) |
| `CACHE_EXPIRY` | No | File retention in seconds (default: 604800 = 7 days) |
| `AWS_ACCESS_KEY_ID` | For S3 | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | For S3 | AWS secret key |
| `S3_STORAGE_BUCKET` | For S3 | S3 bucket name |
| `AWS_REGION` | For S3 | AWS region |
| `AWS_ENDPOINT` | For S3 | Custom S3 endpoint (MinIO, etc.) |

### File Limits

- **Max file size**: 100MB
- **Supported formats**: WAV files only (`audio/wav`, `audio/x-wav`)
- **Cache retention**: 7 days (configurable via `CACHE_EXPIRY`)

### S3 Storage

When `s3_path` is provided in requests, results are stored at:
```
s3://{S3_STORAGE_BUCKET}/transcriber/{client_id}/{s3_path}.{json|md}
```

Files stored in S3 are not automatically deleted and must be managed externally.

## Architecture

- **FastAPI**: Web API server handling HTTP requests
- **Celery**: Background task processing for transcription
- **Redis**: Message broker and metadata storage
- **multistep-transcriber**: AI transcription engine with topic segmentation

## Development

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run API server locally
uvicorn transcriber_service.app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker
celery -A transcriber_service.tasks.transcription.celery_app worker -l INFO
```

### API Documentation

FastAPI provides comprehensive interactive documentation:

- **Swagger UI**: `http://localhost:8000/docs` - Interactive API explorer
- **ReDoc**: `http://localhost:8000/redoc` - Clean, three-panel documentation  
- **OpenAPI JSON**: `http://localhost:8000/openapi.json` - Machine-readable API spec

Use these for development, testing, and integration planning.

## Troubleshooting

### Common Issues

1. **Ollama connection failed**: Ensure Ollama server is running and accessible
2. **Redis connection failed**: Check Redis container status  
3. **File upload rejected**: Verify file is WAV format and under 100MB
4. **S3 upload failed**: Check AWS credentials and bucket permissions
5. **Task stuck at PENDING_CELERY_DISPATCH**: Celery worker not running or not connected
6. **Task stuck at PROCESSING**: Check worker logs for transcription errors

### Debug Workflow

For stuck tasks, follow this troubleshooting sequence:

1. **Check overall health**:
   ```bash
   curl http://localhost:8000/health
   ```
   
2. **Get detailed task information**:
   ```bash
   curl -H "client_id: your-client-id" \
     "http://localhost:8000/debug/task/your-task-id"
   ```

3. **Check service logs**:
   ```bash
   # View all service logs
   docker compose logs
   
   # View specific service logs with timestamps
   docker compose logs -t app
   docker compose logs -t worker
   docker compose logs -t redis
   
   # Follow logs in real-time
   docker compose logs -f worker
   ```

4. **Monitor queue status**:
   ```bash
   curl "http://localhost:8000/queue"
   ```

### Status Meanings

- **`PENDING_UPLOADED/DOWNLOADED`**: File received, waiting for Celery dispatch
- **`PENDING_CELERY_DISPATCH`**: Task sent to Celery, waiting for worker pickup
- **`PROCESSING`**: Worker is actively transcribing the audio
- **`COMPLETED`**: Transcription finished successfully
- **`FAILED`**: Error occurred during processing

### Health Check Statuses

- **`celery: "ok"`**: Workers are active and responding
- **`celery: "no_workers"`**: No Celery workers found
- **`celery: "not_imported"`**: Celery task import failed
- **`celery: "error: ..."`**: Celery inspection error

### Restart Services

If issues persist, restart the services:
```bash
docker compose down
docker compose up -d

# Watch logs during startup
docker compose logs -f
```

### Monitor Service Health

Continuously monitor service health:
```bash
watch -n 5 "curl -s http://localhost:8000/health | jq"
```

## License

See LICENSE file for details.
