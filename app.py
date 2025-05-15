from flask import Flask, render_template, send_from_directory, abort, redirect, url_for
import os
import mimetypes

app = Flask(__name__)

# Configure the video directory
VIDEO_DIR = '/dvr'
ALLOWED_EXTENSIONS = {'mp4'}

def get_video_files():
    """Return a list of video files from the VIDEO_DIR."""
    video_files = []
    if os.path.exists(VIDEO_DIR):
        for file in os.listdir(VIDEO_DIR):
            if file.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
                video_files.append(file)
    return sorted(video_files)

@app.route('/')
def index():
    """Display a list of available video files."""
    videos = get_video_files()
    return render_template('index.html', videos=videos)

@app.route('/video/<filename>')
def serve_video(filename):
    """Stream a specific video file."""
    # Security check to prevent directory traversal
    if not filename or '..' in filename:
        abort(404)
    
    if not os.path.exists(os.path.join(VIDEO_DIR, filename)):
        abort(404)
        
    # Ensure the file has a valid extension
    if not filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
        abort(403)
        
    return send_from_directory(VIDEO_DIR, filename)

@app.route('/download/<filename>')
def download_video(filename):
    """Download a specific video file."""
    # Security check to prevent directory traversal
    if not filename or '..' in filename:
        abort(404)
    
    if not os.path.exists(os.path.join(VIDEO_DIR, filename)):
        abort(404)
        
    # Ensure the file has a valid extension
    if not filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
        abort(403)
        
    return send_from_directory(
        VIDEO_DIR, 
        filename, 
        as_attachment=True
    )

@app.route('/delete/<filename>')
def delete_video(filename):
    """Delete a specific video file."""
    # Security check to prevent directory traversal
    if not filename or '..' in filename:
        abort(404)
    
    file_path = os.path.join(VIDEO_DIR, filename)
    if not os.path.exists(file_path):
        abort(404)
        
    # Ensure the file has a valid extension
    if not filename.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
        abort(403)
    
    try:
        os.remove(file_path)
        return redirect(url_for('index'))
    except Exception as e:
        # Handle error (e.g., permission denied)
        return f"Error deleting file: {str(e)}", 500

if __name__ == '__main__':
    # Register common MIME types
    mimetypes.add_type('video/mp4', '.mp4')
    
    print(f"Starting video server. Videos will be served from {VIDEO_DIR}")
    print("Access the server at http://localhost or http://<your-ip-address>")
    
    # Run the Flask app on 0.0.0.0 (all interfaces) and port 80
    app.run(host='0.0.0.0', port=80, debug=False)
