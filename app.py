from flask import Flask, render_template, send_file, request, redirect, url_for, flash, jsonify
import os
from pathlib import Path
import configparser
from typing import Dict, List
import shutil
import subprocess
import yaml
import re
import platform
import time
import json
import tempfile

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
THUMBNAIL_FOLDER = os.path.join('static', 'thumbnails')
THUMBNAIL_SIZE = '320x180'  # 16:9 aspect ratio

def ensure_thumbnail_dir():
    """Ensure the thumbnail directory exists"""
    os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

def generate_thumbnail(video_path, video_filename):
    """Generate a thumbnail for a video file using ffmpeg"""
    thumbnail_filename = f"{os.path.splitext(video_filename)[0]}.jpg"
    thumbnail_path = os.path.join(THUMBNAIL_FOLDER, thumbnail_filename)
    
    # Only generate thumbnail if it doesn't exist or video is newer
    if (not os.path.exists(thumbnail_path) or 
        os.path.getmtime(video_path) > os.path.getmtime(thumbnail_path)):
        try:
            # Create a temporary file for the thumbnail
            with tempfile.NamedTemporaryFile(suffix='.jpg') as temp_thumb:
                # Extract frame at 1 second mark
                subprocess.run([
                    'ffmpeg', '-y',
                    '-ss', '1',  # Seek to 1 second
                    '-i', video_path,
                    '-vframes', '1',  # Extract one frame
                    '-s', THUMBNAIL_SIZE,  # Resize
                    '-f', 'image2',  # Force image output
                    temp_thumb.name
                ], check=True, capture_output=True)
                
                # Move the temporary thumbnail to final location
                import shutil
                shutil.copy2(temp_thumb.name, thumbnail_path)
                
            return thumbnail_filename
        except subprocess.CalledProcessError as e:
            print(f"Error generating thumbnail for {video_filename}: {e}")
            return None
    
    return thumbnail_filename

def ping_host(host, timeout=10):
    """
    Returns True if host responds to a ping request, False otherwise
    
    Args:
        host (str): The host to ping
        timeout (int): Timeout in seconds
    """
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', host]
    
    try:
        subprocess.check_output(command, stderr=subprocess.STDOUT, timeout=timeout)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False

