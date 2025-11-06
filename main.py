import socket
import os
import mimetypes
import json
from datetime import datetime
import threading

# Define the host and port
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 8080

# Configuration for server behavior
MAX_CONNECTIONS = 10  # Increased from 5 for better load handling
BUFFER_SIZE = 8192  # Increased from 1500 for better performance
REQUEST_TIMEOUT = 30  # Timeout in seconds for client requests

# Initialize MIME types - this helps us serve files with correct content types
# MIME types tell the browser what kind of content it's receiving
mimetypes.init()

# ---------- LOGGING UTILITY ----------
# It's crucial to log server activity for debugging and monitoring
# We'll create a simple logger that writes to both console and file
class ServerLogger:
    def __init__(self, log_file='server.log'):
        self.log_file = log_file
    
    def log(self, message, level='INFO'):
        """
        Logs messages with timestamp and level.
        Level can be: INFO, WARNING, ERROR, DEBUG
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f'[{timestamp}] [{level}] {message}'
        print(log_message)
        
        # Write to log file for persistence
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_message + '\n')
        except Exception as e:
            print(f'Failed to write to log file: {e}')

logger = ServerLogger()

# ---------- CREATE SOCKET ----------
# Create a TCP/IP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Enable reusing the same address/port even if previous instance didn't release it yet
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Set socket timeout to prevent indefinite blocking
# This ensures that if a client hangs, our server doesn't freeze
server_socket.settimeout(REQUEST_TIMEOUT)

# Bind the socket to the address and port
try:
    server_socket.bind((SERVER_HOST, SERVER_PORT))
except OSError as e:
    logger.log(f'Failed to bind to {SERVER_HOST}:{SERVER_PORT}. Error: {e}', 'ERROR')
    logger.log(f'Make sure the port {SERVER_PORT} is not already in use.', 'ERROR')
    exit(1)

# Enable the server to accept connections (max 10 clients in waiting queue)
server_socket.listen(MAX_CONNECTIONS)

logger.log(f'Server successfully started on {SERVER_HOST}:{SERVER_PORT}', 'INFO')
logger.log(f'Maximum connections in queue: {MAX_CONNECTIONS}', 'INFO')
logger.log(f'Waiting for connections...', 'INFO')

# ---------- HELPER FUNCTIONS ----------
def get_content_type(file_path):
    """
    Determines the MIME type of a file based on its extension.
    This is essential for the browser to correctly interpret the file.
    For example, .html files should be served as text/html,
    .json as application/json, .css as text/css, etc.
    """
    content_type, _ = mimetypes.guess_type(file_path)
    # Default to plain text if type cannot be determined
    return content_type or 'text/plain'

def read_file_safely(file_path):
    """
    Safely reads a file with proper error handling.
    Returns tuple: (success: bool, content: str/bytes, error_message: str)
    """
    try:
        # Check if file exists first
        if not os.path.exists(file_path):
            return False, None, f'File not found: {file_path}'
        
        # Determine if file should be read as binary or text
        # Images, videos, PDFs etc should be binary
        content_type = get_content_type(file_path)
        is_binary = not content_type.startswith('text') and content_type != 'application/json'
        
        mode = 'rb' if is_binary else 'r'
        encoding = None if is_binary else 'utf-8'
        
        with open(file_path, mode, encoding=encoding) as f:
            content = f.read()
        
        return True, content, None
        
    except PermissionError:
        return False, None, f'Permission denied: {file_path}'
    except Exception as e:
        return False, None, f'Error reading file: {str(e)}'

def build_response(status_code, status_text, content='', content_type='text/html', extra_headers=None):
    """
    Builds a complete HTTP response with proper headers.
    This is a cleaner way to construct responses than string concatenation.
    
    Parameters:
    - status_code: HTTP status code (200, 404, 500, etc.)
    - status_text: Status message (OK, Not Found, etc.)
    - content: Response body content
    - content_type: MIME type of the content
    - extra_headers: Dictionary of additional headers to include
    """
    # Start with status line
    response = f'HTTP/1.1 {status_code} {status_text}\r\n'
    
    # Add standard headers
    headers = {
        'Server': 'Own-Web-Server/1.0',
        'Date': datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT'),
        'Content-Type': content_type,
        'Content-Length': len(content) if isinstance(content, bytes) else len(content.encode('utf-8')),
        'Connection': 'close'  # We close after each request for simplicity
    }
    
    # Add any extra headers provided
    if extra_headers:
        headers.update(extra_headers)
    
    # Build header section
    for key, value in headers.items():
        response += f'{key}: {value}\r\n'
    
    # Empty line separates headers from body (REQUIRED by HTTP spec)
    response += '\r\n'
    
    # Return response as bytes if content is binary, otherwise encode
    if isinstance(content, bytes):
        return response.encode('utf-8') + content
    else:
        return (response + content).encode('utf-8')

def create_error_page(status_code, status_text, message):
    """
    Creates a user-friendly HTML error page instead of plain text.
    This provides better UX when errors occur.
    """
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{status_code} - {status_text}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            color: #333;
        }}
        .error-container {{
            background: white;
            padding: 3rem;
            border-radius: 15px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            text-align: center;
            max-width: 500px;
        }}
        .error-code {{
            font-size: 5rem;
            font-weight: bold;
            color: #667eea;
            margin: 0;
        }}
        .error-text {{
            font-size: 1.5rem;
            color: #666;
            margin: 1rem 0;
        }}
        .error-message {{
            color: #888;
            margin: 1rem 0;
        }}
        .back-button {{
            display: inline-block;
            margin-top: 2rem;
            padding: 0.8rem 2rem;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 25px;
            transition: transform 0.3s;
        }}
        .back-button:hover {{
            transform: translateY(-2px);
        }}
    </style>
</head>
<body>
    <div class="error-container">
        <h1 class="error-code">{status_code}</h1>
        <h2 class="error-text">{status_text}</h2>
        <p class="error-message">{message}</p>
        <a href="/" class="back-button">← Back to Home</a>
    </div>
</body>
</html>'''
    return html

def parse_request(request_data):
    """
    Parses HTTP request and extracts key information.
    Returns a dictionary with method, path, headers, and body.
    This centralizes request parsing and makes it reusable.
    """
    try:
        # Split request into lines
        lines = request_data.split('\r\n')
        if not lines or not lines[0]:
            return None
        
        # Parse request line (first line)
        request_line_parts = lines[0].split()
        if len(request_line_parts) < 2:
            return None
        
        method = request_line_parts[0]
        path = request_line_parts[1]
        http_version = request_line_parts[2] if len(request_line_parts) > 2 else 'HTTP/1.1'
        
        # Parse headers
        headers = {}
        body_start = 0
        for i, line in enumerate(lines[1:], 1):
            if line == '':
                body_start = i + 1
                break
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()
        
        # Get body if present
        body = '\r\n'.join(lines[body_start:]) if body_start > 0 else ''
        
        return {
            'method': method,
            'path': path,
            'http_version': http_version,
            'headers': headers,
            'body': body
        }
    except Exception as e:
        logger.log(f'Error parsing request: {e}', 'ERROR')
        return None

def handle_client(client_socket, client_address):
    """
    Handles individual client connection in a separate thread.
    This allows the server to handle multiple clients simultaneously.
    Each client gets their own thread, preventing one slow client
    from blocking others.
    """
    logger.log(f'New connection from {client_address[0]}:{client_address[1]}', 'INFO')
    
    try:
        # Set timeout for this specific client socket
        client_socket.settimeout(REQUEST_TIMEOUT)
        
        # Receive request data - using larger buffer for better performance
        request_data = client_socket.recv(BUFFER_SIZE).decode('utf-8')
        
        if not request_data:
            logger.log(f'Empty request from {client_address[0]}', 'WARNING')
            return
        
        # Parse the request
        request = parse_request(request_data)
        if not request:
            error_html = create_error_page(400, 'Bad Request', 'The request could not be understood by the server.')
            response = build_response(400, 'Bad Request', error_html)
            client_socket.sendall(response)
            return
        
        logger.log(f'{request["method"]} {request["path"]} from {client_address[0]}', 'INFO')
        
        # Handle different HTTP methods
        if request['method'] == 'GET':
            handle_get_request(client_socket, request['path'])
        elif request['method'] == 'POST':
            handle_post_request(client_socket, request['path'], request['body'])
        elif request['method'] == 'HEAD':
            # HEAD is like GET but only returns headers, no body
            handle_head_request(client_socket, request['path'])
        else:
            # Method not allowed
            error_html = create_error_page(405, 'Method Not Allowed', 
                                          f'The {request["method"]} method is not supported for this resource.')
            response = build_response(405, 'Method Not Allowed', error_html, 
                                     extra_headers={'Allow': 'GET, POST, HEAD'})
            client_socket.sendall(response)
            logger.log(f'Method {request["method"]} not allowed for {request["path"]}', 'WARNING')
    
    except socket.timeout:
        logger.log(f'Request timeout from {client_address[0]}', 'WARNING')
        error_html = create_error_page(408, 'Request Timeout', 'The server timed out waiting for the request.')
        response = build_response(408, 'Request Timeout', error_html)
        try:
            client_socket.sendall(response)
        except:
            pass
    
    except Exception as e:
        logger.log(f'Error handling client {client_address[0]}: {e}', 'ERROR')
        error_html = create_error_page(500, 'Internal Server Error', 'An unexpected error occurred on the server.')
        response = build_response(500, 'Internal Server Error', error_html)
        try:
            client_socket.sendall(response)
        except:
            pass
    
    finally:
        # Always close the client socket to free resources
        try:
            client_socket.close()
            logger.log(f'Connection closed for {client_address[0]}', 'DEBUG')
        except:
            pass

def handle_get_request(client_socket, path):
    """
    Handles GET requests by serving files from the workspace.
    This is the most common HTTP method used by browsers.
    """
    # Remove query parameters if present (everything after ?)
    path = path.split('?')[0]
    
    # Route mapping - maps URL paths to files
    route_map = {
        '/': 'index.html',
        '/book': 'book.json',
        '/book.json': 'book.json'
    }
    
    # Get the file to serve
    if path in route_map:
        file_path = route_map[path]
    else:
        # Try to serve the file directly if it exists in the workspace
        # Remove leading slash and prevent directory traversal attacks
        file_path = path.lstrip('/').replace('..', '')
    
    # Read the file
    success, content, error = read_file_safely(file_path)
    
    if success:
        content_type = get_content_type(file_path)
        response = build_response(200, 'OK', content, content_type)
        client_socket.sendall(response)
        logger.log(f'Served {file_path} ({content_type})', 'INFO')
    else:
        # File not found or error reading
        error_html = create_error_page(404, 'Not Found', f'The requested resource "{path}" was not found on this server.')
        response = build_response(404, 'Not Found', error_html)
        client_socket.sendall(response)
        logger.log(f'404 - {path} not found: {error}', 'WARNING')

def handle_post_request(client_socket, path, body):
    """
    Handles POST requests. This is useful for form submissions,
    API calls, and data uploads. Currently implements a simple
    echo endpoint for demonstration.
    """
    if path == '/api/echo':
        # Echo endpoint - returns the data sent to it
        try:
            # Try to parse as JSON
            data = json.loads(body) if body else {}
            response_data = {
                'success': True,
                'message': 'Data received successfully',
                'received': data,
                'timestamp': datetime.now().isoformat()
            }
            response_json = json.dumps(response_data, indent=2)
            response = build_response(200, 'OK', response_json, 'application/json')
            client_socket.sendall(response)
            logger.log(f'POST /api/echo - Data: {body[:100]}...', 'INFO')
        except json.JSONDecodeError:
            error_data = {'success': False, 'error': 'Invalid JSON'}
            response = build_response(400, 'Bad Request', json.dumps(error_data), 'application/json')
            client_socket.sendall(response)
    else:
        # Endpoint not found
        error_html = create_error_page(404, 'Not Found', f'The API endpoint "{path}" does not exist.')
        response = build_response(404, 'Not Found', error_html)
        client_socket.sendall(response)

def handle_head_request(client_socket, path):
    """
    Handles HEAD requests. Returns only headers without the body.
    This is useful for checking if a resource exists or getting
    metadata without downloading the entire file.
    """
    # Similar to GET but only send headers
    path = path.split('?')[0]
    route_map = {
        '/': 'index.html',
        '/book': 'book.json',
        '/book.json': 'book.json'
    }
    
    file_path = route_map.get(path, path.lstrip('/').replace('..', ''))
    success, content, error = read_file_safely(file_path)
    
    if success:
        content_type = get_content_type(file_path)
        # Build response but with empty content
        response = build_response(200, 'OK', '', content_type)
        client_socket.sendall(response)
        logger.log(f'HEAD {file_path}', 'INFO')
    else:
        response = build_response(404, 'Not Found', '')
        client_socket.sendall(response)

# ---------- MAIN SERVER LOOP ----------
try:
    while True:
        try:
            # Accept new connection
            # This blocks until a connection is made or timeout occurs
            client_socket, client_address = server_socket.accept()
            
            # Create a new thread to handle this client
            # This allows us to handle multiple clients concurrently
            # daemon=True means the thread will automatically close when main program exits
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()
            
        except socket.timeout:
            # This is normal - just means no connection was made in timeout period
            # We continue the loop to accept more connections
            continue
            
        except KeyboardInterrupt:
            # User pressed Ctrl+C
            logger.log('Keyboard interrupt received. Shutting down...', 'INFO')
            break
            
except Exception as e:
    logger.log(f'Fatal server error: {e}', 'ERROR')

finally:
    # Clean shutdown - close the server socket
    logger.log('Closing server socket...', 'INFO')
    server_socket.close()
    logger.log('Server stopped.', 'INFO')