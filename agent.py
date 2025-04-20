import requests
from supabase import create_client, Client
import re
import json
import os
import tempfile
import whisper
import io
import subprocess
import shutil
import sys
import zipfile
import time
import base64
from typing import Dict, List, Any, Union
from dotenv import load_dotenv

# Try to load .env file if it exists
try:
    load_dotenv()
    print("Loaded environment from .env file")
except ImportError:
    print("python-dotenv package not installed. Loading directly from environment.")
except Exception as e:
    print(f"Could not load .env file: {str(e)}")

# ---------- Set up FFmpeg path for Windows compatibility ---------- #
def setup_ffmpeg():
    """Set up FFmpeg path for Windows compatibility by downloading if necessary"""
    # Check if FFmpeg is available in PATH
    try:
        # Check if ffmpeg command is available
        result = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode == 0:
            print("FFmpeg found in PATH")
            # Tell Whisper to use the system FFmpeg
            os.environ["FFMPEG_BINARY"] = shutil.which("ffmpeg")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("FFmpeg not found in PATH, attempting to download and configure...")
    
    # Create a local FFmpeg directory in the application folder
    ffmpeg_dir = os.path.join(os.getcwd(), 'ffmpeg-local')
    os.makedirs(ffmpeg_dir, exist_ok=True)
    
    # Check if bin directory already exists with ffmpeg.exe
    ffmpeg_exe_path = None
    for root, dirs, files in os.walk(ffmpeg_dir):
        if 'ffmpeg.exe' in files:
            ffmpeg_exe_path = os.path.join(root, 'ffmpeg.exe')
            bin_dir = root
            # Add to PATH
            os.environ['PATH'] = os.pathsep.join([bin_dir, os.environ['PATH']])
            # Explicitly set for Whisper
            os.environ["FFMPEG_BINARY"] = ffmpeg_exe_path
            print(f"Using existing FFmpeg from {ffmpeg_exe_path}")
            return True
    
    try:
        # Download FFmpeg
        print("Downloading FFmpeg (this may take a few minutes)...")
        ffmpeg_zip = os.path.join(ffmpeg_dir, 'ffmpeg.zip')
        ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        
        # Download the file
        response = requests.get(ffmpeg_url, stream=True)
        if response.status_code == 200:
            # Make sure we're not trying to overwrite a file in use
            if os.path.exists(ffmpeg_zip):
                try:
                    os.remove(ffmpeg_zip)
                except OSError:
                    # If we can't remove it, use a different name
                    ffmpeg_zip = os.path.join(ffmpeg_dir, f'ffmpeg_{os.urandom(4).hex()}.zip')
            
            with open(ffmpeg_zip, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            print("Extracting FFmpeg...")
            # Extract the ZIP file
            with zipfile.ZipFile(ffmpeg_zip, 'r') as zip_ref:
                zip_ref.extractall(ffmpeg_dir)
            
            # Find the bin directory in the extracted contents
            for root, dirs, files in os.walk(ffmpeg_dir):
                if 'ffmpeg.exe' in files:
                    ffmpeg_exe_path = os.path.join(root, 'ffmpeg.exe')
                    bin_dir = root
                    # Add to PATH
                    os.environ['PATH'] = os.pathsep.join([bin_dir, os.environ['PATH']])
                    # Explicitly set for Whisper
                    os.environ["FFMPEG_BINARY"] = ffmpeg_exe_path
                    print(f"Added FFmpeg from {ffmpeg_exe_path} to PATH")
                    
                    # Clean up the zip file
                    try:
                        os.remove(ffmpeg_zip)
                    except OSError as e:
                        print(f"Note: Could not remove zip file: {e}")
                    return True
            
            print("Could not find ffmpeg.exe in the extracted archive")
            return False
        else:
            print(f"Failed to download FFmpeg: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"Error setting up FFmpeg: {str(e)}")
        return False

def ensure_ffmpeg_available():
    """
    Ensure FFmpeg is available for Whisper transcription, especially on Windows systems.
    Returns True if FFmpeg is configured properly, False otherwise.
    """
    try:
        # Check if we're on Windows
        is_windows = sys.platform.startswith('win')
        
        if is_windows:
            # On Windows, we need to set the FFmpeg path explicitly
            # Try to find FFmpeg from common install locations
            potential_paths = [
                os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'ffmpeg', 'bin'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'ffmpeg', 'bin'),
                os.path.join(os.environ.get('USERPROFILE', 'C:\\Users\\' + os.getlogin()), 'ffmpeg', 'bin'),
                os.path.join(os.environ.get('LOCALAPPDATA', 'C:\\Users\\' + os.getlogin() + '\\AppData\\Local'), 'ffmpeg', 'bin')
            ]
            
            # Add current directory and script directory
            potential_paths.append(os.path.abspath(os.path.dirname(__file__)))
            potential_paths.append(os.getcwd())
            
            ffmpeg_path = None
            for path in potential_paths:
                test_path = os.path.join(path, 'ffmpeg.exe')
                if os.path.exists(test_path):
                    ffmpeg_path = test_path
                    break
            
            if ffmpeg_path:
                print(f"Found FFmpeg at: {ffmpeg_path}")
                # Set the environment variable for FFmpeg
                os.environ["FFMPEG_BINARY"] = ffmpeg_path
                # Also set the path for the parent directory for other tools
                bin_dir = os.path.dirname(ffmpeg_path)
                if bin_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
            else:
                # Try to check if FFmpeg is in PATH already
                try:
                    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
                    print("FFmpeg found in system PATH")
                except (subprocess.SubprocessError, FileNotFoundError):
                    print("WARNING: FFmpeg not found. Audio transcription may fail.")
                    print("Please install FFmpeg and make sure it's in your PATH")
                    print("Or place ffmpeg.exe in one of these directories:")
                    for path in potential_paths:
                        print(f"  - {path}")
                    return False
        else:
            # On Unix systems, check if FFmpeg is available
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
                print("FFmpeg found in system PATH")
            except (subprocess.SubprocessError, FileNotFoundError):
                print("WARNING: FFmpeg not found. Audio transcription may fail.")
                print("Please install FFmpeg with your package manager.")
                return False
        
        # Test FFmpeg directly instead of using whisper.utils.get_executor()
        try:
            # Simple test of FFmpeg functionality
            ffmpeg_cmd = ["ffmpeg", "-version"]
            result = subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
            if result.returncode == 0:
                print("FFmpeg test successful")
                return True
            else:
                print(f"FFmpeg test failed with return code {result.returncode}")
                return False
        except Exception as e:
            print(f"Error testing FFmpeg directly: {str(e)}")
            return False
            
    except Exception as e:
        print(f"Error configuring FFmpeg: {str(e)}")
        return False

# Initialize FFmpeg setup
setup_ffmpeg()

# Initialize Supabase config
# First try to get from environment variables, then fall back to hardcoded values
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://advfymskrwzncvmlgrxz.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdmZ5bXNrcnd6bmN2bWxncnh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNTk2ODAsImV4cCI6MjA2MDYzNTY4MH0.rLWsbtWRwfah1q_EXB86QFYABXO_j53PnjNITeGmPcc')

# Gemini API config
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ')
GEMINI_API_URL = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'

# Initialize Whisper model (will download on first use)
print("Loading Whisper model (this may take a few minutes on first run)...")
whisper_model = whisper.load_model("base")
print("Whisper model loaded successfully!")

# Create Supabase client
try:
    print(f"Connecting to Supabase at URL: {SUPABASE_URL}")
    sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Test the connection by making a simple query
    test_query = "SELECT 1 as test"
    test_response = sb.rpc('run_sql', {'sql_query': test_query}).execute()
    if test_response.data:
        print("Successfully connected to Supabase!")
    else:
        print("Warning: Connected to Supabase but received empty response from test query")
except Exception as e:
    print(f"Error connecting to Supabase: {str(e)}")
    print("Please check your Supabase URL and API key")
    sb = None

# ------------------------- Query Helpers ---------------------------- #
def get_supabase_schema_via_rest():
    """
    Get database schema information using the Supabase function get_table_schema
    """
    try:
        # Try using the direct RPC function first
        try:
            response = sb.rpc("get_table_schema", {}).execute()
            
            if response.data:
                schema = {}
                for entry in response.data:
                    table = entry["table_name"]
                    column = entry["column_name"]
                    if table not in schema:
                        schema[table] = []
                    schema[table].append(column)
                return schema
        except Exception as func_error:
            print(f"Direct RPC call failed: {str(func_error)}, falling back to SQL query.")
            
        # Fall back to SQL query if the RPC function isn't available
        schema_query = """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
        response = sb.rpc('run_sql_query', {'sql_query': schema_query}).execute()
        
        if not response.data:
            # Try alternative RPC function name
            response = sb.rpc('run_sql', {'sql_query': schema_query}).execute()
        
        if response.data:
            schema = {}
            for entry in response.data:
                table = entry["table_name"]
                column = entry["column_name"]
                if table not in schema:
                    schema[table] = []
                schema[table].append(column)
            return schema
        else:
            return {"error": "No data returned from schema query"}
    except Exception as e:
        return {"error": f"Exception occurred while fetching schema: {str(e)}"}

def execute_sql_query(query: str):
    """
    Executes an SQL query using Supabase and returns the results.
    Works with all SQL operations (SELECT, INSERT, UPDATE, DELETE).
    """
    try:
        query = query.strip().rstrip(';')  # Remove the semicolon
        print(f"Executing SQL Query: {query}")
        
        # Check if this is an INSERT statement
        if query.lower().startswith("insert into"):
            # Extract table name and values for the Insert
            match = re.match(r"insert\s+into\s+(\w+)\s*\((.*?)\)\s*values\s*\((.*?)\)", query, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                columns = [col.strip() for col in match.group(2).split(',')]
                values = [val.strip() for val in match.group(3).split(',')]
                
                # Convert values to proper format
                data = {}
                for i, column in enumerate(columns):
                    value = values[i]
                    # Convert 'NULL' to Python None
                    if value.upper() == 'NULL':
                        data[column] = None
                    # Remove quotes for strings
                    elif (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                        data[column] = value[1:-1]
                    # Try to convert numbers
                    else:
                        try:
                            # Convert to int or float
                            if '.' in value:
                                data[column] = float(value)
                            else:
                                data[column] = int(value)
                        except ValueError:
                            # If conversion fails, keep as string
                            data[column] = value
                
                print(f"Inserting into table '{table_name}' with data: {data}")
                response = sb.table(table_name).insert(data).execute()
                
                if hasattr(response, 'error') and response.error:
                    print(f"Insert error: {response.error}")
                    return {"error": f"Insert failed: {response.error}"}
                    
                if hasattr(response, 'data'):
                    return response.data
                else:
                    return {"message": "Insert was executed successfully", "success": True}
        
        # Check if this is an UPDATE statement
        elif query.lower().startswith("update"):
            # Extract table name, set values and where condition
            match = re.match(r"update\s+(\w+)\s+set\s+(.*?)\s+where\s+(.*)", query, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                set_clause = match.group(2)
                where_clause = match.group(3)
                
                # Parse the SET clause
                set_items = set_clause.split(',')
                data = {}
                
                for item in set_items:
                    if '=' in item:
                        column, value = [part.strip() for part in item.split('=', 1)]
                        
                        # Convert values
                        if value.upper() == 'NULL':
                            data[column] = None
                        # Remove quotes for strings
                        elif (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                            data[column] = value[1:-1]
                        # Try to convert numbers
                        else:
                            try:
                                # Convert to int or float
                                if '.' in value:
                                    data[column] = float(value)
                                else:
                                    data[column] = int(value)
                            except ValueError:
                                # If conversion fails, keep as string
                                data[column] = value
                
                # Parse the WHERE clause 
                # We'll only handle simple equality conditions like id = 5
                where_match = re.match(r"(\w+)\s*=\s*(\S+)", where_clause)
                if where_match:
                    where_column = where_match.group(1)
                    where_value = where_match.group(2).strip()
                    
                    # Convert where value
                    if where_value.startswith("'") and where_value.endswith("'"):
                        where_value = where_value[1:-1]  # Remove quotes
                    elif where_value.isdigit():
                        where_value = int(where_value)
                    
                    print(f"Updating table '{table_name}' with data: {data} where {where_column} = {where_value}")
                    
                    # Use the Supabase update function with the where clause
                    response = sb.table(table_name).update(data).eq(where_column, where_value).execute()
                    
                    if hasattr(response, 'error') and response.error:
                        print(f"Update error: {response.error}")
                        return {"error": f"Update failed: {response.error}"}
                        
                    if hasattr(response, 'data'):
                        return response.data
                    else:
                        return {"message": "Update was executed successfully", "success": True}
                        
        # Check if this is a DELETE statement
        elif query.lower().startswith("delete from"):
            # Extract table name and where condition
            match = re.match(r"delete\s+from\s+(\w+)(?:\s+where\s+(.*))?", query, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                where_clause = match.group(2) if match.group(2) else None
                
                # If there's no WHERE clause, this is a dangerous operation
                if not where_clause:
                    print("WARNING: DELETE without WHERE clause will delete all records!")
                    return {"error": "DELETE without WHERE clause is not allowed for safety. Please specify a WHERE condition."}
                
                # Parse the WHERE clause 
                # We'll only handle simple equality conditions like id = 5
                where_match = re.match(r"(\w+)\s*=\s*(\S+)", where_clause)
                if where_match:
                    where_column = where_match.group(1)
                    where_value = where_match.group(2).strip()
                    
                    # Convert where value
                    if where_value.startswith("'") and where_value.endswith("'"):
                        where_value = where_value[1:-1]  # Remove quotes
                    elif where_value.isdigit():
                        where_value = int(where_value)
                    
                    print(f"Deleting from table '{table_name}' where {where_column} = {where_value}")
                    
                    # Use the Supabase delete function with the where clause
                    response = sb.table(table_name).delete().eq(where_column, where_value).execute()
                    
                    if hasattr(response, 'error') and response.error:
                        print(f"Delete error: {response.error}")
                        return {"error": f"Delete failed: {response.error}"}
                        
                    if hasattr(response, 'data'):
                        return {"message": "Delete was executed successfully", "success": True, "rows_affected": len(response.data) if response.data else 0}
                    else:
                        return {"message": "Delete was executed successfully", "success": True}
        
        # For other SQL operations (mainly SELECT), use the RPC function
        try:
            response = sb.rpc("run_sql_query", {"sql_query": query}).execute()
        except Exception as e:
            # Fall back to alternative RPC function name
            print(f"First RPC call failed: {str(e)}, trying alternative method.")
            response = sb.rpc('run_sql', {'sql_query': query}).execute()
            
        if hasattr(response, 'error') and response.error:
            print(f"SQL query error: {response.error}")
            return {"error": f"Database error: {response.error}"}
            
        if hasattr(response, 'data'):
            if response.data:
                return response.data
            else:
                # For INSERT/UPDATE/DELETE, often no data is returned but operation succeeded
                if any(op in query.lower() for op in ['insert', 'update', 'delete']):
                    operation = "insert" if "insert" in query.lower() else "update" if "update" in query.lower() else "delete"
                    return {"message": f"The {operation} operation was executed successfully", "success": True}
                return []
        else:
            return {"warning": "Query executed but returned no data attribute"}
            
    except Exception as e:
        error_message = str(e)
        print(f"Query execution error: {error_message}")
        return {"error": f"Query failed: {error_message}"}

# --------------------- Schema Extraction -------------------------- #

def get_supabase_schema():
    schema_query = """
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
    ORDER BY table_name, ordinal_position;
    """
    return execute_sql_query(schema_query)

def format_schema_for_prompt(schema_data):
    schema_str = "Here is the database schema:\n"
    
    # Check if we're dealing with the dictionary format from get_supabase_schema_via_rest()
    if isinstance(schema_data, dict) and not "error" in schema_data:
        for table, columns in schema_data.items():
            schema_str += f"\nTable `{table}` with columns: {', '.join(columns)}"
    # Handle the list of dictionaries format from get_supabase_schema()
    elif isinstance(schema_data, list):
        table_dict = {}
        for row in schema_data:
            table = row['table_name']
            column = row['column_name']
            if table not in table_dict:
                table_dict[table] = []
            table_dict[table].append(column)
            
        for table, columns in table_dict.items():
            schema_str += f"\nTable `{table}` with columns: {', '.join(columns)}"
    
    return schema_str

# ------------------ Gemini API Interaction ---------------------- #

def nl_to_sql_gemini(prompt: str):
    """
    Convert natural language prompt to SQL query using Gemini AI.
    This version focuses on generating SQL directly for all operations.
    """
    headers = {
        "Content-Type": "application/json"
    }

    # Get and format schema
    schema_data = get_supabase_schema_via_rest()
    schema_error = "error" in schema_data
    
    if schema_error:
        print(f"Warning: Schema fetch issue: {schema_data['error']}")
        # Check if we can still proceed (status success error)
        if "status" in str(schema_data["error"]) and "success" in str(schema_data["error"]):
            print("Attempting to generate SQL without schema...")
            schema_description = "Generate SQL using the common tables like 'employees', 'customers', 'orders', 'products', or 'refund_requests' with standard columns."
        else:
            return {"error": "Failed to fetch schema from Supabase."}
    else:
        schema_description = format_schema_for_prompt(schema_data)

    # Detect operation type for better prompting
    prompt_lower = prompt.lower()
    is_update = "update" in prompt_lower or "modify" in prompt_lower or "change" in prompt_lower or "set" in prompt_lower
    is_delete = "delete" in prompt_lower or "remove" in prompt_lower
    is_insert = "insert" in prompt_lower or "add" in prompt_lower or "create" in prompt_lower or "new" in prompt_lower
    is_select = "fetch" in prompt_lower or "show" in prompt_lower or "get" in prompt_lower or "select" in prompt_lower or "find" in prompt_lower or "list" in prompt_lower

    # Check for explicit row references
    has_row_reference = re.search(r"(?:row|record|id)\s*(?:number)?\s*(\d+)", prompt_lower)
    row_id = has_row_reference.group(1) if has_row_reference else None

    # Build operation-specific guidance
    operation_guidance = ""
    if is_select:
        operation_guidance = "\nFor the SELECT query:\n- Use PostgreSQL syntax\n- Use single quotes for strings\n- Use ILIKE for case-insensitive matching"
    elif is_insert:
        operation_guidance = "\nFor the INSERT query:\n- Include all relevant columns from the user's request\n- Do NOT include the id column (it's auto-generated)\n- Do NOT include the created_at column (it's auto-generated)\n- Use single quotes for strings"
    elif is_update:
        operation_guidance = "\nFor the UPDATE query:\n- Include all relevant columns to update from the user's request\n- Be sure to include a proper WHERE clause"
        if row_id:
            operation_guidance += f"\n- Use 'WHERE id = {row_id}' as the condition"
    elif is_delete:
        operation_guidance = "\nFor the DELETE query:\n- Include a proper WHERE clause to avoid deleting all records"
        if row_id:
            operation_guidance += f"\n- Use 'WHERE id = {row_id}' as the condition"

    # Add table hint if we detect a specific table in the prompt
    table_hint = ""
    common_tables = ["employees", "customers", "orders", "products", "refund_requests"]
    for table in common_tables:
        if table in prompt_lower or table[:-1] in prompt_lower:  # Check singular and plural
            if schema_error:
                table_hint = f"\nYou should use the '{table}' table for this query."
            break

    # Construct refined prompt
    refined_prompt = (
        f"{schema_description}\n\n"
        f"Generate a PostgreSQL query for: {prompt}.{operation_guidance}{table_hint}\n\n"
        f"Return only the SQL query without any explanation, markdown formatting, or backticks."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": refined_prompt}
                ]
            }
        ]
    }

    response = requests.post(GEMINI_API_URL, json=payload, headers=headers)

    if response.status_code == 200:
        data = response.json()
        candidates = data.get('candidates', [])
        if candidates:
            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            # Clean up the response by removing markdown formatting
            text = text.replace('```sql', '').replace('```', '').strip()
            
            # Extract the actual SQL query
            sql_match = re.search(r'(SELECT|INSERT|UPDATE|DELETE).*', text, re.IGNORECASE | re.DOTALL)
            if sql_match:
                return sql_match.group(0).strip()
            return text.strip()
        else:
            return {"error": "No candidates returned by Gemini."}
    else:
        return {"error": response.text}

def transcribe_audio(audio_file):
    """
    Transcribe audio file using Whisper model.
    Falls back to an alternative method if the primary method fails.
    """
    if not os.path.exists(audio_file):
        return f"Error: Audio file '{audio_file}' not found."
    
    # Get file size and check if it's a valid audio file
    try:
        file_size = os.path.getsize(audio_file)
        if file_size == 0:
            return "Error: Audio file is empty."
        
        # Ensure FFmpeg is available before attempting transcription
        if not ensure_ffmpeg_available():
            return "Error: FFmpeg not properly configured for audio transcription."
        
        try:
            # Primary method: Use Whisper model directly
            print(f"Transcribing audio file: {audio_file}")
            result = whisper_model.transcribe(audio_file)
            return result["text"]
        except Exception as primary_error:
            print(f"Primary transcription method failed: {str(primary_error)}")
            
            # Fallback method: Use whisper with alternative approach
            try:
                print("Attempting fallback transcription method...")
                import tempfile
                import subprocess
                import json
                
                # Create temporary file for output
                with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as temp_output:
                    temp_output_path = temp_output.name
                
                try:
                    # Get the whisper installation path
                    import whisper
                    whisper_path = os.path.dirname(os.path.abspath(whisper.__file__))
                    python_exe = sys.executable
                    
                    # Run whisper CLI directly as a subprocess
                    cmd = [
                        python_exe,
                        "-m", "whisper",
                        audio_file,
                        "--model", "base",
                        "--output_format", "json",
                        "--output_dir", os.path.dirname(temp_output_path)
                    ]
                    
                    # On Windows, specify FFmpeg path if available
                    if sys.platform.startswith('win') and "FFMPEG_BINARY" in os.environ:
                        cmd.extend(["--ffmpeg_path", os.environ["FFMPEG_BINARY"]])
                    
                    print(f"Running fallback command: {' '.join(cmd)}")
                    subprocess.run(cmd, check=True, capture_output=True)
                    
                    # Load the output JSON
                    output_json = os.path.join(
                        os.path.dirname(temp_output_path),
                        os.path.basename(audio_file).rsplit(".", 1)[0] + ".json"
                    )
                    
                    if os.path.exists(output_json):
                        with open(output_json, 'r', encoding='utf-8') as f:
                            result_data = json.load(f)
                        os.unlink(output_json)
                        return result_data.get("text", "Transcription produced no text")
                    else:
                        return "Error: Fallback transcription did not produce output file."
                
                finally:
                    # Cleanup temp file
                    if os.path.exists(temp_output_path):
                        os.unlink(temp_output_path)
            
            except Exception as fallback_error:
                print(f"Fallback transcription method failed: {str(fallback_error)}")
                return f"Error transcribing audio: {str(primary_error)}. Fallback also failed: {str(fallback_error)}"
    
    except Exception as e:
        return f"Error checking audio file: {str(e)}"

def summarize_text(text):
    """Summarize text using Gemini API"""
    try:
        print("Generating summary using Gemini...")
        prompt = f"Please provide a concise summary of this audio transcript: {text}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }

        response = requests.post(GEMINI_API_URL, json=payload, headers={"Content-Type": "application/json"})
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data and len(data['candidates']) > 0:
                summary = data['candidates'][0]['content']['parts'][0]['text']
                print("Summary generated successfully!")
                return summary
        print("Could not generate summary from API response")
        return "Could not generate summary"
    except Exception as e:
        print(f"Error during summarization: {str(e)}")
        return f"Error summarizing text: {str(e)}"

def get_audio_summary(audio_path):
    """Get summary of audio content using transcription and summarization"""
    transcript = transcribe_audio(audio_path)
    if not transcript.startswith("Error"):
        return summarize_text(transcript)
    return transcript

def cleanup_temp_files(temp_dir=None):
    """Clean up temporary audio files and directory"""
    # If a list of files is provided, clean up those specific files
    if isinstance(temp_dir, list):
        file_list = temp_dir
        print(f"Cleaning up {len(file_list)} specific files")
        for file_path in file_list:
            if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
                try:
                    os.unlink(file_path)
                    print(f"Cleaned up file: {file_path}")
                except Exception as e:
                    print(f"Warning: Error cleaning up file {file_path}: {str(e)}")
        return
        
    # Otherwise clean up a whole directory
    if temp_dir is None:
        temp_dir = os.path.join(os.getcwd(), 'temp_audio')
        
    if not os.path.exists(temp_dir):
        return
        
    try:
        # Clean up all files in the directory
        files_removed = 0
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    files_removed += 1
                    print(f"Cleaned up file: {file_path}")
                elif os.path.isdir(file_path):
                    # Recursively clean subdirectories
                    shutil.rmtree(file_path, ignore_errors=True)
                    print(f"Cleaned up directory: {file_path}")
            except Exception as e:
                print(f"Warning: Error cleaning up {file_path}: {str(e)}")
                
        print(f"Removed {files_removed} files from {temp_dir}")
                
        # Try to remove the temp directory if it's now empty
        if files_removed > 0:
            try:
                # Only remove if directory is empty
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                    print(f"Removed empty temporary directory: {temp_dir}")
                else:
                    print(f"Directory not empty, keeping: {temp_dir}")
            except Exception as e:
                print(f"Warning: Error removing temporary directory: {str(e)}")
    except Exception as e:
        print(f"Warning: Error during cleanup: {str(e)}")
        # Continue execution despite cleanup errors

def ensure_temp_dir():
    """Ensure temporary directory exists and is clean"""
    temp_dir = os.path.join(os.getcwd(), 'temp_audio')
    
    # Clean up existing directory if it exists
    if os.path.exists(temp_dir):
        cleanup_temp_files(temp_dir)
        
    # Create fresh directory
    try:
        os.makedirs(temp_dir, exist_ok=True)
        print(f"Created/ensured temporary directory: {temp_dir}")
    except Exception as e:
        print(f"Error creating temporary directory: {str(e)}")
        return None
        
    return temp_dir

def download_audio_safer(url, temp_dir):
    """Download audio file in a way that's safer for Windows"""
    try:
        print(f"Downloading audio from {url}")
        
        # Use a cleaner filename with a unique identifier
        filename = f"audio_{os.urandom(4).hex()}.mp3"
        local_path = os.path.join(temp_dir, filename)
        
        # Download the file
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            print(f"Failed to download audio. HTTP status: {response.status_code}")
            return None
        
        # Make sure the temp directory exists
        if not os.path.exists(temp_dir):
            try:
                os.makedirs(temp_dir, exist_ok=True)
            except Exception as e:
                print(f"Error creating temp directory: {str(e)}")
                return None
            
        # Save to disk with proper file handling
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
            # Ensure data is written to disk
            f.flush()
            os.fsync(f.fileno())
        
        # Verify the file exists and is not empty
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f"Audio downloaded successfully to {local_path}")
            
            # For Windows, give a small delay to ensure file isn't locked
            if sys.platform.startswith('win'):
                time.sleep(0.5)
                
            # Attempt to read the first few bytes to verify file is accessible
            try:
                with open(local_path, 'rb') as test_read:
                    test_read.read(1024)
                print("File verified as readable")
            except Exception as e:
                print(f"Warning: Downloaded file not readable: {str(e)}")
                return None
                
            return local_path
        else:
            print("Downloaded file is empty or not accessible")
            if os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                except Exception as e:
                    print(f"Warning: Could not remove empty file: {str(e)}")
            return None
            
    except Exception as e:
        print(f"Error downloading audio: {str(e)}")
        return None

