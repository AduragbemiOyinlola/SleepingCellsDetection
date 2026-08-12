# SleepGuard — Sleeping Cell Detector

A Streamlit app that automates detection of "sleeping cells" (cell sites reporting healthy availability while carrying little or no real traffic) in a telecom network. It walks through a 5-step pipeline: connect to a mailbox, fetch the daily alert email, pull KPI data from the NMS, generate diagnostic plots, classify each cell with a CNN, and email out a report of confirmed sleeping cells.

## Pipeline

1. **Email Setup** — connect a Gmail/Outlook account (OAuth or IMAP), or use demo mode.
2. **Fetch Alert Email** — scan the inbox for the sleeping-cell alert and extract the attached CSV of suspected sites (or upload a CSV directly).
3. **KPI Retrieval** — pull `availability`, `cs_traffic`, and `ps_traffic` per site from the NMS over the observation window.
4. **Plots & Classification** — render availability-vs-traffic plots and classify each one with a fine-tuned ResNet (availability high + traffic collapsed → sleeping).
5. **Report & Delivery** — compile confirmed sleeping cells into a CSV and email it to the NOC team.

## Project structure

```
app.py              Streamlit entry point (auth gate + routing)
pages/dashboard.py  5-step pipeline UI
models/classifier.py  ResNet-based sleeping-cell classifier (+ mock mode)
models/train.py       Grouped 5-fold CV training script
utils/                Auth, email (IMAP/Graph), NMS client, plotting, reporting, config
Dataset_clean/         train/val/test image sets (healthy/ sleeping/)
Sleeping-Cell-KPI-Data/  Raw KPI spreadsheets used to build the dataset
```

## Setup

```bash
pip install streamlit torch torchvision pandas numpy scikit-learn pillow python-dotenv msal
streamlit run app.py
```

Configure via a `.env` file (see `utils/config.py` for the full list):

| Variable | Purpose |
|---|---|
| `AUTH_MODE` | `DEMO` or `OAUTH` login |
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` | Google OAuth for sign-in / Gmail API |
| `MS_CLIENT_ID` / `MS_TENANT` / `MS_CLIENT_SECRET` | Microsoft Graph app registration for Outlook |
| `NMS_MOCK` | `1` to use synthetic KPI data instead of a real NMS |
| `NMS_BASE_URL` / `NMS_API_KEY` | Real NMS endpoint + key |
| `MODEL_MOCK` | `1` to classify with a rule-based mock instead of a trained model |
| `MODEL_WEIGHTS` | Path to a trained `.pt` state dict |
| `DECISION_THRESHOLD` | Sigmoid cutoff for the sleeping label |

By default `NMS_MOCK=1` and `MODEL_MOCK=1`, so the whole pipeline runs end-to-end with synthetic data and no trained weights required — good for demoing the UI.

## Training the classifier

```bash
python models/train.py --data_dir Dataset_clean --arch resnet18 --n_splits 5 --epochs 30
```

Runs a leak-safe, grouped 5-fold stratified cross-validation (images grouped by cell ID and by rendered content hash so no cell can span a train/test split), saving per-fold weights and a pooled out-of-fold report to `models/weights/`.
