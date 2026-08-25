# 📚 Booktures

> Booktures is a local AI-driven book illustration platform that extracts narrative context from PDFs and generates consistent, scene-aware visuals.

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React-Frontend-61DAFB?style=for-the-badge&logo=react)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-316192?style=for-the-badge&logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker)

---

# ✨ Project Summary

Booktures processes uploaded books and PDFs to build a narrative illustration pipeline with the following capabilities:

- Extracts text and chunks pages from PDF files
- Detects characters and builds stable visual profiles
- Generates per-page summaries and image prompts
- Produces illustrations using local diffusion models
- Tracks progress and status with a background job queue
- Serves generated assets through a FastAPI backend

This repository contains a local development implementation, including a React frontend and a Python backend.

---

# 🚀 Key Features

- 📄 PDF upload and text extraction
- 🧠 AI-assisted page summarization
- 🎭 Character consistency across pages
- 🖼️ Image prompt generation
- 🧵 Background job queue for book processing + image generation
- 🗂️ Static asset hosting via FastAPI
- 🧪 Modern React UI with data fetching via React Query
- 🐳 Local Dockerized PostgreSQL with pgvector support

---

# 🏗️ Architecture

## Backend

- `backend/main.py` — FastAPI app, DB initialization, and worker startup
- `backend/api/routes.py` — REST endpoints for books, jobs, settings, and content
- `backend/database.py` — SQLAlchemy engine, session management, and database creation
- `backend/models/` — DB schemas for books, pages, characters, jobs, and page assets
- `backend/services/` — PDF extraction, prompt generation, character analysis, image rendering, and job processing

## Frontend

- `frontend/src/App.tsx` — routes and app shell
- `frontend/src/pages/` — UI pages for library, jobs, settings, and book viewer
- `frontend/src/services/` — API clients for books, jobs, settings, and characters
- `frontend/src/lib/api.ts` — shared API exports and error handling

---

# 📂 Repository Layout

```text
booktures/
├── backend/
│   ├── api/
│   ├── models/
│   ├── services/
│   ├── database.py
│   ├── docker-compose.yml
│   ├── main.py
│   └── ...
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── ...
├── requirements.txt
└── README.md
```

---

# ⚙️ Local Setup

## Prerequisites

- Python 3.11+
- Node.js 18+ / npm
- Docker Desktop
- Git

## 1. Clone the repository

```bash
git clone https://github.com/your-username/booktures.git
cd booktures
```

## 2. Start PostgreSQL with Docker

The repository includes `backend/docker-compose.yml` for a PostgreSQL container with pgvector support.

```bash
cd backend
docker compose up -d
```

Confirm the database is running:

```bash
docker ps
```

## 3. Create the pgvector extension

```bash
docker exec -it booktures_db psql -U postgres -d booktures
CREATE EXTENSION IF NOT EXISTS vector;
```

---

# 🔌 Backend Environment

Copy `backend/.env.example` to `backend/.env` and set your own `DATABASE_URL` / `POSTGRES_PASSWORD` (required — the app no longer falls back to a hardcoded password).

> Note: The code currently uses Ollama for text and prompt generation, and Diffusers for local image generation.

---

# ▶️ Run the Backend

From the repository root:

```bash
conda create -n booktures python=3.11
conda activate booktures

pip install -r requirements.txt   # full local dev (API + GPU inference stack)
# or for a lean cloud/API-only install:
# pip install -r backend/requirements-api.txt
cd backend
alembic upgrade head
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API docs are available at:

```text
http://127.0.0.1:8000/docs
```

---

# 💻 Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

---

# 🔧 Primary API Endpoints

- `GET /books` — list uploaded books
- `POST /upload-pdf` — upload a PDF/image and queue book processing
- `GET /books/{book_id}` — book metadata
- `GET /books/{book_id}/content` — extracted pages, summaries, scene metadata, and illustration URLs
- `GET /books/{book_id}/characters` — extracted characters and visual profiles
- `POST /books/{book_id}/generate-images` — queue image generation for a book
- `GET /jobs` — list background jobs and statuses
- `POST /jobs/{job_id}/action` — manage queued jobs (`cancel`, `pause`, `resume`, `retry`)
- `GET /settings` — current AI settings
- `GET /settings/ollama-models` — available Ollama models

---

# 🧠 Data Flow

1. Upload a PDF through the frontend
2. Backend saves the file in `storage/pdfs`
3. A `book_pipeline` job extracts page text and creates `DocumentChunk` records
4. Character service identifies characters and builds a visual bible
5. Prompt service generates page summaries and image prompts
6. `image_generation` jobs render illustrations via Diffusers
7. Generated images are stored under `storage/illustrations`

---

# 🛠️ Notes

- The backend automatically mounts `storage/` to serve uploaded PDFs and generated images.
- The job worker runs in a background thread and polls for queued jobs.
- `backend/services/image_generation_service.py` uses `diffusers.DiffusionPipeline`, optionally with CUDA.
- `backend/services/pdf_service.py` uses `pdfplumber`, OCR, and Ollama-powered text cleanup.

---

# 🐳 Docker Shortcuts

Stop the database container:

```bash
docker compose down
```

Reset the database data:

```bash
docker compose down -v
```

View container logs:

```bash
docker compose logs -f
```

---

# 📌 Important

This README reflects the repository codebase and local dev flow. It removes outdated references to Supabase/Gemini and instead documents the current Ollama + Diffusers-based implementation.


```bash
docker logs booktures_db
```

---

# 📸 Future Improvements

- Multi-character interaction consistency
- Fine-tuned illustration pipelines
- Story timeline visualization
- Chapter-wise image galleries
- Multi-language support
- Cloud deployment
- Real-time collaborative reading

---

# 🤝 Contributing

Contributions, ideas, and improvements are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Open a pull request

---

# 📄 License

This project is currently intended for educational and research purposes.

---

# 👨‍💻 Author

Developed by Pratik

---

# ⭐ Acknowledgements

Special thanks to the open-source AI and developer community for the tools and frameworks powering this project.