def process_audio_urls(audio_urls):
    """Process a list of audio URLs and return their transcriptions."""
    print(f"Processing {len(audio_urls)} audio URLs")
    
    # Ensure FFmpeg is properly configured before processing any audio
    if not ensure_ffmpeg_available():
        return {"error": "Failed to set up FFmpeg for audio processing"}
    
    # First ensure we have a clean temp directory
    temp_dir = ensure_temp_dir()
    if not temp_dir:
        return {"error": "Failed to create temporary directory"}
    
    results = []
    processed_files = []
    
    try:
        for url in audio_urls:
            print(f"Processing audio URL: {url}")
            local_path = None
            try:
                # Download the audio file
                local_path = download_audio_safer(url, temp_dir)
                if local_path:
                    processed_files.append(local_path)
                
                if local_path is None:
                    print(f"Failed to download audio from URL: {url}")
                    results.append({
                        "url": url,
                        "status": "download_failed",
                        "transcription": "Failed to download audio",
                        "summary": "Failed to download audio"
                    })
                    continue
                
                # Transcribe the audio
                print(f"Transcribing audio from: {local_path}")
                transcription = transcribe_audio(local_path)
                
                if transcription.startswith("Error"):
                    print(f"Transcription failed: {transcription}")
                    results.append({
                        "url": url,
                        "status": "transcription_failed",
                        "transcription": transcription,
                        "summary": "Failed to transcribe audio"
                    })
                    continue
                
                # Summarize the transcription
                print("Summarizing transcription")
                summary = summarize_text(transcription)
                
                results.append({
                    "url": url,
                    "status": "success",
                    "transcription": transcription,
                    "summary": summary
                })
                
            except Exception as e:
                error_message = f"Error processing audio URL {url}: {str(e)}"
                print(error_message)
                results.append({
                    "url": url,
                    "status": "error",
                    "transcription": error_message,
                    "summary": error_message
                })
            
            # Clean up the current file after processing
            if local_path and os.path.exists(local_path):
                try:
                    os.unlink(local_path)
                    print(f"Cleaned up file: {local_path}")
                    # Remove from processed_files list since we already cleaned it up
                    if local_path in processed_files:
                        processed_files.remove(local_path)
                except Exception as e:
                    print(f"Error cleaning up file {local_path}: {str(e)}")
    finally:
        # Clean up any remaining downloaded files
        if processed_files:
            cleanup_temp_files(processed_files)
        
        # Clean up the temp directory
        cleanup_temp_files(temp_dir)
        
    return results

