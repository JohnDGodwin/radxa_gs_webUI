from flask import Flask, render_template, send_file, request, redirect, url_for, flash, jsonify
import os
from pathlib import Path
import configparser
from typing import Dict, List
import shutil
import subprocess
import yaml
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)

MEDIA_FOLDER = '/media'
GS_KEY_PATH = '/etc/gs.key'
CONFIG_WHITELIST = [
    '/etc/wifibroadcast.cfg',
    '/config/scripts/screen-mode',
    '/config/scripts/osd',
    '/config/scripts/rec-fps'
]
COMMANDS_SCRIPT = os.path.join(os.path.dirname(__file__), 'commands.sh')

def read_ini_file(filepath: str) -> Dict:
    config = configparser.ConfigParser()
    try:
        config.read(filepath)
        return {section: dict(config[section]) for section in config.sections()}
    except Exception as e:
        return {}

def write_ini_file(filepath: str, data: Dict) -> bool:
    config = configparser.ConfigParser()
    try:
        # Load existing file first to preserve structure
        config.read(filepath)
        
        # Update with new values
        for section, values in data.items():
            if not config.has_section(section):
                config.add_section(section)
            for key, value in values.items():
                config.set(section, key, value)
        
        # Write to file
        with open(filepath, 'w') as f:
            config.write(f)
        return True
    except Exception as e:
        print(f"Error writing config: {str(e)}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/files')
def files():
    video_files = []
    if os.path.exists(MEDIA_FOLDER):
        for file in os.listdir(MEDIA_FOLDER):
            if file.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')):
                file_path = os.path.join(MEDIA_FOLDER, file)
                size = os.path.getsize(file_path)
                size_mb = round(size / (1024 * 1024), 2)
                video_files.append({
                    'name': file,
                    'size': size_mb
                })
    return render_template('files.html', files=video_files)

@app.route('/config')
def config():
    # List available config files
    available_configs = []
    for filepath in CONFIG_WHITELIST:
        if os.path.exists(filepath):
            available_configs.append({
                'path': filepath,
                'name': os.path.basename(filepath)
            })
            
    # Check if gs.key exists
    gs_key_exists = os.path.exists(GS_KEY_PATH)
    if gs_key_exists:
        gs_key_size = os.path.getsize(GS_KEY_PATH)
    else:
        gs_key_size = 0
        
    return render_template('config.html', 
                         configs=available_configs,
                         gs_key_exists=gs_key_exists,
                         gs_key_size=gs_key_size)

@app.route('/config/edit/<path:filepath>', methods=['GET', 'POST'])
def edit_config(filepath):
    # Normalize the filepath to handle URL encoding
    filepath = os.path.normpath('/' + filepath)
    
    # Validate filepath is in whitelist
    if filepath not in CONFIG_WHITELIST:
        print(f"Access denied. Filepath '{filepath}' not in whitelist: {CONFIG_WHITELIST}")
        return "Access denied", 403
    
    if request.method == 'POST':
        # Process form data
        new_config = {}
        for key in request.form:
            # Parse section and option from form field name
            if '__' in key:
                section, option = key.split('__')
                if section not in new_config:
                    new_config[section] = {}
                new_config[section][option] = request.form[key]
        
        # Write updated config
        if write_ini_file(filepath, new_config):
            flash('Configuration saved successfully!', 'success')
        else:
            flash('Error saving configuration', 'error')
        
        return redirect(url_for('edit_config', filepath=filepath))
    
    # Read current config
    config_data = read_ini_file(filepath)
    return render_template('edit_config.html', 
                         filepath=filepath,
                         filename=os.path.basename(filepath),
                         config=config_data)

@app.route('/config/gskey', methods=['POST'])
def upload_gskey():
    if 'gskey' not in request.files:
        flash('No file provided', 'error')
        return redirect(url_for('config'))
    
    file = request.files['gskey']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('config'))
    
    try:
        # Create a backup of the existing key if it exists
        if os.path.exists(GS_KEY_PATH):
            backup_path = GS_KEY_PATH + '.backup'
            shutil.copy2(GS_KEY_PATH, backup_path)
        
        # Save the new key file
        file.save(GS_KEY_PATH)
        # Set appropriate permissions
        os.chmod(GS_KEY_PATH, 0o644)
        
        flash('gs.key file updated successfully', 'success')
    except Exception as e:
        flash(f'Error updating gs.key: {str(e)}', 'error')
    
    return redirect(url_for('config'))

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(os.path.join(MEDIA_FOLDER, filename), as_attachment=True)
    except Exception as e:
        return f"Error downloading file: {str(e)}", 400

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    try:
        file_path = os.path.join(MEDIA_FOLDER, filename)
        os.remove(file_path)
        return redirect(url_for('files'))
    except Exception as e:
        return f"Error deleting file: {str(e)}", 400

