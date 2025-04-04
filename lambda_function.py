import json
import os
import boto3
import time
import re
from datetime import datetime

s3 = boto3.client('s3')
BUCKET_NAME = os.getenv("BUCKET_NAME", "YOUR_S3_BUCKET_NAME")
UPLOAD_PASSWORD = os.getenv("UPLOAD_PASSWORD", "CHANGE_ME")
CLIENT_PREFIX = os.getenv("CLIENT_PREFIX", "default")

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "png", "jpg", "jpeg", "eml", "msg", "txt", "gif"}

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
        "body": json.dumps(message)  # message can be dict or string
    }

def lambda_handler(event, context):
    # Handle preflight OPTIONS request
    if event.get("httpMethod") == "OPTIONS":
        return build_response(200, {"message": "CORS preflight response"})

    try:
        # If using API Gateway proxy, event["body"] is a JSON string
        body = json.loads(event["body"]) if "body" in event else event

        # Validate password
        if body.get("password") != UPLOAD_PASSWORD:
            return build_response(401, {"error": "Unauthorized: Incorrect password"})

        # Get the files array: [ { "name": ..., "type": ... }, ... ]
        files = body.get("files", [])
        if not files:
            return build_response(400, {"error": "No files found in the request"})

        if len(files) > 10:
            return build_response(400, {"error": "You can upload a maximum of 10 files"})

        timestamp = int(time.time())
        date_folder = datetime.now().strftime("%Y-%m-%d")

        presigned_urls = []

        for file_obj in files:
            # Example: file_obj = { "name": "some.pdf", "type": "application/pdf" }
            original_filename = file_obj["name"]
            file_extension = original_filename.split('.')[-1].lower()

            if file_extension not in ALLOWED_EXTENSIONS:
                return build_response(
                    400,
                    {"error": f"Invalid file type: {original_filename}. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}."}
                )

            # Disallow .zip
            if file_extension == "zip":
                return build_response(400, {"error": "ZIP files are not allowed"})

            # Create sanitized filename
            sanitized_filename = re.sub(r'[^\w\.-]', '_', original_filename)

            # Create an S3 key that organizes by date
            s3_key = f"{date_folder}/{timestamp}_{sanitized_filename}"

            # Generate a presigned URL for PUT
            # (Optionally, you can set ACL, content type, or metadata in Params.)
            presigned_url = s3.generate_presigned_url(
                ClientMethod="put_object",
                Params={
                    "Bucket": BUCKET_NAME,
                    "Key": s3_key,
                    "Metadata": {
                        "client": CLIENT_PREFIX,
                        "original-filename": original_filename
                    },
                    # "ContentType": file_obj.get("type", "application/octet-stream"),
                },
                ExpiresIn=3600  # 1 hour
            )

            presigned_urls.append({
                "fileName": original_filename,
                "s3Key": s3_key,
                "uploadUrl": presigned_url
            })

        return build_response(200, {
            "message": "Presigned URLs generated successfully",
            "presignedUrls": presigned_urls
        })

    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return build_response(500, {"error": f"Server error: {str(e)}"})
