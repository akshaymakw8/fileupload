import json
import base64
import boto3
import os
import time
from datetime import datetime

# Get environment variables
s3 = boto3.client('s3')
BUCKET_NAME = os.getenv("BUCKET_NAME")
UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD")
CLIENT_PREFIX = os.getenv("CLIENT_PREFIX", "default")

# Allowed file extensions
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "png", "jpg", "jpeg", "eml", "msg"}

def build_response(status_code, message):
    """
    Helper function to build a response that includes
    CORS headers for AWS_PROXY integration.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Access-Control-Allow-Credentials": "true"
        },
        "body": json.dumps({"body": message}) if isinstance(message, str) else json.dumps(message)
    }

def lambda_handler(event, context):
    # Handle preflight OPTIONS request
    if event.get("httpMethod") == "OPTIONS":
        return build_response(200, {"message": "CORS preflight response"})

    try:
        # Log request details for debugging
        print(f"Processing request for client: {CLIENT_PREFIX}")
        print(f"Using S3 bucket: {BUCKET_NAME}")

        # If using API Gateway proxy, 'body' is a JSON string
        body = json.loads(event["body"]) if "body" in event else event

        if body.get("password") != UPLOAD_PASSWORD:
            return build_response(401, {"error": "Unauthorized: Incorrect password"})

        files = body.get("files", [])
        if not files:
            return build_response(400, {"error": "No files found in the request"})

        if len(files) > 10:
            return build_response(400, {"error": "You can upload a maximum of 10 files"})

        uploaded_files = []
        timestamp = int(time.time())
        date_folder = datetime.now().strftime("%Y-%m-%d")

        for file in files:
            # Get original filename
            original_filename = file["name"]
            file_extension = original_filename.split('.')[-1].lower()

            if file_extension not in ALLOWED_EXTENSIONS:
                return build_response(
                    400,
                    {"error": f"Invalid file type: {original_filename}. Allowed types: PDF, Word, Excel, PNG, JPG, Email."}
                )

            # Create a sanitized filename to avoid S3 key issues
            import re
            sanitized_filename = re.sub(r'[^\w\.-]', '_', original_filename)

            # Create the S3 key with date-based organization
            s3_key = f"{date_folder}/{timestamp}_{sanitized_filename}"

            try:
                file_content = base64.b64decode(file["content"])
                s3.put_object(
                    Bucket=BUCKET_NAME,
                    Key=s3_key,
                    Body=file_content,
                    Metadata={
                        'client': CLIENT_PREFIX,
                        'original-filename': original_filename
                    }
                )
                uploaded_files.append({
                    "originalName": original_filename,
                    "s3Key": s3_key
                })
            except Exception as e:
                print(f"Error uploading file {original_filename}: {str(e)}")
                return build_response(500, {"error": f"Error uploading {original_filename}: {str(e)}"})

        return build_response(200, {
            "message": "File(s) uploaded successfully!",
            "files": uploaded_files,
            "client": CLIENT_PREFIX
        })
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return build_response(500, {"error": f"Error: {str(e)}"})