def read_ini_file(filepath: str) -> Dict:
    config = configparser.ConfigParser()
    try:
        config.read(filepath)
        return {section: dict(config[section]) for section in config.sections()}
    except Exception as e:
        print(f"Error reading config file: {str(e)}")
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
    ensure_thumbnail_dir()
    video_files = []
    if os.path.exists(MEDIA_FOLDER):
        for file in os.listdir(MEDIA_FOLDER):
            if file.lower().endswith(('.mp4', '.avi', '.mkv', '.mov')):
                file_path = os.path.join(MEDIA_FOLDER, file)
                size = os.path.getsize(file_path)
                size_mb = round(size / (1024 * 1024), 2)
                
                # Generate thumbnail
                thumbnail = generate_thumbnail(file_path, file)
                
                video_files.append({
                    'name': file,
                    'size': size_mb,
                    'thumbnail': thumbnail
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

@app.route('/rssi')
def rssi_grapher():
    return render_template('rssi_grapher.html')

@app.route('/rssi/data')
def rssi_data():
    try:
        print("Starting rssi_data request...")
        # Check if the API endpoint is reachable with shorter timeout
        if not ping_host('10.5.0.1', timeout=2):
            print("API endpoint ping failed")
            return jsonify({
                'success': False,
                'message': 'API endpoint is not reachable'
            }), 404
            
        try:
            print("Starting netcat process...")
            # Use popen to handle streaming output
            process = subprocess.Popen(
                ['nc', '10.5.0.1', '8103'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            print("Reading netcat output...")
            # Read for up to 2 seconds
            import select
            readable, _, _ = select.select([process.stdout], [], [], 2)
            
            if not readable:
                process.kill()
                print("No data received within timeout")
                return jsonify({
                    'success': False,
                    'message': 'No data received from API endpoint'
                }), 504
                
            # Read the available output
            output = process.stdout.readline()
            print(f"Raw output received: {output[:200]}...")
            
            if not output.strip():
                process.kill()
                print("Empty output received")
                return jsonify({
                    'success': False,
                    'message': 'Empty response from API endpoint'
                }), 504
            
            # Parse the received JSON data
            try:
                data = json.loads(output)
                print(f"Parsed JSON: {str(data)[:200]}...")
                print(f"Data type: {data.get('type')}")
                print(f"Has rx_ant_stats: {'rx_ant_stats' in data}")
                
                if (data.get('type') == 'rx' and 
                    'rx_ant_stats' in data and 
                    data['rx_ant_stats']):
                    print("Found valid rx stats in first object")
                    process.kill()
                    return jsonify({
                        'success': True,
                        'data': data
                    })
                
                # If first object wasn't rx stats, try a few more times
                for _ in range(5):  # Try up to 5 more lines
                    output = process.stdout.readline()
                    if not output.strip():
                        continue
                        
                    print(f"Trying next line: {output[:200]}...")
                    data = json.loads(output)
                    
                    if (data.get('type') == 'rx' and 
                        'rx_ant_stats' in data and 
                        data['rx_ant_stats']):
                        print("Found valid rx stats in subsequent object")
                        process.kill()
                        return jsonify({
                            'success': True,
                            'data': data
                        })
                
                process.kill()
                print("No valid rx stats found in response")
                return jsonify({
                    'success': False,
                    'message': 'No RSSI data found in response'
                }), 404
                
            except json.JSONDecodeError as e:
                process.kill()
                print(f"JSON decode error: {str(e)}")
                print(f"Raw output: {output[:200]}...")
                return jsonify({
                    'success': False,
                    'message': 'Invalid JSON response from API'
                }), 500
                
        except Exception as e:
            if process:
                process.kill()
            print(f"Error reading from netcat: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'Error reading from netcat: {str(e)}'
            }), 500
            
    except Exception as e:
        print(f"Unexpected error in rssi_data: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/camera')
def camera_settings():
    return render_template('camera_settings.html')

@app.route('/camera/load-config')
def load_camera_config():
    try:
        # Increase timeout and attempts for more reliable connection
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Check if camera is reachable with longer timeout
                if not ping_host('10.5.0.10', timeout=10):
                    if attempt == max_retries - 1:
                        return jsonify({
                            'success': False,
                            'message': 'Camera is not reachable after multiple attempts. Please check the connection.'
                        }), 404
                    continue
                
                # If ping successful, proceed with config reading
                wfb_output = subprocess.check_output(
                    ['bash', '-c', f'source {COMMANDS_SCRIPT} && read_wfb_config'], 
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=15  # Increase SSH command timeout
                )
                
                majestic_output = subprocess.check_output(
                    ['bash', '-c', f'source {COMMANDS_SCRIPT} && read_majestic_config'],
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=15  # Increase SSH command timeout
                )
                
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
                    video_config = majestic_config.get('video0', {})
                except yaml.YAMLError as e:
                    print(f"YAML parsing error: {e}")
                    video_config = {}
                
                # Build response with actual values, not defaults
                config = {
                    'fps': str(video_config.get('fps', '60')),
                    'size': str(video_config.get('size', '1920x1080')),
                    'bitrate': str(video_config.get('bitrate', '4096')),
                    'gopSize': str(video_config.get('gopSize', '1')),
                    'channel': wfb_config.get('channel', '161'),
                    'txpower_override': wfb_config.get('driver_txpower_override', '1'),
                    'stbc': wfb_config.get('stbc', '0'),
                    'ldpc': wfb_config.get('ldpc', '0'),
                    'mcs_index': wfb_config.get('mcs_index', '1'),
                    'fec_k': wfb_config.get('fec_k', '8'),
                    'fec_n': wfb_config.get('fec_n', '12'),
                    'bandwidth': wfb_config.get('bandwidth', '20')
                }
                
                return jsonify({
                    'success': True,
                    'data': config
                })
                
            except subprocess.TimeoutExpired:
                if attempt == max_retries - 1:
                    raise
                continue
                
    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'message': f'Error executing SSH commands: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/camera/update', methods=['POST'])
def update_camera_settings():
    try:
        changes = request.json
        if not changes:
            return jsonify({'success': False, 'message': 'No changes detected'}), 400
            
        # Map frontend field names to environment variables and function names
        field_mapping = {
            # Majestic config fields
            'fps': {'env': 'FPS', 'func': 'update_fps'},
            'size': {'env': 'SIZE', 'func': 'update_size'},
            'bitrate': {'env': 'BITRATE', 'func': 'update_bitrate'},
            'gopSize': {'env': 'GOPSIZE', 'func': 'update_gopSize'},
            # WFB config fields
            'channel': {'env': 'CHANNEL', 'func': 'update_channel'},
            'txpower_override': {'env': 'TXPOWER_OVERRIDE', 'func': 'update_txpower_override'},
            'stbc': {'env': 'STBC', 'func': 'update_stbc'},
            'ldpc': {'env': 'LDPC', 'func': 'update_ldpc'},
            'mcs_index': {'env': 'MCS_INDEX', 'func': 'update_mcs_index'},
            'fec_k': {'env': 'FEC_K', 'func': 'update_fec_k'},
            'fec_n': {'env': 'FEC_N', 'func': 'update_fec_n'}
        }
        
        # Only process fields that were actually changed
        changed_fields = set(changes.keys())
        if not changed_fields:
            return jsonify({'success': False, 'message': 'No valid changes detected'}), 400

        updated_fields = []
        for field, value in changes.items():
            if field in field_mapping:
                # Create a new environment with all current env vars
                env = os.environ.copy()
                # Set the specific environment variable for this field
                env[field_mapping[field]['env']] = str(value)
                
                print(f"Updating {field} to {value} using {field_mapping[field]['env']}")
                
                try:
                    # Run only the update function for this specific changed field
                    result = subprocess.run(
                        ['bash', '-c', f'source {COMMANDS_SCRIPT} && {field_mapping[field]["func"]}'],
                        env=env,
                        check=True,
                        text=True,
                        capture_output=True
                    )
                    print(f"Command output: {result.stdout}")
                    if result.stderr:
                        print(f"Command error: {result.stderr}")
                    updated_fields.append(field)
                except subprocess.CalledProcessError as e:
                    print(f"Error updating {field}: {str(e)}")
                    return jsonify({
                        'success': False, 
                        'message': f'Error updating {field}',
                        'updated_fields': updated_fields
                    }), 500
        
        return jsonify({
            'success': True,
            'message': f'Successfully updated: {", ".join(updated_fields)}'
        })
    except Exception as e:
        print(f"Error in update_camera_settings: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/camera/reboot', methods=['POST'])
def reboot_camera():
    try:
        # Check if camera is reachable
        if not ping_host('10.5.0.10'):
            return jsonify({
                'success': False,
                'message': 'Camera is not reachable. Please check the connection.'
            }), 404
            
        # Execute the reboot command
        result = subprocess.run(
            ['bash', '-c', f'source {COMMANDS_SCRIPT} && update_reboot'],
            check=True,
            text=True,
            capture_output=True
        )
        
        return jsonify({
            'success': True,
            'message': 'Camera reboot initiated successfully'
        })
        
    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'message': f'Error rebooting camera: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/camera/restart-majestic', methods=['POST'])
def restart_majestic():
    try:
        # Check if camera is reachable
        if not ping_host('10.5.0.10'):
            return jsonify({
                'success': False,
                'message': 'Camera is not reachable. Please check the connection.'
            }), 404
            
        # Execute the restart majestic command
        result = subprocess.run(
            ['bash', '-c', f'source {COMMANDS_SCRIPT} && update_restart_majestic'],
            check=True,
            text=True,
            capture_output=True
        )
        
        return jsonify({
            'success': True,
            'message': 'Majestic service restarted successfully'
        })
        
    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'message': f'Error restarting Majestic: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500

@app.route('/config/restart-gs-wfb', methods=['POST'])
def restart_gs_wfb():
    try:
        result = subprocess.run(
            ['bash', '-c', f'source {COMMANDS_SCRIPT} && update_restart_gs_wfb'],
            check=True,
            text=True,
            capture_output=True
        )
        
        return jsonify({
            'success': True,
            'message': 'WFB Ground Station services restarted successfully'
        })
        
    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'message': f'Error restarting WFB services: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Unexpected error: {str(e)}'
        }), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
