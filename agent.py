import requests
from supabase import create_client, Client
import re

# Initialize Supabase config
SUPABASE_URL = "https://advfymskrwzncvmlgrxz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdmZ5bXNrcnd6bmN2bWxncnh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNTk2ODAsImV4cCI6MjA2MDYzNTY4MH0.rLWsbtWRwfah1q_EXB86QFYABXO_j53PnjNITeGmPcc"

# Gemini API config
GEMINI_API_KEY = "AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

# Create Supabase client
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------- Query Helpers ---------------------------- #
def get_supabase_schema_via_rest():
    try:
        response = sb.rpc("get_table_schema").execute()
       
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
            return {"error": "No data returned from get_table_schema()"}
    except Exception as e:
        return {"error": f"Exception occurred while fetching schema: {str(e)}"}



def execute_sql_query(query: str):
    """
    Executes an SQL query using Supabase and returns the results.
    """
    try:
        query = query.strip().rstrip(';')  # Remove the semicolon
        print(f"Executing SQL Query: {query}")  # Debugging line
        # response = sb.rpc('run_sql', {'sql_query': query}).execute()
        response = sb.rpc("run_sql_query", {"sql_query": query}).execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}



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
    headers = {
        "Content-Type": "application/json"
    }

    # Get and format schema
    schema_data = get_supabase_schema_via_rest()
    if "error" in schema_data:
        return {"error": "Failed to fetch schema from Supabase."}
    
    schema_description = format_schema_for_prompt(schema_data)

    # Construct refined prompt
    refined_prompt = (
        f"{schema_description}\n\n"
        f"Now, based on the above schema, generate an SQL query for: {prompt}.\n"
        f"Return only the SQL query without any explanation or markdown formatting."
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
            sql_match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL)
            return sql_match.group(1).strip() if sql_match else text.strip()
        else:
            return {"error": "No candidates returned by Gemini."}
    else:
        return {"error": response.text}

# ------------------------ Master Handler ------------------------ #

def handle_request(user_input: str):
    sql_query = nl_to_sql_gemini(user_input)
    
    if "error" in sql_query:
        return sql_query

    print("Generated SQL:", sql_query)
    result = execute_sql_query(sql_query)
    return result

# ------------------------ Entry Point --------------------------- #

if __name__ == "__main__":
    while True:
        user_input = input("\n💬 Ask a question about your database (or 'exit' to quit): ")
        if user_input.lower() == "exit":
            print("👋 Exiting. Goodbye!")
            break

        response = handle_request(user_input)
        print("\n📊 Response:\n", response)
