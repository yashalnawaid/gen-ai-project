# Database and Audio Agent

A powerful agent that can interact with a Supabase database, process audio files for transcription and summarization, and analyze receipt images to extract totals.

## Features

- **Natural Language to SQL**: Convert natural language queries into SQL for Supabase
- **Audio Processing**: Transcribe and summarize audio files from URLs
- **Receipt Analysis**: Extract total amounts from receipt images
- **Windows Compatibility**: Enhanced FFmpeg handling for Windows environments

## Setup

### Prerequisites

- Python 3.8+
- FFmpeg (automatically downloaded on Windows if not present)
- Supabase account and API credentials
- Gemini API key

### Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd gen-ai-project-main
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Configure environment variables (create a `.env` file):
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   GEMINI_API_KEY=your_gemini_api_key
   ```

## Usage

Run the agent:
```
python agent.py
```

### Database Queries

The agent can handle various database operations:

```
> Ask a question about your database: Show me all employees with salary greater than 50000
> Ask a question about your database: Insert a new employee named John Doe with salary 75000
> Ask a question about your database: Update the salary for employee with id 5 to 80000
> Ask a question about your database: Delete employee with id 10
```

### Audio Processing

Process audio files stored in your Supabase storage:

```
> Ask a question about your database: Get all audio URLs from refunds and give me a summary of what is being said in each audio
> Ask a question about your database: Transcribe the audio in row 5 of the refund_requests table
```

### Receipt Processing

Process receipt images and extract total amounts:

```
> Ask a question about your database: Get all the urls from the storage, the names are refund_req1.png through refund_req10.png. Then read/get info from the image and get the total written in the receipt. Update the respective rows in the refunds table with the image_url and the amount in the image
```

## Error Handling

The agent includes robust error handling for:
- Database connection issues
- Audio file download and processing failures
- FFmpeg configuration problems on different platforms
- Image processing errors

## Schema

The application assumes a Supabase database with tables like:
- `employees` (id, name, salary, etc.)
- `refund_requests` (id, amount, image_url, audio_url, etc.)

## Technical Details

### Components

1. **Database Interface**: Uses Supabase Python client to execute SQL and table operations
2. **AI Models**:
   - Uses Gemini API for natural language processing and summarization
   - Uses OpenAI Whisper for audio transcription
3. **Media Processing**:
   - Uses FFmpeg for audio processing
   - Uses Gemini Vision for receipt image analysis

### Architecture

- The application follows a modular design with specialized functions for each capability
- Uses direct table API operations for data manipulation when possible
- Falls back to SQL for complex operations
- Includes specialized detection for audio, image, and database operations

## Troubleshooting

### FFmpeg Issues
If you encounter issues with audio transcription:
- Windows: The application will attempt to download and configure FFmpeg automatically
- Other platforms: Install FFmpeg using your package manager

### Database Connection
If database operations fail:
- Verify your Supabase URL and API key
- Check network connectivity
- Ensure the database schema matches expected tables and columns


 
