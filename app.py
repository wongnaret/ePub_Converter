import os
import uuid
import json
import shutil
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'projects'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB limit

socketio = SocketIO(app, async_mode='eventlet')

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
    return render_template('project.html', project=project_data)

@app.route('/project/<project_id>/pdf')
def serve_pdf(project_id):
    project_data = get_project_data(project_id)
    if not project_data:
        return 'Project not found', 404
    return send_from_directory(get_project_path(project_id), project_data['pdf_path'])

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


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