def handle_audio_request(query_result):
    """Handle requests involving audio processing"""
    print("\nProcessing audio files...")
    
    # Extract audio URLs from different possible query result formats
    audio_urls = []
    
    if isinstance(query_result, list):
        if len(query_result) > 0:
            if isinstance(query_result[0], dict):
                # Case 1: List of dictionaries with 'audio_url' key
                if 'audio_url' in query_result[0]:
                    audio_urls = [record['audio_url'] for record in query_result if record.get('audio_url')]
                # Case 2: List of dictionaries with just URLs (single column query)
                elif len(query_result[0]) == 1:
                    # Get the first key, which should be the column name (likely 'audio_url')
                    key = list(query_result[0].keys())[0]
                    audio_urls = [record[key] for record in query_result if record.get(key)]
            # Case 3: Just a list of URLs as strings
            elif isinstance(query_result[0], str):
                audio_urls = [url for url in query_result if url]
    
    if not audio_urls:
        print("No valid audio URLs found in the query result.")
        return {"warning": "No valid audio URLs found", "data": query_result}
    
    print(f"Found {len(audio_urls)} audio URLs to process")
    
    try:
        return process_audio_urls(audio_urls)
    finally:
        # Ensure cleanup happens even if processing fails
        cleanup_temp_files()

