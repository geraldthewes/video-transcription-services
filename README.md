# Video Transcription Services

A microservice for audio/video transcription using AI-powered topic segmentation and embeddings. The service processes WAV files asynchronously and generates structured transcripts in JSON and Markdown formats.

## Features

- **Asynchronous Processing**: Uses Celery workers for background transcription
- **Multiple Input Methods**: Upload files directly or provide URLs
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
  "ollama": "ok"
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

### Logs

```bash
# View all service logs
docker compose logs

# View specific service logs
docker compose logs app
docker compose logs worker
docker compose logs redis
```

### Health Check

Monitor service health:
```bash
watch -n 5 "curl -s http://localhost:8000/health | jq"
```

## License

See LICENSE file for details.
