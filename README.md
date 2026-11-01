# Student Mental Health Predictor — MindScore

A browser-based mental health assessment tool trained on 5,000 student records, paired with an AI-powered support chat backed by a Python/FastAPI backend.

---

## Features

- **Predictive Assessment** — A compressed random forest (40 trees) runs entirely in the browser. Enter 12 daily-habit variables and receive a mental health score (1–10) with a live histogram showing your position across the dataset.
- **What Would Change It** — Estimated score delta for single-variable adjustments (sleep, social media use, physical activity, etc.).
- **Dataset Insights** — Four charts revealing how social media usage, sleep duration, perceived stress, and platform choice correlate with average mental health scores across the 5,000-student dataset.
- **AI Support Chat** — Powered by the Groq LLM (`qwen/qwen3-27b`) with live DuckDuckGo web search for up-to-date, evidence-based answers. Includes crisis detection with emergency resource links.
- **Nearby Clinics** — Uses the browser Geolocation API + OpenStreetMap Overpass to surface licensed psychologists, counsellors, and clinics within 15 km.

---

## Project Structure

```
health pred/
├── Student Mental Health Predictor.html   # Main single-page app
├── Student Mental Health Predictor.css    # All styles and design tokens
├── Student Mental Health Predictor.js     # In-browser ML model + charts + UI logic
├── rag_chat.js                            # AI chat + nearby clinics frontend logic
├── rag_engine.py                          # FastAPI backend (chat API, nearby doctors)
├── requirements.txt                       # Python dependencies
├── Mental_Health_Model.pkl                # Trained scikit-learn model (reference)
└── Student Social Media And Mental Health Impact.csv  # Source dataset (5,000 records)
```

---

## Quick Start

### 1. Open without AI chat (no server needed)

Simply open `Student Mental Health Predictor.html` directly in any modern browser. The predictive assessment, charts, and insights all run fully client-side — no server or API key required.

### 2. Enable the AI Support Chat

The chat panel requires the FastAPI backend to be running.

#### Prerequisites

- Python 3.10 or later
- A free [Groq API key](https://console.groq.com/)

#### Install dependencies

```bash
pip install -r requirements.txt
```

#### Configure environment

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

#### Start the server

```bash
python -m uvicorn rag_engine:app --host 127.0.0.1 --port 8000
```

Then open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser. The server serves the HTML page and all static assets directly.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the main HTML app |
| `POST` | `/api/chat` | AI chat — accepts `{"message": "..."}`, returns `{answer, sources, urgent}` |
| `POST` | `/api/doctors` | Nearby clinics — accepts `{latitude, longitude, radius_m}`, returns up to 25 providers sorted by distance |
| `GET` | `/{asset}` | Serves CSS and JS static files |

---

## Model Details

| Property | Value |
|----------|-------|
| Algorithm | Random Forest Regressor — 100 decision trees (40 used in browser) |
| Target | Mental health score, continuous 1–10 |
| Training data | 5,000 student records |
| In-sample R² | 0.95 |
| Mean Absolute Error | 0.19 points |
| Browser vs. full model | Within 0.04 points on average |

**Input variables (12):** daily social media hours, sleep duration, phone unlocks per day, study hours, physical activity hours, age, perceived stress level, gender, academic level, primary platform, primary use, country of study.

**Feature importance (top):** Daily social media hours (67.5%) · Sleep per night (11.1%) · Phone unlocks (4.7%)

---

## Dataset

`Student Social Media And Mental Health Impact.csv` — 5,000 anonymised student survey responses. Social media usage correlates negatively with well-being (r = −0.82); sleep duration shows a strong positive association.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla HTML/CSS/JavaScript (no framework) |
| ML inference | Compressed random forest serialised to base64, runs in-browser via TypedArrays |
| Backend | Python · FastAPI · Uvicorn |
| LLM | Groq API (`qwen/qwen3-27b`) |
| Web search | DuckDuckGo (`ddgs`) — no API key required |
| Nearby search | OpenStreetMap Overpass API + browser Geolocation |
| Model training | scikit-learn `RandomForestRegressor` |

---

## Disclaimer

This tool provides a statistical estimate derived from survey data and is **not** a clinical diagnostic instrument or psychological screening tool. The accuracy metric is measured on the training dataset and may not reflect real-world performance. If you or someone you know is experiencing persistent mental health difficulties, please consult a qualified healthcare professional or licensed counsellor.

**Emergency:** This tool is not a crisis service. If you are in immediate danger, contact your local emergency services. In the United States or Canada, call or text **988**.