# ------------------- Image Processing Functions -------------------- #
def image_url_to_base64(image_url):
    """Convert an image URL to base64 encoding"""
    image_response = requests.get(image_url)
    if image_response.status_code == 200:
        return base64.b64encode(image_response.content).decode("utf-8")
    else:
        raise Exception(f"Failed to fetch image. Status code: {image_response.status_code}")

def extract_amount_from_receipt(image_url):
    """Extract the total amount from a receipt image using Gemini Vision"""
    try:
        print(f"Extracting amount from receipt image: {image_url}")
        base64_image = image_url_to_base64(image_url)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        { "text": "What is the total amount in this receipt?" },
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64_image
                            }
                        }
                    ]
                }
            ]
        }

        response = requests.post(GEMINI_API_URL, json=payload)

        if response.status_code == 200:
            try:
                response_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                print("🔎 Gemini response:", response_text)

                # Updated regex to match amounts with any number of decimal places
                match = re.search(r"\$?\s?([\d,]+\.?\d*)", response_text)
                if match:
                    # Clean the amount string by removing any non-numeric characters except decimal point
                    amount_str = match.group(1).replace(",", "").replace("$", "")
                    # Further clean to ensure only digits and decimal point remain
                    amount_str = ''.join(c for c in amount_str if c.isdigit() or c == '.')
                    return float(amount_str)
                else:
                    print("❌ No valid amount found in response.")
                    return None
            except KeyError:
                print("❌ Could not parse response.")
                return None
        else:
            print("❌ Error calling Gemini API:", response.status_code, response.text)
            return None
    except Exception as e:
        print(f"Error extracting amount from receipt: {str(e)}")
        return None

