import os
import uuid
import logging
import tempfile
import mimetypes
import base64
import requests
import time
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash

# Import S3 uploader module
from s3_uploader import upload_file_from_memory, save_file_url_to_database

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.info("Starting application...")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure session
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_FILE_DIR'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_session')

# Initialize Flask-Session
Session(app)

# Add request logging middleware
@app.before_request
def log_request_info():
    print(f"Request received: {request.method} {request.path}")
    logger.info(f"Request received: {request.method} {request.path}")

@app.after_request
def log_response_info(response):
    print(f"Response sent: {response.status}")
    logger.info(f"Response sent: {response.status}")
    return response

# Add health check endpoint
@app.route('/healthz', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200

# Configure Flask for large file uploads
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload size
app.config['REQUEST_TIMEOUT'] = 900  # 15 minutes timeout

# Supabase setup
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create Supabase client with default settings
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Buckets are already created in Supabase UI
# No need to create them programmatically


@app.route('/submit-text', methods=['POST'])
def submit_text():
    try:
        data = request.json
        text_data = data.get('text_data')

        if not text_data:
            return jsonify({'error': 'No text data provided'}), 400

        result = supabase.table('contributions').insert({
            'text_data': text_data
        }).execute()

        # Check for error in APIResponse object
        if hasattr(result, 'error') and result.error:
            return jsonify({'error': result.error.message}), 500

        return jsonify({'success': True, 'data': result.data}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def handle_file_upload(bucket_name, field_name):
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        # Guess content type more reliably
        content_type = file.content_type
        if not content_type or content_type == 'text/plain':
            guessed_type, _ = mimetypes.guess_type(file.filename)
            content_type = guessed_type or 'application/octet-stream'
        
        # Log file information for debugging
        app.logger.debug(f"Processing file upload: {file.filename}, Original Content-Type: {file.content_type}, Using Content-Type: {content_type}")
        
        # Use the S3 uploader for fast, efficient uploads
        # This handles large files with multipart uploads and optimized transfer settings
        upload_result = upload_file_from_memory(
            file_data=file,
            filename=file.filename,
            bucket_name=bucket_name,
            content_type=content_type
        )
        
        if not upload_result["success"]:
            app.logger.error(f"S3 upload failed: {upload_result['error']}")
            return jsonify({'error': f'Upload failed: {upload_result["error"]}'}), 500
        
        # Log upload performance metrics
        app.logger.info(f"Upload completed in {upload_result['upload_time_seconds']:.2f} seconds at {upload_result['upload_speed_mbps']:.2f} MB/s")
        
        # Get the public URL from the upload result
        file_url = upload_result["url"]
        app.logger.debug(f"File URL: {file_url}")
        
        # Save URL to database
        db_result = save_file_url_to_database(file_url, field_name)
        
        if not db_result["success"]:
            app.logger.error(f"Database insert failed: {db_result['error']}")
            return jsonify({'error': f'Database error: {db_result["error"]}'}), 500
        
        # Return success response with URL and upload metrics
        return jsonify({
            'success': True, 
            'url': file_url, 
            'data': db_result["data"],
            'upload_time_seconds': upload_result['upload_time_seconds'],
            'upload_speed_mbps': upload_result['upload_speed_mbps']
        }), 201

    except Exception as e:
        app.logger.error(f"Error in handle_file_upload: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    return handle_file_upload('audio', 'audio_url')


@app.route('/upload-video', methods=['POST'])
def upload_video():
    return handle_file_upload('video', 'video_url')


@app.route('/upload-image', methods=['POST'])
def upload_image():
    return handle_file_upload('images', 'image_url')


@app.route('/auth/register', methods=['POST'])
def register():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Log registration attempt
        app.logger.info(f"Registration attempt for email: {email}")
        
        # Register user with Supabase Auth with retry logic
        max_retries = 3
        retry_count = 0
        retry_delay = 2  # seconds
        
        while retry_count < max_retries:
            try:
                # Attempt to register the user
                user = supabase.auth.sign_up({
                    "email": email,
                    "password": password,
                })
                
                app.logger.info(f"Registration successful for email: {email}")
                return jsonify({
                    'success': True,
                    'user': user.dict(),
                    'message': 'Registration successful. Please check your email for verification.'
                }), 201
                
            except Exception as e:
                error_str = str(e)
                
                # Check if user already exists
                if 'User already registered' in error_str:
                    app.logger.info(f"User already exists: {email}")
                    return jsonify({'error': 'User with this email already exists'}), 409
                
                # Check for timeout errors
                if 'timeout' in error_str.lower() or 'timed out' in error_str.lower() or 'after 29 seconds' in error_str.lower():
                    retry_count += 1
                    if retry_count < max_retries:
                        app.logger.warning(f"Timeout during registration. Retrying ({retry_count}/{max_retries})...")
                        time.sleep(retry_delay)
                        # Increase delay for next retry
                        retry_delay *= 2
                        continue
                    else:
                        app.logger.error(f"Registration failed after {max_retries} retries: {error_str}")
                        return jsonify({'error': 'Registration service temporarily unavailable. Please try again later.'}), 503
                else:
                    # For other errors, don't retry
                    raise e
                
    except Exception as e:
        app.logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'An error occurred during registration. Please try again later.'}), 500


@app.route('/auth/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
            
        # Sign in with Supabase Auth
        try:
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            # Store session data
            session['user'] = {
                'id': response.user.id,
                'email': response.user.email,
                'access_token': response.session.access_token,
                'refresh_token': response.session.refresh_token
            }
            
            return jsonify({
                'success': True,
                'user': response.user.dict(),
                'session': response.session.dict(),
                'message': 'Login successful'
            }), 200
            
        except Exception as e:
            if 'Invalid login credentials' in str(e):
                return jsonify({'error': 'Invalid email or password'}), 401
            else:
                raise e
                
    except Exception as e:
        app.logger.error(f"Login error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/auth/logout', methods=['POST'])
def logout():
    try:
        # Get session from request
        auth_token = request.headers.get('Authorization')
        if auth_token and auth_token.startswith('Bearer '):
            token = auth_token.split(' ')[1]
            # Sign out from Supabase
            supabase.auth.sign_out(token)
        
        # Clear session
        session.pop('user', None)
        
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200
        
    except Exception as e:
        app.logger.error(f"Logout error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/auth/user', methods=['GET'])
def get_user():
    try:
        # Get session from request
        auth_token = request.headers.get('Authorization')
        if not auth_token or not auth_token.startswith('Bearer '):
            return jsonify({'error': 'Unauthorized'}), 401
            
        token = auth_token.split(' ')[1]
        
        # Get user from Supabase
        try:
            user = supabase.auth.get_user(token)
            return jsonify({
                'success': True,
                'user': user.dict()
            }), 200
        except Exception as e:
            return jsonify({'error': 'Invalid or expired token'}), 401
            
    except Exception as e:
        app.logger.error(f"Get user error: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)
