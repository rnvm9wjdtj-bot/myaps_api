# MyAPS FastAPI Project

A simple FastAPI project template with a Python virtual environment.

## Project Structure

```
myaps_fastapi/
├── venv/              # Python virtual environment
├── main.py            # Main FastAPI application
├── requirements.txt   # Project dependencies
├── .gitignore         # Git ignore file
└── README.md          # Project documentation
```

## Getting Started

### 1. Activate the Virtual Environment

**Windows:**
```cmd
venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 2. Install Dependencies

```cmd
pip install -r requirements.txt
```

### 3. Run the FastAPI Server

```cmd
uvicorn main:app --reload
```

### 4. Access the API

- Open your browser and go to [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Swagger UI documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc documentation: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

## API Endpoints

- `GET /` - Root endpoint with welcome message
- `GET /api/info` - Project information

## Features

- FastAPI framework for high-performance API development
- Automatic interactive API documentation
- Python virtual environment for dependency isolation
- Git integration with proper ignore rules

## Requirements

- Python 3.7+","}}}