@app.route('/camera')
def camera_settings():
    return render_template('camera_settings.html')

@app.route('/camera/load-config')
def load_camera_config():
    try:
        # Run the read config commands
        wfb_output = subprocess.check_output(['bash', '-c', f'source {COMMANDS_SCRIPT} && read_wfb_config'], 
                                          stderr=subprocess.STDOUT,
                                          text=True)
        
        majestic_output = subprocess.check_output(['bash', '-c', f'source {COMMANDS_SCRIPT} && read_majestic_config'],
                                                stderr=subprocess.STDOUT,
                                                text=True)
        
        # Parse WFB config
        wfb_config = {}
        for line in wfb_output.splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                wfb_config[key.strip()] = value.strip()
        
        # Parse Majestic YAML config
        try:
            yaml_content = majestic_output.replace("Reading majestic configuration", "").strip()
            majestic_config = yaml.safe_load(yaml_content)
            
            # Extract only video0 section
            video_config = majestic_config.get('video0', {})
            print("Found video0 config:", video_config)
            
        except yaml.YAMLError as e:
            print(f"YAML parsing error: {e}")
            video_config = {}
        except Exception as e:
            print(f"Error processing Majestic config: {e}")
            video_config = {}
        
        # Combine configurations
        config = {
            'fps': str(video_config.get('fps', '60')),
            'size': str(video_config.get('size', '1920x1080')),
            'bitrate': str(video_config.get('bitrate', '4096')),
            'channel': wfb_config.get('channel', '161'),
            'txpower_override': wfb_config.get('driver_txpower_override', '1'),
            'stbc': wfb_config.get('stbc', '0'),
            'ldpc': wfb_config.get('ldpc', '0'),
            'mcs_index': wfb_config.get('mcs_index', '1'),
            'fec_k': wfb_config.get('fec_k', '8'),
            'fec_n': wfb_config.get('fec_n', '12')
        }
        
        print("Final config:", config)
        return jsonify(config)
    except Exception as e:
        print(f"Error in load_camera_config: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/camera/update', methods=['POST'])
def update_camera_settings():
    try:
        changes = request.json
        
        # Map frontend field names to bash function names
        function_map = {
            'fps': 'update_fps',
            'size': 'update_size',
            'bitrate': 'update_bitrate',
            'channel': 'update_channel',
            'txpower_override': 'update_txpower_override',
            'stbc': 'update_stbc',
            'ldpc': 'update_ldpc',
            'mcs_index': 'update_mcs_index',
            'fec_k': 'update_fec_k',
            'fec_n': 'update_fec_n'
        }
        
        # Execute update functions for changed fields
        for field, value in changes.items():
            if field in function_map:
                # Set the corresponding environment variable
                env_var = field.upper()
                os.environ[env_var] = str(value)
                
                # Run the update function
                subprocess.run(['bash', '-c', f'source {COMMANDS_SCRIPT} && {function_map[field]}'],
                             check=True)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
