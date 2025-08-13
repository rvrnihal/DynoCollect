import os
import boto3
import logging
import uuid
import warnings
import urllib3
import requests
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from supabase import create_client

# Suppress SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Disable SSL verification warnings in requests
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

# Disable SSL verification globally
os.environ['PYTHONHTTPSVERIFY'] = '0'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Supabase client for database operations
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# S3 configuration
S3_ENDPOINT = "https://gxzsxowfeztwrtidfdru.storage.supabase.co/storage/v1/s3"
S3_REGION = "ap-south-1"
S3_ACCESS_KEY = os.getenv("SUPABASE_S3_KEY", "2d7d13dc7201b58ef2f9a4f028eb6ea4")
S3_SECRET_KEY = os.getenv("SUPABASE_S3_SECRET", "447f36651ef7bb1bf4bf38205f1c4e2b6dfe77da574c1ded4caeb9ba36e1c83d")

# Valid bucket names
VALID_BUCKETS = ["video", "audio", "images"]

# Public URL format
PUBLIC_URL_FORMAT = "https://gxzsxowfeztwrtidfdru.storage.supabase.co/storage/v1/object/public/{bucket}/{filename}"


def get_s3_client():
    """
    Create and return a boto3 S3 client configured for Supabase Storage.
    """
    try:
        # Create a custom session with SSL verification disabled
        session = boto3.session.Session()
        
        # Set environment variable to disable SSL verification
        # This affects the underlying requests library used by boto3
        import os
        os.environ['PYTHONHTTPSVERIFY'] = '0'
        
        # Create S3 client with SSL verification disabled
        s3_client = session.client(
            's3',
            endpoint_url=S3_ENDPOINT,
            region_name=S3_REGION,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            verify=False,  # Disable SSL verification to fix SSL validation errors
            config=boto3.session.Config(
                signature_version='s3v4',
                # Significantly increased timeouts for large files
                connect_timeout=60,               # 60 seconds to establish connection
                read_timeout=900,                 # 15 minutes to read data
                retries={
                    'max_attempts': 15,           # More retry attempts
                    'mode': 'adaptive',           # Adaptive retry mode
                    'total_max_attempts': 15      # Total max attempts including retries
                }
            )
        )
        return s3_client
    except Exception as e:
        logger.error(f"Failed to create S3 client: {str(e)}")
        raise


