# AKI Prediction Backend

FastAPI service wrapping the trained Voting ensemble.

## Run

```bash
# from project root
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | Service + model status |
| GET  | `/api/features` | 35 feature names, medians, timing |
| POST | `/api/predict` | Single patient `{features: {...}}` → prob + SHAP |
| POST | `/api/predict/batch` | List of feature dicts |
| POST | `/api/predict/csv` | CSV upload → CSV download |
| POST | `/api/report/pdf` | Same payload as predict → PDF |
| GET  | `/api/performance` | Model metrics from outputs/tables |

The SHAP explainer uses the XGBoost sub-estimator extracted from the Voting
ensemble, so it works even when `models/*.pkl` are unresolved Git-LFS pointers.