def process_receipt_images(image_urls):
    """Process a list of receipt image URLs and extract amounts"""
    print(f"Processing {len(image_urls)} receipt images")
    
    results = []
    
    for image_url in image_urls:
        print(f"Processing receipt image: {image_url}")
        try:
            amount = extract_amount_from_receipt(image_url)
            
            if amount is None:
                results.append({
                    "url": image_url,
                    "status": "extraction_failed",
                    "amount": None,
                    "message": "Failed to extract amount from receipt"
                })
                continue
            
            # Try to save the extracted amount to the database
            try:
                insert_data = {
                    'image_url': image_url,
                    'amount': amount
                }
                
                # Insert into refund_requests table
                if sb is not None:
                    response = sb.table('refund_requests').insert(insert_data).execute()
                    if hasattr(response, 'data') and response.data:
                        insert_id = response.data[0]['id'] if response.data and len(response.data) > 0 else None
                        print(f"✅ Saved to database with ID: {insert_id}")
                        db_success = True
                    else:
                        print("⚠️ Database insert returned no data")
                        db_success = False
                else:
                    print("⚠️ Supabase client not initialized")
                    db_success = False
                
                results.append({
                    "url": image_url,
                    "status": "success" if db_success else "db_save_failed",
                    "amount": amount,
                    "saved_to_db": db_success
                })
                
            except Exception as db_error:
                print(f"Error saving to database: {str(db_error)}")
                results.append({
                    "url": image_url,
                    "status": "db_save_failed",
                    "amount": amount,
                    "error": str(db_error)
                })
                
        except Exception as e:
            error_message = f"Error processing receipt image {image_url}: {str(e)}"
            print(error_message)
            results.append({
                "url": image_url,
                "status": "error",
                "error": error_message
            })
    
    return results

