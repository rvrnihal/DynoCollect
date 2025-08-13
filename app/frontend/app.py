import streamlit as st
import requests
import json
import time

# ---------- Config ----------
API_URL = "https://dynocollect.onrender.com"

st.set_page_config(
    page_title="Swecha Media Upload",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- Helpers ----------
def safe_rerun():
    """Safe rerun for both old/new Streamlit versions."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# ---------- Session State ----------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user" not in st.session_state:
    st.session_state.user = None
if "show_login" not in st.session_state:
    st.session_state.show_login = True

# ---------- API Calls ----------
def login(email, password):
    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            st.session_state.authenticated = True
            st.session_state.user = response.json()
            return True, "Login successful!"
        return False, response.json().get("error", "Login failed. Please check your credentials.")
    except Exception as e:
        return False, f"Error: {str(e)}"

def register(email, password, confirm_password):
    if password != confirm_password:
        return False, "Passwords do not match."
    try:
        response = requests.post(
            f"{API_URL}/auth/register",
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 201:
            st.session_state.show_login = True
            return True, "Registration successful! Please login."
        return False, response.json().get("error", "Registration failed.")
    except Exception as e:
        return False, f"Error: {str(e)}"

def logout():
    st.session_state.authenticated = False
    st.session_state.user = None
    return True, "Logout successful!"

# ---------- UI ----------
st.title("Swecha Media Upload")

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.session_state.show_login:
            st.header("Login")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("Login", key="login_button"):
                success, message = login(email, password)
                if success:
                    st.success(message)
                    safe_rerun()
                else:
                    st.error(message)
                    
            if st.button("Need to register?", key="goto_register"):
                st.session_state.show_login = False
                safe_rerun()

        else:
            st.header("Register")
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
            
            if st.button("Register", key="register_button"):
                success, message = register(email, password, confirm_password)
                if success:
                    st.success(message)
                    safe_rerun()
                else:
                    st.error(message)
                    
            if st.button("Already have an account?", key="goto_login"):
                st.session_state.show_login = True
                safe_rerun()

else:
    # Sidebar user info
    with st.sidebar:
        st.write(f"Logged in as: {st.session_state.user.get('email')}")
        if st.button("Logout"):
            success, message = logout()
            if success:
                st.success(message)
                safe_rerun()
            else:
                st.error(message)
    
    # Submission type
    submission_type = st.radio("Select submission type", ["Text", "Audio", "Video", "Image"])

    # Text
    if submission_type == "Text":
        st.header("Submit Text")
        text_data = st.text_area("Enter your text here", height=200)
        if st.button("Submit Text"):
            if text_data:
                try:
                    response = requests.post(
                        f"{API_URL}/submit-text",
                        json={"text_data": text_data},
                        headers={"Content-Type": "application/json"}
                    )
                    if response.status_code == 201:
                        st.success("Text submitted successfully!")
                        st.json(response.json())
                    else:
                        st.error(f"Error: {response.json().get('error', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            else:
                st.warning("Please enter some text before submitting.")

    # Audio
    elif submission_type == "Audio":
        st.header("Upload Audio")
        st.info("✨ Supports files up to 500MB")
        audio_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "ogg"])

        if audio_file:
            size_mb = len(audio_file.getvalue()) / (1024 * 1024)
            st.info(f"File size: {size_mb:.2f} MB")
        
        if st.button("Submit Audio"):
            if audio_file:
                size_mb = len(audio_file.getvalue()) / (1024 * 1024)
                if size_mb > 500:
                    st.error(f"File size ({size_mb:.2f} MB) exceeds 500 MB limit.")
                else:
                    try:
                        with st.spinner("Uploading..."):
                            files = {"file": (audio_file.name, audio_file.getvalue(), audio_file.type)}
                            response = requests.post(f"{API_URL}/upload-audio", files=files, timeout=600)
                        if response.status_code == 201:
                            st.success("✅ Audio uploaded successfully!")
                            st.json(response.json())
                        else:
                            st.error(response.json().get('error', 'Unknown error'))
                    except requests.exceptions.Timeout:
                        st.error("Upload timed out.")
                    except Exception as e:
                        st.error(f"Upload error: {str(e)}")
            else:
                st.warning("Please select an audio file.")

    # Video
    elif submission_type == "Video":
        st.header("Upload Video")
        st.info("✨ Supports files up to 500MB")
        video_file = st.file_uploader("Choose a video file", type=["mp4", "mov", "avi"])
        
        if video_file:
            size_mb = len(video_file.getvalue()) / (1024 * 1024)
            st.info(f"File size: {size_mb:.2f} MB")

        if st.button("Submit Video"):
            if video_file:
                size_mb = len(video_file.getvalue()) / (1024 * 1024)
                if size_mb > 500:
                    st.error(f"File size ({size_mb:.2f} MB) exceeds 500 MB limit.")
                else:
                    try:
                        with st.spinner("Uploading..."):
                            files = {"file": (video_file.name, video_file.getvalue(), video_file.type)}
                            response = requests.post(f"{API_URL}/upload-video", files=files, timeout=600)
                        if response.status_code == 201:
                            st.success("✅ Video uploaded successfully!")
                            st.json(response.json())
                        else:
                            st.error(response.json().get('error', 'Unknown error'))
                    except requests.exceptions.Timeout:
                        st.error("Upload timed out.")
                    except Exception as e:
                        st.error(f"Upload error: {str(e)}")
            else:
                st.warning("Please select a video file.")

    # Image
    elif submission_type == "Image":
        st.header("Upload Image")
        st.info("✨ Supports files up to 500MB")
        image_file = st.file_uploader("Choose an image file", type=["jpg", "jpeg", "png", "gif"])
        
        if image_file:
            size_mb = len(image_file.getvalue()) / (1024 * 1024)
            st.info(f"File size: {size_mb:.2f} MB")

        if st.button("Submit Image"):
            if image_file:
                size_mb = len(image_file.getvalue()) / (1024 * 1024)
                if size_mb > 500:
                    st.error(f"File size ({size_mb:.2f} MB) exceeds 500 MB limit.")
                else:
                    try:
                        with st.spinner("Uploading..."):
                            files = {"file": (image_file.name, image_file.getvalue(), image_file.type)}
                            response = requests.post(f"{API_URL}/upload-image", files=files, timeout=600)
                        if response.status_code == 201:
                            st.success("✅ Image uploaded successfully!")
                            st.json(response.json())
                        else:
                            st.error(response.json().get('error', 'Unknown error'))
                    except requests.exceptions.Timeout:
                        st.error("Upload timed out.")
                    except Exception as e:
                        st.error(f"Upload error: {str(e)}")
            else:
                st.warning("Please select an image file.")