def upload_file_to_supabase(file_path, bucket_name, custom_filename=None, content_type=None):
    """
    Upload a file to Supabase Storage using boto3 S3 client.
    
    Args:
        file_path (str): Path to the file to upload
        bucket_name (str): Name of the bucket (video, audio, or images)
        custom_filename (str, optional): Custom filename to use. If None, uses original filename with UUID prefix
        content_type (str, optional): Content type of the file. If None, will be guessed
        
    Returns:
        dict: Dictionary containing success status, public URL, and any error message
    """
    # Validate bucket name
    if bucket_name not in VALID_BUCKETS:
        return {
            "success": False,
            "error": f"Invalid bucket name. Must be one of: {', '.join(VALID_BUCKETS)}"
        }
    
    # Check if file exists
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"File not found: {file_path}"
        }
    
    try:
        # Get file size for logging
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # Get original filename
        original_filename = os.path.basename(file_path)
        
        # Generate unique filename if not provided
        if custom_filename:
            filename = custom_filename
        else:
            filename = f"{uuid.uuid4()}_{original_filename}"
        
        logger.info(f"Uploading file: {original_filename} ({file_size_mb:.2f} MB) to {bucket_name}")
        
        # Get S3 client
        s3_client = get_s3_client()
        
        # Prepare upload parameters
        upload_args = {
            'Bucket': bucket_name,
            'Key': filename,
            'ACL': 'public-read',  # Make file publicly accessible
        }
        
        # Add content type if provided
        if content_type:
            upload_args['ContentType'] = content_type
        
        # Use TransferConfig for multipart uploads and performance tuning
        # Optimized settings for large files with smaller chunk sizes for Supabase Storage limits
        # Adjust chunk size based on file size to avoid EntityTooLarge errors
        if file_size_mb > 50:  # For files larger than 50MB
            chunk_size = 256 * 1024  # 256KB chunks for very large files
        else:
            chunk_size = 512 * 1024  # 512KB chunks for smaller files
            
        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=5 * 1024 * 1024,  # 5MB - start multipart upload sooner
            max_concurrency=30,                 # 30 threads for better parallelism
            multipart_chunksize=chunk_size,     # Dynamic chunk size based on file size
            use_threads=True,
            max_io_queue=200,                   # Increased queue size for better throughput
            io_chunksize=262144,                # 256KB chunks for reading
            num_download_attempts=15            # More retry attempts
        )
        
        # Upload file with progress tracking
        start_time = __import__('time').time()
        
        with open(file_path, 'rb') as file_data:
            s3_client.upload_fileobj(
                file_data,
                upload_args['Bucket'],
                upload_args['Key'],
                ExtraArgs={
                    'ACL': upload_args['ACL'],
                    **(({'ContentType': upload_args['ContentType']} if 'ContentType' in upload_args else {}))
                },
                Config=config
            )
        
        end_time = __import__('time').time()
        upload_time = end_time - start_time
        upload_speed = file_size / upload_time / 1024 / 1024  # MB/s
        
        logger.info(f"Upload completed in {upload_time:.2f} seconds ({upload_speed:.2f} MB/s)")
        
        # Generate public URL
        public_url = PUBLIC_URL_FORMAT.format(bucket=bucket_name, filename=filename)
        
        return {
            "success": True,
            "url": public_url,
            "filename": filename,
            "size_bytes": file_size,
            "upload_time_seconds": upload_time,
            "upload_speed_mbps": upload_speed
        }
        
    except ClientError as e:
        error_message = str(e)
        logger.error(f"S3 client error: {error_message}")
        return {
            "success": False,
            "error": error_message
        }
    except ConnectionError as e:
        error_message = str(e)
        logger.error(f"Connection error during upload: {error_message}")
        # Provide a more user-friendly error message
        return {
            "success": False,
            "error": "Connection error during upload. Please try again or use a smaller file.",
            "detailed_error": error_message
        }
    except TimeoutError as e:
        error_message = str(e)
        logger.error(f"Timeout error during upload: {error_message}")
        return {
            "success": False,
            "error": "Upload timed out. Please try again or use a smaller file.",
            "detailed_error": error_message
        }
    except Exception as e:
        error_message = str(e)
        logger.error(f"Unexpected error: {error_message}")
        return {
            "success": False,
            "error": f"Upload failed: {error_message}"
        }


