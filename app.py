import eventlet
eventlet.monkey_patch()

import os
import uuid
import json
import shutil
import threading
import traceback
import sys
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# Import the backend conversion logic
from epub_converter import convert_project

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'projects'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit to handle large PDFs

# Initialize SocketIO without passing async_mode yet, 
# run.py will handle the eventlet monkey patching and server start
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Helper function to get project path
def get_project_path(project_id):
    return os.path.join(app.config['UPLOAD_FOLDER'], project_id)

# Helper function to get project data
def get_project_data(project_id):
    project_path = get_project_path(project_id)
    json_path = os.path.join(project_path, 'project.json')
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            return json.load(f)
    return None

# Helper function to save project data
def save_project_data(project_id, data):
    project_path = get_project_path(project_id)
    json_path = os.path.join(project_path, 'project.json')
    with open(json_path, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/')
def index():
    # List existing projects
    projects = []
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for d in os.listdir(app.config['UPLOAD_FOLDER']):
            if os.path.isdir(os.path.join(app.config['UPLOAD_FOLDER'], d)):
                data = get_project_data(d)
                if data:
                    projects.append({'id': d, 'name': data.get('project_name', data.get('original_filename', d))})
    return render_template('index.html', projects=projects)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and file.filename.lower().endswith('.pdf'):
        filename = secure_filename(file.filename)
        project_id = str(uuid.uuid4())
        project_dir = get_project_path(project_id)
        os.makedirs(project_dir, exist_ok=True)
        
        file_path = os.path.join(project_dir, filename)
        file.save(file_path)
        
        # Determine initial project name
        project_name = request.form.get('project_name', '').strip()
        if not project_name:
            project_name = os.path.splitext(filename)[0]

        # Initialize project settings
        project_data = {
            'id': project_id,
            'project_name': project_name,
            'original_filename': filename,
            'pdf_path': filename,
            'settings': {
                'page_size': 'kindle', # Default
                'global_skip_areas': [], # Store skip areas applied to all pages
                'page_configs': {} # e.g., {'1': {'type': 'front_cover'}, '5': {'images': [{'x':0,'y':0,'w':100,'h':100}]}}
            },
            'status': 'new' # new, processing, done
        }
        save_project_data(project_id, project_data)
        
        return redirect(url_for('project_view', project_id=project_id))
    return 'Invalid file type. Only PDF is allowed.'

@app.route('/project/<project_id>')
def project_view(project_id):
    project_data = get_project_data(project_id)
    if not project_data:
        return 'Project not found', 404
        
    api_key_set = bool(os.environ.get("TYPHOON_API_KEY"))
    return render_template('project.html', project=project_data, api_key_set=api_key_set)

@app.route('/project/<project_id>/pdf')
def serve_pdf(project_id):
    project_data = get_project_data(project_id)
    if not project_data:
        return 'Project not found', 404
    return send_from_directory(get_project_path(project_id), project_data['pdf_path'])
    
@app.route('/project/<project_id>/download_epub')
def download_epub(project_id):
    project_data = get_project_data(project_id)
    if not project_data or project_data.get('status') != 'done':
        return 'ePub not ready or project not found', 404
    
    epub_filename = f"{project_data.get('project_name', 'output')}.epub"
    return send_from_directory(get_project_path(project_id), epub_filename, as_attachment=True)

@app.route('/project/<project_id>/save_settings', methods=['POST'])
def save_settings(project_id):
    project_data = get_project_data(project_id)
    if not project_data:
        return jsonify({'error': 'Project not found'}), 404
    
    payload = request.json
    project_data['settings'] = payload.get('settings', project_data['settings'])
    
    # Update project name if provided
    new_name = payload.get('project_name')
    if new_name:
        project_data['project_name'] = new_name.strip()

    save_project_data(project_id, project_data)
    return jsonify({'success': True, 'project_name': project_data['project_name']})

@app.route('/project/<project_id>/save_as', methods=['POST'])
def save_as_new_project(project_id):
    original_project_data = get_project_data(project_id)
    if not original_project_data:
        return jsonify({'error': 'Original project not found'}), 404
        
    payload = request.json
    new_project_name = payload.get('new_project_name', '').strip()
    if not new_project_name:
        return jsonify({'error': 'New project name is required'}), 400

    # Create new project ID and directory
    new_project_id = str(uuid.uuid4())
    new_project_dir = get_project_path(new_project_id)
    original_project_dir = get_project_path(project_id)
    
    try:
        # Copy the entire project directory (including PDF and potentially other assets later)
        shutil.copytree(original_project_dir, new_project_dir)
        
        # Load the copied project data to modify it
        new_project_data = get_project_data(new_project_id)
        
        # Update IDs and Names
        new_project_data['id'] = new_project_id
        new_project_data['project_name'] = new_project_name
        
        # Also ensure we save the latest incoming settings from the frontend before duplicating
        latest_settings = payload.get('settings')
        if latest_settings:
             new_project_data['settings'] = latest_settings
             
        save_project_data(new_project_id, new_project_data)
        
        return jsonify({'success': True, 'new_project_id': new_project_id})
        
    except Exception as e:
        # Cleanup if copy fails
        if os.path.exists(new_project_dir):
            shutil.rmtree(new_project_dir)
        return jsonify({'error': str(e)}), 500

@app.route('/project/<project_id>/reset_status', methods=['POST'])
def reset_status(project_id):
    """Allows forcing the project status back to 'new' if it gets stuck."""
    project_data = get_project_data(project_id)
    if not project_data:
        return jsonify({'error': 'Project not found'}), 404
        
    project_data['status'] = 'new'
    save_project_data(project_id, project_data)
    return jsonify({'success': True})

@app.route('/project/<project_id>/start_ocr', methods=['POST'])
def start_ocr(project_id):
    project_data = get_project_data(project_id)
    if not project_data:
        return jsonify({'error': 'Project not found'}), 404
        
    if project_data.get('status') == 'processing':
         return jsonify({'error': 'Project is already processing. If it is stuck, please force reset it.'}), 400
        
    api_key = os.environ.get("TYPHOON_API_KEY")
    if not api_key:
         return jsonify({'error': 'TYPHOON_API_KEY environment variable is not set.'}), 400

    # Ensure latest settings are saved before starting
    payload = request.json
    if payload and 'settings' in payload:
         project_data['settings'] = payload['settings']
         
    project_data['status'] = 'processing'
    save_project_data(project_id, project_data)

    # Start OCR in a background thread
    print(f"[{project_id}] Starting OCR background thread...")
    thread = threading.Thread(target=run_ocr_background, args=(project_id, project_data, get_project_path(project_id), api_key))
    thread.daemon = True
    thread.start()

    return jsonify({'success': True})

def run_ocr_background(project_id, project_data, project_dir, api_key):
    try:
        def progress_callback(percent):
            # Print to command line
            print(f"[{project_id}] OCR Progress: {percent}%")
            # Send to web UI
            socketio.emit('ocr_progress', {'project_id': project_id, 'percent': percent})
            
        print(f"[{project_id}] Calling convert_project...")
        convert_project(project_data, project_dir, api_key, progress_callback=progress_callback)
        
        print(f"[{project_id}] OCR Complete.")
        # Update status to done
        project_data = get_project_data(project_id) # reload to be safe
        project_data['status'] = 'done'
        save_project_data(project_id, project_data)
        
        socketio.emit('ocr_complete', {'project_id': project_id})
        
    except Exception as e:
        print(f"[{project_id}] Background OCR Error: {e}", file=sys.stderr)
        traceback.print_exc()
        
        project_data = get_project_data(project_id)
        project_data['status'] = 'error'
        save_project_data(project_id, project_data)
        socketio.emit('ocr_error', {'project_id': project_id, 'error': str(e)})

if __name__ == '__main__':
    print("Warning: Please use 'python run.py' to start the server to ensure background tasks work correctly.")
    app.debug = True
    socketio.run(app, port=5000)