def handle_image_request(query_result):
    """Handle requests involving image processing"""
    print("\nProcessing receipt images...")
    
    # Extract image URLs from different possible query result formats
    image_urls = []
    
    if isinstance(query_result, list):
        if len(query_result) > 0:
            if isinstance(query_result[0], dict):
                # Case 1: List of dictionaries with 'image_url' key
                if 'image_url' in query_result[0]:
                    image_urls = [record['image_url'] for record in query_result if record.get('image_url')]
                # Case 2: List of dictionaries with just URLs (single column query)
                elif len(query_result[0]) == 1:
                    # Get the first key, which should be the column name (likely 'image_url')
                    key = list(query_result[0].keys())[0]
                    image_urls = [record[key] for record in query_result if record.get(key)]
            # Case 3: Just a list of URLs as strings
            elif isinstance(query_result[0], str):
                image_urls = [url for url in query_result if url]
    
    if not image_urls:
        print("No valid image URLs found in the query result.")
        return {"warning": "No valid image URLs found", "data": query_result}
    
    print(f"Found {len(image_urls)} image URLs to process")
    return process_receipt_images(image_urls)

# ------------------- Storage and Batch Processing Functions -------------------- #
def fetch_and_process_storage_receipts(start_num=1, end_num=10):
    """
    Fetch receipt images from storage with names refund_req1.png through refund_req10.png,
    extract amounts from them, and update the corresponding rows in the refund_requests table.
    """
    # Define the bucket name
    bucket_name = "receipts"
    base_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}"
    
    print(f"Processing receipt images from {start_num} to {end_num}...")
    
    # Process each receipt image
    results = []
    for i in range(start_num, end_num + 1):
        image_name = f"refund_req{i}.png"
        image_url = f"{base_url}/{image_name}"
        print(f"Processing image {i}: {image_url}")
        
        try:
            # Extract amount from receipt
            amount = extract_amount_from_receipt(image_url)
            if amount is None:
                # Fallback: Try with a different URL construction pattern sometimes used in Supabase
                alternative_url = f"{SUPABASE_URL}/storage/v1/render/image/public/{bucket_name}/{image_name}"
                print(f"Trying alternative URL: {alternative_url}")
                amount = extract_amount_from_receipt(alternative_url)
                
                if amount is not None:
                    # If this works, update our image_url to this format
                    image_url = alternative_url
                    print(f"Alternative URL successful!")
                else:
                    results.append({
                        "id": i,
                        "image": image_name,
                        "status": "extraction_failed",
                        "amount": None,
                        "message": "Failed to extract amount from receipt with both URL patterns"
                    })
                    continue
            
            # Update the database row with the image URL and amount
            try:
                # Create update data
                update_data = {
                    'image_url': image_url,
                    'amount': amount
                }
                
                print(f"Updating row {i} with amount: {amount} and URL: {image_url}")
                
                # Try using direct database table update instead of SQL
                try:
                    # Update the corresponding row in refund_requests table
                    response = sb.table('refund_requests').update(update_data).eq('id', i).execute()
                    
                    if hasattr(response, 'error') and response.error:
                        print(f"Update error: {response.error}")
                        # Try an SQL fallback
                        sql_query = f"UPDATE refund_requests SET image_url = '{image_url}', amount = {amount} WHERE id = {i}"
                        sql_response = execute_sql_query(sql_query)
                        
                        if isinstance(sql_response, dict) and "error" in sql_response:
                            raise Exception(f"SQL fallback failed: {sql_response['error']}")
                        else:
                            print(f"SQL fallback succeeded for row {i}")
                    
                    if hasattr(response, 'data') and response.data:
                        print(f"✅ Updated row {i} with amount: {amount}")
                        results.append({
                            "id": i,
                            "image": image_name,
                            "status": "success",
                            "amount": amount,
                            "updated": True
                        })
                    else:
                        print(f"⚠️ Row {i} update returned no data")
                        # Check if the row exists
                        check_query = f"SELECT id FROM refund_requests WHERE id = {i}"
                        check_result = execute_sql_query(check_query)
                        
                        if isinstance(check_result, list) and len(check_result) > 0:
                            # Row exists but update didn't return data (common with some Supabase setups)
                            results.append({
                                "id": i,
                                "image": image_name,
                                "status": "likely_success",
                                "amount": amount,
                                "message": "No confirmation, but row exists and was likely updated"
                            })
                        else:
                            # Row doesn't exist, try to insert it
                            insert_data = {
                                'id': i,
                                'image_url': image_url,
                                'amount': amount
                            }
                            
                            insert_response = sb.table('refund_requests').insert(insert_data).execute()
                            if hasattr(insert_response, 'data') and insert_response.data:
                                print(f"✅ Inserted new row {i} with amount: {amount}")
                                results.append({
                                    "id": i,
                                    "image": image_name,
                                    "status": "success_insert",
                                    "amount": amount,
                                    "created": True
                                })
                            else:
                                results.append({
                                    "id": i,
                                    "image": image_name,
                                    "status": "db_update_failed",
                                    "amount": amount,
                                    "updated": False
                                })
                except Exception as table_error:
                    print(f"Table API error for row {i}: {str(table_error)}")
                    # Fallback to SQL
                    sql_query = f"UPDATE refund_requests SET image_url = '{image_url}', amount = {amount} WHERE id = {i}"
                    sql_response = execute_sql_query(sql_query)
                    
                    if isinstance(sql_response, dict) and "error" in sql_response:
                        raise Exception(f"SQL fallback failed: {sql_response['error']}")
                    else:
                        print(f"SQL fallback succeeded for row {i}")
                        results.append({
                            "id": i,
                            "image": image_name,
                            "status": "success_via_sql",
                            "amount": amount,
                            "updated": True
                        })
            except Exception as db_error:
                error_msg = str(db_error)
                print(f"Error updating row {i}: {error_msg}")
                results.append({
                    "id": i,
                    "image": image_name,
                    "status": "error",
                    "amount": amount if amount is not None else None,
                    "message": error_msg
                })
                
        except Exception as e:
            error_msg = str(e)
            print(f"Error processing image {i}: {error_msg}")
            results.append({
                "id": i,
                "image": image_name,
                "status": "error",
                "message": error_msg
            })
    
    print(f"Processed {len(results)} receipt images")
    return results