def upload_file_from_memory(file_data, filename, bucket_name, content_type=None):
    """
    Upload a file from memory (bytes or file-like object) to Supabase Storage.
    
    Args:
        file_data (bytes or file-like): File data to upload
        filename (str): Filename to use in the bucket
        bucket_name (str): Name of the bucket (video, audio, or images)
        content_type (str, optional): Content type of the file
        
    Returns:
        dict: Dictionary containing success status, public URL, and any error message
    """
    # Validate bucket name
    if bucket_name not in VALID_BUCKETS:
        return {
            "success": False,
            "error": f"Invalid bucket name. Must be one of: {', '.join(VALID_BUCKETS)}"
        }
    
    try:
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}_{filename}"
        
        # Get file size for logging
        if hasattr(file_data, 'getbuffer'):
            file_size = len(file_data.getbuffer())
        elif hasattr(file_data, 'seek') and hasattr(file_data, 'tell'):
            current_pos = file_data.tell()
            file_data.seek(0, os.SEEK_END)
            file_size = file_data.tell()
            file_data.seek(current_pos)  # Reset position
        else:
            file_size = len(file_data)
            
        file_size_mb = file_size / (1024 * 1024)
        
        logger.info(f"Uploading file from memory: {filename} ({file_size_mb:.2f} MB) to {bucket_name}")
        
        # Get S3 client
        s3_client = get_s3_client()
        
        # Use TransferConfig for multipart uploads and performance tuning
        # Optimized settings for large files with smaller chunk sizes for Supabase Storage limits
        # Adjust chunk size based on file size to avoid EntityTooLarge errors
        if file_size_mb > 50:  # For files larger than 50MB
            chunk_size = 256 * 1024  # 256KB chunks for very large files
        else:
            chunk_size = 512 * 1024  # 512KB chunks for smaller files
            
        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=5 * 1024 * 1024,  # 5MB - start multipart upload sooner
            max_concurrency=30,                 # 30 threads for better parallelism
            multipart_chunksize=chunk_size,     # Dynamic chunk size based on file size
            use_threads=True,
            max_io_queue=200,                   # Increased queue size for better throughput
            io_chunksize=262144,                # 256KB chunks for reading
            num_download_attempts=15            # More retry attempts
        )
        
        # Prepare extra args
        extra_args = {
            'ACL': 'public-read'
        }
        
        if content_type:
            extra_args['ContentType'] = content_type
        
        # Upload file with progress tracking
        start_time = __import__('time').time()
        
        s3_client.upload_fileobj(
            file_data if hasattr(file_data, 'read') else __import__('io').BytesIO(file_data),
            bucket_name,
            unique_filename,
            ExtraArgs=extra_args,
            Config=config
        )
        
        end_time = __import__('time').time()
        upload_time = end_time - start_time
        upload_speed = file_size / upload_time / 1024 / 1024  # MB/s
        
        logger.info(f"Upload completed in {upload_time:.2f} seconds ({upload_speed:.2f} MB/s)")
        
        # Generate public URL
        public_url = PUBLIC_URL_FORMAT.format(bucket=bucket_name, filename=unique_filename)
        
        return {
            "success": True,
            "url": public_url,
            "filename": unique_filename,
            "size_bytes": file_size,
            "upload_time_seconds": upload_time,
            "upload_speed_mbps": upload_speed
        }
        
    except ClientError as e:
        error_message = str(e)
        logger.error(f"S3 client error: {error_message}")
        return {
            "success": False,
            "error": error_message
        }
    except ConnectionError as e:
        error_message = str(e)
        logger.error(f"Connection error during upload: {error_message}")
        # Provide a more user-friendly error message
        return {
            "success": False,
            "error": "Connection error during upload. Please try again or use a smaller file.",
            "detailed_error": error_message
        }
    except TimeoutError as e:
        error_message = str(e)
        logger.error(f"Timeout error during upload: {error_message}")
        return {
            "success": False,
            "error": "Upload timed out. Please try again or use a smaller file.",
            "detailed_error": error_message
        }
    except Exception as e:
        error_message = str(e)
        logger.error(f"Unexpected error: {error_message}")
        return {
            "success": False,
            "error": f"Upload failed: {error_message}"
        }


def save_file_url_to_database(url, field_name):
    """
    Save a file URL to the contributions table in the database.
    
    Args:
        url (str): The public URL of the uploaded file
        field_name (str): The field name in the contributions table (audio_url, video_url, or image_url)
        
    Returns:
        dict: Dictionary containing success status and database response
    """
    try:
        # Validate field name
        valid_fields = ['audio_url', 'video_url', 'image_url']
        if field_name not in valid_fields:
            return {
                "success": False,
                "error": f"Invalid field name. Must be one of: {', '.join(valid_fields)}"
            }
        
        # Insert into database
        result = supabase.table('contributions').insert({
            field_name: url
        }).execute()
        
        # Check for error in APIResponse object
        if hasattr(result, 'error') and result.error:
            return {
                "success": False,
                "error": result.error.message
            }
        
        return {
            "success": True,
            "data": result.data
        }
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"Database error: {error_message}")
        return {
            "success": False,
            "error": error_message
        }