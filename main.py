from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
import os
import logging
import tempfile
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from uploader import BlobUploader
import traceback

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)

logger = logging.getLogger(__name__)
app = FastAPI(timeout=3000)  # 50 minutes

connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
blob_uploader = BlobUploader(connection_string, container_name)

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"An error occurred: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "An internal server error occurred."}
    )

import asyncio

@app.post("/upload/")
async def upload_files(files: list[UploadFile] = File(...)):
    try:
        upload_results = []
        upload_tasks = []
        for file in files:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file_path = temp_file.name
                chunk_size = 1024 * 1024
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    temp_file.write(chunk)

            upload_task = asyncio.create_task(upload_file_task(temp_file_path, file.filename))
            upload_tasks.append(upload_task)
            upload_results.append({"filename": file.filename, "status": "Upload started"})

        await asyncio.gather(*upload_tasks)

        return {"message": "Upload process completed for all files", "results": upload_results}

    except Exception as e:
        logger.error(f"Failed to start upload process due to: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to start upload process.")


async def upload_file_task(temp_file_path: str, filename: str):
    try:
        blob_uploader.upload_stream(temp_file_path, filename)
        logger.info(f"Upload of {filename} completed successfully")
    except Exception as e:
        logger.error(f"Error uploading file {filename}: {str(e)}")
        logger.error(traceback.format_exc())
    finally:
        os.remove(temp_file_path)

@app.get("/upload/progress/{filename}")
async def get_upload_progress(filename: str):
    progress = blob_uploader.get_progress(filename)
    if progress is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {"filename": filename, "progress": f"{progress:.2f}%"}

@app.get("/upload/all-progress")
async def get_all_upload_progress():
    return blob_uploader.get_all_progress()
