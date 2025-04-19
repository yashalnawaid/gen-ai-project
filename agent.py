import requests
from supabase import create_client, Client
import re

# Initialize the Supabase client
SUPABASE_URL = "https://advfymskrwzncvmlgrxz.supabase.co" 
SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFkdmZ5bXNrcnd6bmN2bWxncnh6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUwNTk2ODAsImV4cCI6MjA2MDYzNTY4MH0.rLWsbtWRwfah1q_EXB86QFYABXO_j53PnjNITeGmPcc"
SUPABASE_DB_URL="postgresql://postgres:[9Or3oYvHFXKDZmHS]@db.advfymskrwzncvmlgrxz.supabase.co:5432/postgres"


# Initialize Gemini API configuration
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ" 
GEMINI_API_KEY = "AIzaSyA8eFP7AB8OopYbcGcjPCO1Adp-WGovVPQ"

# Initialize the Supabase client
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def execute_sql_query(query: str):
    """
    Executes an SQL query using Supabase and returns the results.
    """
    try:
        # For SELECT queries, use the from_() method
        if query.strip().upper().startswith('SELECT'):
            # Extract table name from the query (this is a simple approach and might not work for complex queries)
            table_match = re.search(r'FROM\s+([^\s;]+)', query, re.IGNORECASE)
            if table_match:
                table_name = table_match.group(1)
                # Use the Supabase client's from_() method
                response = sb.from_(table_name).select('*').execute()
                return response.data
            else:
                return {"error": "Could not parse table name from query"}
        else:
            # For other queries, use the rpc method
            response = sb.rpc('run_sql', {'sql_query': query}).execute()
            return response.data
    except Exception as e:
        return {"error": str(e)}

def nl_to_sql_gemini(prompt: str):
    """
    Converts a natural language prompt into an SQL query using the Gemini API.
    """
    headers = {
        "Content-Type": "application/json"
    }

    # Refine the prompt for better context
    refined_prompt = f"Generate an SQL query for the following request: {prompt}. Return only the SQL query without any explanation or markdown formatting."

    payload = {
        "contents": [{
            "parts": [{"text": refined_prompt}]
        }]
    }

    # Log the refined prompt, payload, and headers
    print("Refined prompt:", refined_prompt)
    print("Sending request to Gemini API with payload:", payload)
    print("Headers:", headers)

    # Send the request to Gemini API to convert natural language to SQL
    response = requests.post(GEMINI_API_URL, json=payload, headers=headers)

    # Log the response status code
    print("Response status code:", response.status_code)

    if response.status_code == 200:
        data = response.json()
        # Log the response data
        print("Response data:", data)
        
        # Extract the SQL query from the response
        candidates = data.get('candidates', [])
        if candidates:
            # Get the text from the response
            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
            
            # Extract just the SQL query from the text
            # This will handle cases where the response includes markdown code blocks
            sql_match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL)
            if sql_match:
                sql_query = sql_match.group(1).strip()
            else:
                # If no code block, try to extract the SQL directly
                sql_query = text.strip()
            
            return sql_query
        else:
            return {"error": "No candidates found in response"}
    else:
        # Log the error response
        print("Error response:", response.text)
        return {"error": "Failed to convert prompt to SQL"}

def handle_request(user_input: str):
    """
    Handles the user input: converts natural language to SQL and fetches results.
    """
    # Step 1: Convert the user's natural language input to an SQL query
    sql_query = nl_to_sql_gemini(user_input)
    
    if "error" in sql_query:
        return sql_query
    print(sql_query, "sql_query yashallll")
    # Step 2: Execute the SQL query
    result = execute_sql_query(sql_query)
    
    # Step 3: Return the result
    return result

# Example usage
if __name__ == "__main__":
    while True:
        # Take user input for the query
        user_input = input("Enter your query (or 'exit' to quit): ")
        
        # Check if user wants to exit
        if user_input.lower() == 'exit':
            print("Goodbye!")
            break
            
        result = handle_request(user_input)
        print(result)
