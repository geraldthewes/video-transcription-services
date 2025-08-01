# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a microservice for audio/video transcription using AI-powered topic segmentation and embeddings. The service processes WAV files asynchronously and generates structured transcripts in JSON and Markdown formats using the `multistep-transcriber` package.

## Common Development Commands

### Running the Service

```bash
# Build and start all services
docker compose build
docker compose up

# Run in background
docker compose up -d

# View logs
docker compose logs -f
docker compose logs -t worker
docker compose logs -t app
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run API server locally
uvicorn transcriber_service.app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker locally
celery -A transcriber_service.tasks.transcription.celery_app worker -l INFO
```

### Health Checks

```bash
# Check service health
curl http://localhost:8000/health

# Check queue status
curl "http://localhost:8000/queue"

# Debug specific task
curl -H "client_id: your-client-id" "http://localhost:8000/debug/task/uuid-task-id"
```

## Architecture

The service follows a microservice architecture with these key components:

### Services
- **FastAPI App** (port 8000): HTTP API server handling requests
- **Celery Worker**: Background task processor with GPU support for transcription  
- **Redis**: Message broker and metadata storage

### Key Modules
- `transcriber_service/app/main.py`: FastAPI application with all REST endpoints
- `transcriber_service/tasks/transcription.py`: Celery tasks for audio processing
- `transcriber_service/core/`: Core business logic (placeholder structure)

### API Endpoints
- `POST /transcribe`: Upload WAV file for transcription
- `POST /transcribe_url`: Transcribe from public URL
- `POST /transcribe_s3`: Transcribe from S3 object
- `GET /status/{task_id}`: Check transcription status
- `GET /download/{task_id}?fmt=[json|md]`: Download results
- `DELETE /release/{task_id}`: Clean up task resources
- `GET /queue`: Monitor queue status
- `GET /health`: Service health check
- `GET /debug/task/{task_id}`: Debug task information

### Task Processing Flow
1. Audio file received via upload, URL, or S3
2. File validation (WAV format, size limits)
3. Celery task dispatched to worker
4. Worker performs multi-step transcription:
   - Initial transcription using Whisper
   - Topic segmentation using embeddings
   - Format generation (JSON/Markdown)
5. Results stored locally and optionally uploaded to S3
6. Client retrieves results or they're auto-cleaned after 7 days

## Development Requirements

### Docker Environment
- Docker with GPU support (nvidia-docker)
- NVIDIA GPU with CUDA support
- At least 4GB GPU memory for model loading

### Required Environment Variables
```bash
# Required
OLLAMA_HOST=http://ollama:11434        # Ollama server for embeddings
HF_TOKEN=hf_your_token_here           # Hugging Face token for model access

# Optional S3 Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_STORAGE_BUCKET=your_bucket_name
AWS_ENDPOINT=                         # For MinIO/custom S3

# Service Configuration  
REDIS_HOST=redis                      # Redis hostname
REDIS_PORT=6379                       # Redis port
CACHE_EXPIRY=604800                   # File retention (7 days)
```

### File Constraints
- **Max file size**: 100MB
- **Supported formats**: WAV files only (`audio/wav`, `audio/x-wav`)
- **Cache retention**: 7 days (configurable via `CACHE_EXPIRY`)

## Code Structure & Patterns

### Client ID Pattern
All API calls require a `client_id` header. This is used for:
- Access control and task ownership validation
- S3 path generation: `s3://{bucket}/transcriber/{client_id}/{s3_path}.{ext}`
- Metadata tracking and debugging

### Task Status Flow
- `PENDING_UPLOADED/DOWNLOADED` → File received, awaiting Celery dispatch
- `PENDING_CELERY_DISPATCH` → Sent to Celery, awaiting worker pickup  
- `PROCESSING` → Worker actively transcribing
- `COMPLETED` → Success
- `FAILED` → Error during processing

### Error Handling
- All API endpoints include comprehensive error handling with appropriate HTTP status codes
- Celery tasks update Redis metadata with detailed error information
- Health checks validate connectivity to Redis, Ollama, and Celery workers

### Caching Strategy
- Input files cached in `/app/cache` volume
- Task-specific output files stored in `/app/cache/{task_id}/`
- Daily cleanup job removes expired files and metadata
- S3 results are not auto-deleted

## Key Dependencies

- **FastAPI**: Web framework and auto-generated API docs
- **Celery**: Asynchronous task processing
- **Redis**: Message broker and metadata storage  
- **multistep-transcriber**: Core transcription engine (from git repository)
- **spacy**: NLP processing (`en_core_web_sm` model)
- **boto3**: AWS S3 integration
- **httpx**: HTTP client for URL downloads

## Troubleshooting

### Common Issues
1. **GPU Access**: Verify `nvidia-smi` works in worker container
2. **Ollama Connection**: Check `OLLAMA_HOST` accessibility
3. **HF Token**: Ensure valid Hugging Face token with read permissions
4. **Model Downloads**: First run downloads ~2-3GB of models to container cache
5. **Memory**: Transcription requires significant GPU memory for large files

### Debug Workflow
1. Check `/health` endpoint for service status
2. Use `/debug/task/{task_id}` for detailed task information  
3. Monitor logs: `docker compose logs -f worker`
4. Verify GPU: `docker compose exec worker nvidia-smi`

### Code Conventions
- Follow functional programming principles from `docs/CONVENTIONS.md`
- Use meaningful variable names and keep functions small
- Implement comprehensive error handling
- Add logging for debugging transcription pipeline issues
- Use type hints where appropriate (`typing` module imports)