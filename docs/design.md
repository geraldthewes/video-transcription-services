# Sumnmary

mutistep-trancriber is video ingestion pipeline that is a python package that takes an input wav file and creates a transcript.
Create a service as a docker image that exposes this transcriber using docker. Since video transcription can take a few minutes the service must be asynchoneous. These set of all services are tied together using docker compose.

# Architecture

* Create web services using FastAPI
** /transcribe and /transcribe_url to request a transcription of a video or audio recording. The results can either be retrieved via another web service call, or the request can specify an S3 path used it to store the results of the transcription.
   
** 
** /status/<task_id> for checking transcription status
** /download/<task_id> to downlod transcribed file. Two versions are available (JSON and Markdown)
** /release/<task_id> to delete all files once client has dowmnloaded
** /queue  return the numbers of video jobs currently in the queue to be processed.
* Execute the transcription requests asynchroneously using Celery and an embedded redis server
* Transcription is performed by the python multistep_transcriber (mst) package at  https://github.com/geraldthewes/multistep-transcriber.git packaged in it's own docker image
* The service is not meant to scale in itself and the expecation is the server is only processing a single request at the time (but can enqueue many requests)
* Transcription files are only kept for 7 days (a configurable parameter named CACHE_EXPIRY in seconds)
* Storage for raw transcription file and trsnacribed result should be stored in a cache directory that is shared between the job and the FastAPI web server
* Large File Handling: For WAV files, consider size limits; uploads may need streaming, and URLs may be better for large files hosted externally.
* Monitoring: Use Flower for Celery task monitoring, tracking progress and worker health.
* Security: Store API keys for external LLMs in environment variables, avoiding any hardcoding.

# Tasks

* Create a docker compose service including the transcriber service and the embedded redis server

* Make use of the OLLAMA_HOST, CACHE_EXPIRY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_STORAGE_BUCKET  S3 keys  environment variables

* Create FastCGI server, using uvcorn  implementing the end points described above: transcribe, status, download, release and one called /docs to contain the auto generated documentation the API. Expose the port for the web server.

** /transcribe: Accepts a WAV file upload (UploadFile in FastAPI) or optionally a URL. 

If an s3 path is specified using the argument s3_path, the transcription results are stored in S3 at that path prefixed by the prefix 'transcriber' and the cliendId used as the key and the bucket is the one specified in S3_STORAGE_BUCKET, otherwise save the file temporarily in the file cache, trigger a Celery task, and return a task ID. Transcribe returns an error if an s3_path is specified and the S3 environment files are not set ( AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_STORAGE_BUCKET)

The clientId is a string, typically a GUID to be managed by the client.

The client is responsible of ensuring the path is unique.

In summary the URL for the S3 storage will be s3://<S3_STORAGE_BUCKET>/transcriber/<clientID>/<s3_path>.

In S3 both the JSON and the md version of the transcript will be stored.

 The Video/audio is expected to be uploaded as bytes and a content type specified. For now only handle wav files
 
/transcribe_url is the same as /transcribe but this is a POST taking in a JDON document as input

{
 "url": "url to audio/video",
 "s3_path": optional s3_path
}

And the audio/video is downloaded from the specified url.

Appropriate HTTP error are returned if there are issues, like not uploading data of the right type, or 200 if success.

** /status/<task_id>: Checks the task status using Celery’s AsyncResult, returning the following styatus: pending, processing, completed, or failed.

** /download/<task_id>?fmt=[md|json]  Download the transcribed file in JSON or markdown format. This calls fails if an s3_path was specified in the transcribe request.

** /release/<task_id>  Release all files related to that task 

** /queue to return number of transcriptions jobs in the queue to be processed

** /health Health checkpoint to check status of FastAPI, Redis and Ollama

* All API calls should include a clientId passed in the HTTP request header, and this meta information should be stored as well as key time stamps of the processing (upload time, transcription completion time, last download time) 

* Cache management is somewhat handled by the mst package, which handles caching of an individual video/audio transcription and management of the cached files. But the service will need to handle when the teranscription was completed and handle the deletion of expired processing. Note even failed processing files should be cleared after CACHE_EXIRY seconds. The transcript stored on s3 are not deleted and management of s3 is the responsability the client.

The uploaded video/audio and cache should be stored in a volume to survive bring the service up/down or a restart.

* Create the job that looks are videos to transcribe and transcribe them. That job will need access to the host GPU and an external Ollama server. Before transcribving a video, the job should delete all expired files in the cache. Install all required dependencies for tje job in the docker image.  The transcrition package is located here https://github.com/geraldthewes/multistep-transcriber.git, information on how to use it is in the repository. Read it.


* Use a base image of python:3.12

* Write sample client code and test harness.

* Write documentation on how to setup and use the service. Documentation of methods should be in  the code as docstring and documentation managed using mkdocs. No code documentation should be stored in the docs folder using markdown. There should be a README.md for the service that gives a brief intriduction and installation instructions.







# Open Questions

Update description to contain optional S3 information for storage