# ------------------------ Master Handler ------------------------ #

def handle_database_operations(user_input: str):
    """
    A simplified handler specifically for database operations.
    This works directly with SQL for all operations.
    """
    print("Fetching schema...")
    schema_data = get_supabase_schema_via_rest()
    if "error" in schema_data:
        print("Schema fetch error:", schema_data["error"])
        
        # If the error is related to empty data but status is success, try to proceed anyway
        if "status" in str(schema_data["error"]) and "success" in str(schema_data["error"]):
            print("Attempting to proceed with SQL generation despite schema error...")
            # Try a direct SQL approach without schema
            sql_query = nl_to_sql_gemini(user_input)
            if isinstance(sql_query, dict) and "error" in sql_query:
                return sql_query
            
            print("Generated SQL:", sql_query)
            return execute_sql_query(sql_query)
        
        # Otherwise return the error
        return schema_data
    
    print("Schema fetched successfully")
    sql_query = nl_to_sql_gemini(user_input)
    
    if isinstance(sql_query, dict) and "error" in sql_query:
        return sql_query

    print("Generated SQL:", sql_query)
    result = execute_sql_query(sql_query)
    return result

# Modified handle_request to include special command handling
def handle_request(user_input: str):
    """Main request handler"""
    # Check for audio summarization requests
    is_audio_summary_request = False
    if any(term in user_input.lower() for term in ["audio", "refund_aud", "refund audio"]) and any(term in user_input.lower() for term in ["summary", "summarize", "summarization", "what is being said", "content", "transcript"]):
        print("Audio summarization request detected")
        is_audio_summary_request = True
        # Get the audio URLs from the database
        query = "SELECT id, audio_url FROM refund_requests WHERE audio_url IS NOT NULL"
        query_result = execute_sql_query(query)
        
        if isinstance(query_result, list) and len(query_result) > 0:
            print(f"Found {len(query_result)} audio files to process")
            return handle_audio_request(query_result)
        else:
            return {"error": "No audio files found to process"}
    
    # Storage processing checks - if the user is asking to process receipt images from storage
    is_storage_process_request = False
    if any(term in user_input.lower() for term in ["storage", "image", "receipt", "refund_req", "png"]) and (
        "update" in user_input.lower() or "extract" in user_input.lower() or "process" in user_input.lower() or 
        "get info" in user_input.lower() or "read" in user_input.lower()
    ):
        # Look for patterns that indicate processing storage receipts and updating rows
        storage_pattern_1 = re.search(r"(get|extract|process).*?(image|storage|receipt).*?(update|set).*?row", user_input.lower())
        storage_pattern_2 = re.search(r"refund_req\d+\.png", user_input.lower())
        
        if storage_pattern_1 or storage_pattern_2:
            is_storage_process_request = True
            print("Special task detected: Processing receipt images from storage")
            
            # Extract start and end numbers if specified
            start_num = 1
            end_num = 10
            
            # Look for specific numbers
            start_match = re.search(r"refund_req(\d+)\.png", user_input)
            if start_match:
                start_num = int(start_match.group(1))
            
            # Look for "to" or "through" followed by a number
            end_match = re.search(r"(?:to|through|till)\s+(?:refund_req)?(\d+)", user_input)
            if end_match:
                end_num = int(end_match.group(1))
                
            print(f"Processing receipts {start_num} through {end_num}")
            return fetch_and_process_storage_receipts(start_num, end_num)
    
    # Count how many database keywords are in the input
    db_operation_keywords = ["insert", "update", "delete", "select", "add", "modify", 
                           "change", "remove", "get", "show", "list", "query", "find", 
                           "fetch", "set", "employee", "refund"]
    
    keyword_count = sum(1 for keyword in db_operation_keywords if keyword in user_input.lower())
    
    # If we detect this is likely a database operation and not an audio/image processing request
    # and not a storage processing request
    is_likely_db_op = keyword_count >= 2 and not is_audio_summary_request and not any(term in user_input.lower() for term in 
                                                   ["process audio", "transcribe", "summarize audio", 
                                                    "extract from receipt", "analyze image"]) and not is_storage_process_request
    
    if is_likely_db_op:
        print("Database operation detected, using optimized handler...")
        return handle_database_operations(user_input)
    
    # Special case for audio summaries/transcriptions - Kept for backward compatibility
    if not is_audio_summary_request and ("audio" in user_input.lower() or "refund_aud" in user_input.lower()) and any(term in user_input.lower() for term in ["summary", "summarize", "transcribe", "transcript", "what is being said"]):
        print("Audio summarization request detected (legacy path)")
        # Get the audio URLs from the database
        query = "SELECT id, audio_url FROM refund_requests WHERE audio_url IS NOT NULL"
        query_result = execute_sql_query(query)
        
        if isinstance(query_result, list) and len(query_result) > 0:
            print(f"Found {len(query_result)} audio files to process")
            return handle_audio_request(query_result)
        else:
            return {"error": "No audio files found to process"}
    
    # Special command to process storage receipts - older checks, keeping for compatibility
    if "get all the urls from the storage" in user_input.lower() and "refund_req" in user_input.lower() and "update the respective rows" in user_input.lower():
        # This is the exact task description
        print("Task detected: Fetching and processing receipt images from storage")
        return fetch_and_process_storage_receipts(1, 10)
    elif any(cmd in user_input.lower() for cmd in ["process all receipts", "update refund rows", "process storage"]):
        if "refund_req" in user_input and ("image" in user_input or "receipt" in user_input):
            # Extract start and end numbers if specified
            start_num = 1
            end_num = 10
            start_match = re.search(r"refund_req(\d+)", user_input)
            if start_match:
                start_num = int(start_match.group(1))
            
            # Look for "to" or "through" followed by a number or "refund_reqX"
            end_match = re.search(r"(?:to|through|till)\s+(?:refund_req)?(\d+)", user_input)
            if end_match:
                end_num = int(end_match.group(1))
            
            print(f"Special command detected: Processing receipts {start_num} through {end_num}")
            return fetch_and_process_storage_receipts(start_num, end_num)
    
    # Regular query processing
    print("Fetching schema...")
    schema_data = get_supabase_schema_via_rest()
    if "error" in schema_data:
        print("Schema fetch error:", schema_data["error"])
        
        # If the error is related to empty data but status is success, try to proceed anyway
        if "status" in str(schema_data["error"]) and "success" in str(schema_data["error"]):
            print("Attempting to proceed with SQL generation despite schema error...")
            # Try a direct SQL approach without schema
            sql_query = nl_to_sql_gemini(user_input)
            if isinstance(sql_query, str):
                print("Generated SQL:", sql_query)
                query_result = execute_sql_query(sql_query)
                
                # Process the result (same as below)
                is_audio_query = "audio" in user_input.lower() and isinstance(query_result, list) and len(query_result) > 0
                is_image_query = any(term in user_input.lower() for term in ["image", "receipt", "photo", "picture"]) and isinstance(query_result, list) and len(query_result) > 0
                
                # Handle audio URLs query
                if is_audio_query:
                    # Check if the user is asking for summaries (again) - ensure we don't miss the request
                    audio_summary_intent = any(term in user_input.lower() for term in [
                        "summary", "summarize", "transcribe", "transcript", "what is being said", "what's being said", "content"
                    ])
                    
                    if audio_summary_intent:
                        try:
                            print("Audio summary intent detected in results phase - processing audio files...")
                            return handle_audio_request(query_result)
                        finally:
                            # Ensure cleanup happens even if processing fails
                            cleanup_temp_files()
                    
                    # Check if the query is just about getting URLs
                    just_get_urls = any(term in user_input.lower() for term in [
                        "get", "fetch", "show", "list", "display", "give me", "return"
                    ]) and (
                        "url" in user_input.lower() or 
                        "link" in user_input.lower()
                    ) and not any(term in user_input.lower() for term in [
                        "summary", "summarize", "transcribe", "transcript", "what is being said"
                    ])
                    
                    # Check if the user specifically wants to process the audio
                    process_audio = any(term in user_input.lower() for term in [
                        "process", "transcribe", "summarize", "analyze", "convert", "summary", 
                        "what is being said", "content", "transcript"
                    ])
                    
                    # Process audio if explicitly requested or if both conditions are met
                    if process_audio or not just_get_urls:
                        try:
                            print("Processing audio files as requested...")
                            return handle_audio_request(query_result)
                        finally:
                            # Ensure cleanup happens even if processing fails
                            cleanup_temp_files()
                    else:
                        # User just wants the URLs
                        print("Returning audio URLs without processing.")
                        return query_result
                
                # Handle image/receipt processing
                elif is_image_query:
                    # Process images (same logic as below)
                    # Check if the query is just about getting URLs
                    just_get_urls = any(term in user_input.lower() for term in [
                        "get", "fetch", "show", "list", "display", "give me", "return"
                    ]) and (
                        "url" in user_input.lower() or 
                        "link" in user_input.lower() or
                        "image" in user_input.lower()
                    )
                    
                    # Check if the user specifically wants to process the images
                    process_images = any(term in user_input.lower() for term in [
                        "process", "extract", "analyze", "amount", "total", "scan"
                    ])
                    
                    # Process images only if explicitly requested or if neither is specified
                    if process_images and not just_get_urls:
                        print("Processing receipt images as requested...")
                        return handle_image_request(query_result)
                    else:
                        # User likely just wants the URLs
                        print("Returning image URLs without processing.")
                        return query_result
                
                return query_result
            else:
                return sql_query
        
        # Otherwise return the error
        return schema_data
    
    print("Schema fetched successfully")
    result = nl_to_sql_gemini(user_input)
    
    if isinstance(result, str):
        print("Generated SQL:", result)
        query_result = execute_sql_query(result)
        
        # Determine if this is an audio or image processing query
        is_audio_query = "audio" in user_input.lower() and isinstance(query_result, list) and len(query_result) > 0
        is_image_query = any(term in user_input.lower() for term in ["image", "receipt", "photo", "picture"]) and isinstance(query_result, list) and len(query_result) > 0
        
        # Handle audio URLs query
        if is_audio_query:
            # Check if the user is asking for summaries (again) - ensure we don't miss the request
            audio_summary_intent = any(term in user_input.lower() for term in [
                "summary", "summarize", "transcribe", "transcript", "what is being said", "what's being said", "content"
            ])
            
            if audio_summary_intent:
                try:
                    print("Audio summary intent detected in results phase - processing audio files...")
                    return handle_audio_request(query_result)
                finally:
                    # Ensure cleanup happens even if processing fails
                    cleanup_temp_files()
                    
            # Check if the query is just about getting URLs
            just_get_urls = any(term in user_input.lower() for term in [
                "get", "fetch", "show", "list", "display", "give me", "return"
            ]) and (
                "url" in user_input.lower() or 
                "link" in user_input.lower()
            ) and not any(term in user_input.lower() for term in [
                "summary", "summarize", "transcribe", "transcript", "what is being said"
            ])
            
            # Check if the user specifically wants to process the audio
            process_audio = any(term in user_input.lower() for term in [
                "process", "transcribe", "summarize", "analyze", "convert", "summary", 
                "what is being said", "content", "transcript"
            ])
            
            # Process audio if explicitly requested or if both conditions are met
            if process_audio or not just_get_urls:
                try:
                    print("Processing audio files as requested...")
                    return handle_audio_request(query_result)
                finally:
                    # Ensure cleanup happens even if processing fails
                    cleanup_temp_files()
            else:
                # User just wants the URLs
                print("Returning audio URLs without processing.")
                return query_result
        
        # Handle image/receipt processing
        elif is_image_query:
            # Check if the query is just about getting URLs
            just_get_urls = any(term in user_input.lower() for term in [
                "get", "fetch", "show", "list", "display", "give me", "return"
            ]) and (
                "url" in user_input.lower() or 
                "link" in user_input.lower() or
                "image" in user_input.lower()
            )
            
            # Check if the user specifically wants to process the images
            process_images = any(term in user_input.lower() for term in [
                "process", "extract", "analyze", "amount", "total", "scan"
            ])
            
            # Process images only if explicitly requested or if neither is specified
            if process_images and not just_get_urls:
                print("Processing receipt images as requested...")
                return handle_image_request(query_result)
            else:
                # User likely just wants the URLs
                print("Returning image URLs without processing.")
                return query_result
                
        return query_result
    else:
        return result

# ------------------------ Entry Point --------------------------- #

if __name__ == "__main__":
    print("🤖 Database and Audio Agent is ready!")
    print("Type 'exit' or 'quit' to end the session")
    
    # Setup FFmpeg for Windows compatibility
    setup_ffmpeg()
    
    while True:
        user_input = input("\n💬 Ask a question about your database (or 'exit' to quit): ")
        if user_input.lower() == "exit":
            print("👋 Exiting. Goodbye!")
            break

        response = handle_request(user_input)
        print("\n📊 Response:\n", response)
