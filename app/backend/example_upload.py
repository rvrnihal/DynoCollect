import os
import sys
import time
import urllib3
from dotenv import load_dotenv
from s3_uploader import upload_file_to_supabase, save_file_url_to_database

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

def main():
    # Check if file path is provided
    if len(sys.argv) < 2:
        print("Usage: python example_upload.py <file_path> [bucket_name]")
        print("Example: python example_upload.py ./my_video.mp4 video")
        return
    
    # Get file path from command line argument
    file_path = sys.argv[1]
    
    # Get bucket name from command line argument or default to 'video'
    bucket_name = sys.argv[2] if len(sys.argv) > 2 else 'video'
    
    # Validate bucket name
    valid_buckets = ['video', 'audio', 'images']
    if bucket_name not in valid_buckets:
        print(f"Error: Invalid bucket name. Must be one of: {', '.join(valid_buckets)}")
        return
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return
    
    # Get file size
    file_size = os.path.getsize(file_path)
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"Uploading file: {os.path.basename(file_path)} ({file_size_mb:.2f} MB) to {bucket_name}")
    
    # Start timer
    start_time = time.time()
    
    # Upload file
    result = upload_file_to_supabase(file_path, bucket_name)
    
    # End timer
    end_time = time.time()
    upload_time = end_time - start_time
    
    # Check if upload was successful
    if result['success']:
        print(f"Upload successful!")
        print(f"Public URL: {result['url']}")
        print(f"Upload time: {upload_time:.2f} seconds")
        print(f"Upload speed: {file_size / upload_time / 1024 / 1024:.2f} MB/s")
        
        # Determine field name based on bucket name
        field_name_map = {
            'video': 'video_url',
            'audio': 'audio_url',
            'images': 'image_url'
        }
        field_name = field_name_map[bucket_name]
        
        # Save URL to database
        print(f"Saving URL to database in field: {field_name}")
        db_result = save_file_url_to_database(result['url'], field_name)
        
        if db_result['success']:
            print(f"Database insert successful!")
            print(f"Record ID: {db_result['data'][0]['id']}")
        else:
            print(f"Database insert failed: {db_result['error']}")
    else:
        print(f"Upload failed: {result['error']}")

if __name__ == "__main__":
    main()