# SleepGuard — Technical Report

**System:** Automated Sleeping Cell Detection Platform
**Report scope:** Full project — application architecture, data pipeline, computer-vision model, training methodology, and evaluation
**Stack:** Python 3.12, Streamlit, PyTorch / torchvision, scikit-learn, pandas, matplotlib

---

## 1. Executive Summary

SleepGuard is a Streamlit web application that automates the detection of "sleeping cells" in a telecom network — cells that report high availability but have silently stopped carrying traffic. The system executes a five-step pipeline: (1) authenticate and connect a corporate mailbox, (2) fetch the daily alert email and extract a CSV of suspected sites, (3) retrieve KPI time series for each site from the Network Management System (NMS), (4) render diagnostic plots and classify them with a fine-tuned ResNet-18 computer-vision model, and (5) compile and dispatch a confirmed-sleeping-cells report.

The core technical contribution documented here is the CV classifier and its supporting data pipeline. The original training dataset and evaluation methodology were found, through systematic investigation, to contain multiple sources of information leakage and a critical train/inference format mismatch. Both were diagnosed and corrected; the current model is evaluated with 5-fold grouped stratified cross-validation and verified against real KPI data end-to-end through the production plot-generation path.

---

## 2. System Architecture

### 2.1 Component overview

| Layer | Module(s) | Responsibility |
|---|---|---|
| Entry point | `app.py` | Streamlit page config, global styling, auth-gated routing |
| Auth & session | `utils/auth.py`, `utils/sso.py`, `utils/provider_detect.py` | Login (demo / unified OAuth), session-state initialisation |
| Email integration | `utils/email_client.py`, `scripts/get_outlook_token.py` | Gmail REST API / Microsoft Graph — fetch alert email, send report |
| KPI retrieval | `utils/nms_client.py` | NMS API client (mock + real), CSV site-list parsing |
| Plot generation | `utils/plotter.py` | Renders diagnostic dual-axis line charts consumed by the classifier |
| CV model | `models/classifier.py`, `models/train.py` | ResNet-18/50 wrapper, batch classification, training/CV pipeline |
| Reporting | `utils/reporter.py` | Compiles confirmed-sleeping-cells CSV |
| UI orchestration | `pages/dashboard.py`, `utils/styles.py` | Five-step pipeline UI, session-state wiring, theming |
| Configuration | `utils/config.py` | Central config, environment-variable driven with safe defaults |

### 2.2 Entry point and routing

`app.py` sets Streamlit page config, injects global CSS (`utils.styles.inject_global_styles`), initialises `st.session_state` defaults (`utils.auth.init_session`), and routes to either the login page or the dashboard based on `is_authenticated()`. The dashboard module is imported lazily, inside the authenticated branch, so unauthenticated users never load pipeline code.

### 2.3 Pipeline state machine

`pages/dashboard.py` drives a five-step linear pipeline, tracked via `st.session_state["pipeline_step"]` (0–5) and rendered as nested `st.expander` panels, each gated on the previous step's session-state output being present:

1. **Email Setup** (`_render_step1`) — connect mailbox (Gmail/Outlook) or activate demo mode.
2. **Fetch Email** (`_render_step2`) — search inbox by subject keyword, extract CSV attachment, or accept a manual CSV upload.
3. **KPI Retrieval** (`_render_step3`) — call `fetch_kpi_data()` for every parsed site.
4. **Plots & Classification** (`_render_step4`) — call `generate_all_plots()` then `classify_plots()`.
5. **Report & Delivery** (`_render_step5`) — `build_report_csv()`, download button, optional email dispatch.

A `pipeline_log` list accumulates timestamped, HTML-escaped status lines rendered in a collapsible "System Log" panel at the bottom of the page.

---

## 3. Authentication & Session Management

`utils/auth.py` supports two modes via `AUTH_MODE` (`config.py`):

- **DEMO** — hardcoded credential list (`DEMO_USERS`), SHA-256 password hashing compared with `hmac.compare_digest` (timing-safe).
- **OAUTH** — delegates to `utils/sso.py`'s unified sign-in flow.

`init_session()` seeds every session-state key the rest of the app depends on (`user`, `kpi_data`, `plots`, `classifications`, `pipeline_step`, etc.), preventing `KeyError`s on first render.

### 3.1 Unified OAuth sign-in (`utils/sso.py`)

A single email-address input drives provider detection (`utils/provider_detect.py`) and redirects straight into that provider's OAuth consent — one consent both authenticates the user and authorises mailbox access. Notable design points:

- **Cross-reload state**: the OAuth redirect is a full page reload, which clears `st.session_state`. Flow state (`state` → `{provider, ms_flow}`) is therefore kept in a module-level dict (`_OAUTH_CACHE`) that survives in the Streamlit server process, keyed by the OAuth `state` parameter.
- **Token refresh**: refresh material (Google's authorized-user JSON; MSAL's serializable token cache) is persisted in `st.session_state` (not a module global, since module globals reset on Streamlit's file-watcher re-import). `utils/email_client.py` calls back into a registered refresher (`set_token_refresher`) on any HTTP 401, retrying once with a fresh token.
- **Scope verification**: both `_google_exchange` and `_ms_exchange` explicitly verify the granted OAuth scopes include mailbox read access (`gmail.readonly` / `Mail.Read`) and raise a descriptive error if the provider granted sign-in but not mail access — a common OAuth-app misconfiguration.

### 3.2 Provider detection (`utils/provider_detect.py`)

Three-tier strategy, each tier only invoked if the previous one is inconclusive:

1. Static consumer-domain tables (`gmail.com`, `outlook.com`, `hotmail.com`, etc.) — no network call.
2. MX-record lookup (via optional `dnspython`) — classifies by MX host suffix, covering Google Workspace / M365 custom domains.
3. Microsoft-tenant backstop — probes `https://login.microsoftonline.com/{domain}/v2.0/.well-known/openid-configuration`; a 200 response indicates a managed/federated M365 tenant even when MX points to a third-party spam filter (Proofpoint, Mimecast, etc.).

---

## 4. Email Integration

`utils/email_client.py` unifies Gmail and Outlook behind one interface (`connect_imap`, `fetch_sleeping_cell_email`, `send_report_email`), routed by `_provider()` (session-state-backed, falling back to `config.EMAIL_PROVIDER`). Both providers are called via `requests` directly rather than provider SDKs, specifically avoiding `google-api-python-client`'s `httplib2` dependency, which was found to fail under proxy/DNS configurations that plain `requests` handles correctly.

- **Outlook / Microsoft Graph** (`_graph_fetch`): lists the newest `EMAIL_MAX_SCAN` messages via `$orderby=receivedDateTime desc` and filters by subject client-side (`keyword.lower() in subject.lower()`), deliberately avoiding Graph's `$search` (which requires an extra consistency header and has KQL encoding quirks).
- **Gmail** (`_gmail_fetch`): uses the Gmail API's native `subject:"{keyword}" in:inbox` query. The keyword is lower-cased before being interpolated into the query string (`keyword = keyword.lower()`) so subject matching is case-insensitive on both provider paths — this was a corrected defect; the Gmail path previously passed the raw, unlowered keyword.

CSV attachment extraction handles both providers' distinct payload shapes: Graph returns base64 `contentBytes` on a `/attachments` sub-resource; Gmail requires walking the MIME `parts` tree (`_gmail_walk`) and, for large attachments, a follow-up call to fetch `attachmentId` payloads separately.

`_http_error()` centralises diagnostic message extraction across both providers' differing error shapes (JSON error object → `WWW-Authenticate` header → raw body), including a specific hint for a common misconfiguration (using a tenant GUID for `MS_TENANT` with a personal Microsoft account, which causes Exchange to reject the token with a bare, empty-body 401).

`scripts/get_outlook_token.py` is a standalone CLI helper implementing the MSAL device-code flow to mint a Graph access token outside the Streamlit session, for manual testing of the Outlook path.

---

## 5. KPI Data Retrieval

`utils/nms_client.py` exposes `fetch_kpi_data(sites)`, returning `{cell_id: DataFrame}` with columns `[timestamp, availability, ps_traffic]` and, for 2G/3G cells, `cs_traffic`. Technology-to-CS-capability mapping is centralised in `tech_has_cs()`: 4G/5G/LTE/NR are packet-only and never carry circuit-switched traffic.

`NMS_MOCK` (default `1`) switches between:

- **`_fetch_mock`**: deterministic-per-cell synthetic generator (`random.Random(cell_id)`), producing hourly samples over `OBS_DAYS` (default 7) with a `_SLEEPING_PROBABILITY = 0.35` chance of injecting a traffic collapse roughly one-third into the observation window, while availability stays high — reproducing the same "high availability, collapsed traffic" dissociation pattern the classifier is trained to detect.
- **`_fetch_real`**: a documented stub for a generic REST NMS call (`GET {NMS_BASE_URL}/pm/counters`), with example endpoint references for Nokia NetAct, Ericsson OSS, and Huawei U2020.

`parse_sites_csv()` normalises the email-attached CSV: lower-cases/underscores column names, resolves common `cell_id` column-name variants (`cellid`, `cell`, `site_id`, `node_id`, `id`), and explicitly strips any pre-existing verdict/probability/label/score columns so a re-uploaded prior report can't leak a stale verdict into a fresh classification run.

---

## 6. Diagnostic Plot Generation

`utils/plotter.py` renders the dual-axis line charts that are the classifier's actual input. This module was the subject of a significant defect investigation (§9.4) and its current specification is load-bearing: **any deviation from this exact template degrades the classifier to near-random, class-collapsed predictions**, because the model was trained on images with this specific visual convention.

### 6.1 Template specification

| Property | Value |
|---|---|
| Image dimensions | ≈885 × 345 px (`bbox_inches="tight"`, so exact size varies slightly with content) |
| Format / DPI | PNG, 100 DPI (`PLOT_DPI`) |
| Figure size | 8.9 in × 3.5 in (`PLOT_W_IN`, `PLOT_H_IN`) |
| Background | White (matplotlib default) |
| X-axis | Date, `%m/%d` format, one tick per day (`DayLocator`) |
| Left Y-axis | Availability (%), fixed range `[0, 105]` |
| Right Y-axis | Traffic (Erlangs for CS, MB/h for PS), **floored at 0** (`set_ylim(bottom=0)`), upper bound auto-scaled |
| Availability line | Solid, green, linewidth 1.6 |
| Traffic line | Dashed, blue, linewidth 1.4 |
| Gridlines | Light dashed, alpha 0.7 |
| Legend | Upper-left, combined series |
| Title | **None** — not rendered in the image (cell ID is shown separately in the dashboard UI) |

Two variants are generated per cell (`generate_plots(df)`): Availability-vs-CS for 2G/3G cells and Availability-vs-PS for all cells (4G/5G cells therefore yield a single plot).

### 6.2 The right-axis floor (`ax2.set_ylim(bottom=0)`)

This single line is the most consequential detail in the module. Matplotlib's default autoscale centres the axis range **symmetrically** around a near-constant data series — so a genuinely sleeping cell's near-zero, flat traffic line would be rendered in the *middle* of the frame rather than pinned to the *bottom*. Since the classifier was trained on images where traffic-collapse is visually represented as "a flat line hugging the bottom of the frame," this single default-autoscale behaviour was sufficient, on its own, to invert the model's output on real KPI data (§9.4). Because traffic is physically non-negative, flooring at zero is also the objectively correct convention, independent of the classifier.

---

## 7. Computer-Vision Model

### 7.1 Architecture (`models/classifier.py`, `models/train.py::build_model`)

- **Backbone**: ResNet-18 (default) or ResNet-50, ImageNet-pretrained (`IMAGENET1K_V1` weights), selected via `MODEL_ARCH`.
- **Head**: the pretrained `fc` layer is replaced with `Linear(in_features, 256) → ReLU → Dropout(0.4) → Linear(256, 1) → Sigmoid`, producing a single scalar probability.
- **Input preprocessing**: `Resize((224, 224))`, `ToTensor()`, `Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])` — standard ImageNet normalisation statistics, consistent between training and inference.
- **Label convention**: `healthy = 0`, `sleeping = 1` (`models/train.py:307`).
- **Decision rule**: `label = 1 if prob >= DECISION_THRESHOLD else 0`, threshold default `0.5` (`config.py`).

### 7.2 Inference wrapper (`SleepingCellClassifier`)

Lazily loads weights on first non-mock instantiation (`models/weights/` + `MODEL_WEIGHTS_PATH`). If `MODEL_MOCK=1` (default) or PyTorch is unavailable, `predict()` falls back to `_mock_predict()` — a per-`cell_id`-seeded deterministic pseudo-random output (35% sleeping bias), allowing the full UI pipeline to be demonstrated without GPU or trained weights.

`classify_plots()` combines a cell's CS and PS verdicts with a **logical OR**: a cell is confirmed sleeping if *either* stream exhibits the sleeping pattern. In mock mode with real KPI data available, verdicts are instead derived directly from the KPI DataFrame via `_rule_verdict()` (availability ≥ 95% and traffic collapse ratio, currently threshold `< 0.10`), so the mock demonstration always agrees with the plotted curves rather than being purely random.

### 7.3 Training methodology (`models/train.py`)

| Hyperparameter | Value |
|---|---|
| Optimizer | Adam, `lr=1e-4`, `weight_decay=1e-4` |
| LR schedule | `ReduceLROnPlateau(mode="min", patience=5, factor=0.5)` on validation loss |
| Loss | `BCELoss`, per-sample re-weighted by inverse class frequency |
| Batch size | 16 |
| Max epochs | 30, early stopping patience 10 (on validation loss) |
| Train-time augmentation | `RandomHorizontalFlip`, `RandomRotation(8°)`, `ColorJitter(brightness=0.15, contrast=0.15, saturation=0.1)` |
| Seed | 42 (Python `random`, NumPy, PyTorch CPU+CUDA, `cudnn.deterministic=True`) |

Reproducibility is enforced end-to-end: a seeded `torch.Generator` drives the shuffling `DataLoader`, and `worker_init_fn` reseeds NumPy/`random` inside each spawned worker process.

---

## 8. Dataset & Data Quality Investigation

This section documents the most significant engineering work behind the current model: the original dataset and evaluation methodology were found, through systematic investigation, to produce an artificially perfect (100%) accuracy that did not reflect genuine generalisation. Each issue was diagnosed with concrete evidence (not assumed) and corrected in sequence.

### 8.1 Original dataset

`Dataset/` — 1169 PNG images across `train/val/test` × `healthy/sleeping`, generated by an earlier, since-superseded plot-generation script in a light theme with the cell ID baked into the image title.

### 8.2 Issue 1 — Exact duplicate images

MD5 content-hashing across all three splits found 17 duplicate-hash groups (1169 → 1152 unique files). All 17 groups were `sleeping`-class pairs sharing identical rendered content across a `3G_` and `4G_` filename prefix — an artifact of the original generator reusing the same PS-traffic image for both technology tags. Five of these groups spanned a train/test or val/test boundary, meaning the model's test-set "perfect" recall on the sleeping class was partly attributable to literal memorisation of images it had already seen during training under a different filename.

### 8.3 Issue 2 — Group (entity) leakage

Beyond exact duplicates, each physical cell contributes **two** plots (CS and PS) of correlated underlying behaviour. Checking cross-split placement by parsed cell ID found **175 of 676 unique cells (26%)** had sibling images split across different partitions — 292 healthy and 58 sleeping images (38% of the entire sleeping class) belonged to a cell whose sibling plot lived in a different split. This is the standard "grouped data" leakage failure mode (analogous to the same patient's scans appearing in both train and test in medical imaging).

### 8.4 Issue 3 — Baked-in title text as a shortcut feature

Every image's rendered title contained the literal cell ID (e.g. *"Cell Availability vs Circuit-Switched Traffic — KT2557V"*). Combined with §8.3, this handed the model a trivial memorisation shortcut — recognising an ID's text/rendering and its associated training label — independent of any genuine KPI pattern. **Fix**: the top region of every image was auto-detected (row where a near-full-width dark horizontal run first appears — the axes' top spine, verified consistent at row 41 across all 1169 original images) and cropped out, removing the title entirely.

### 8.5 Issue 4 — Near-duplicate content beyond exact hashes

Re-hashing images *after* title-cropping surfaced 10 additional duplicate-content clusters that were **not** exact duplicates of the original (titled) files — different cell IDs whose charts were pixel-identical once the distinguishing title text was removed. The largest cluster contained 46 images, entirely flat-line "sleeping" templates. Quantifying genuine visual diversity (after merging both cell-ID and post-crop content-hash groups) found the sleeping class contains only **45 genuinely distinct visual patterns across 152 unique images** (healthy: 600 distinct patterns across 1000 images) — meaning naive per-image splitting could not have produced a statistically independent test set regardless of methodology.

### 8.6 Remediation pipeline → `Dataset_clean`

`models/train.py::pool_dataset()` + `build_groups()` implement the final, deterministic (seed=42) pipeline:

1. Pool all images from `train/val/test`, MD5-hash raw bytes, keep one file per exact duplicate.
2. Crop the top 39px off every retained image (removes the title).
3. Compute a post-crop content hash per image.
4. **Union-find** merge: any two records sharing `(class, cell_id)` *or* `(class, post_crop_hash)` are placed in the same group — closing both the entity-leakage and near-duplicate-content vectors simultaneously.
5. Greedy proportional allocation of whole groups (largest-first) into train/val/test targeting an 80/10/10 split by image count, per class.

### 8.7 Final dataset statistics (`Dataset_clean/`)

| Split | Healthy | Sleeping |
|---|---|---|
| train | 800 | 122 |
| val | 100 | 16 |
| test | 100 | 14 |
| **Total** | **1000** | **152** |

Verified zero cross-split leakage on all three vectors simultaneously (cell-ID groups, raw-content hashes, post-crop-content hashes) — re-confirmed after an accidental local deletion and deterministic regeneration from `Dataset/`.

---

## 9. Model Evaluation

### 9.1 Why a single train/val/test split was insufficient

Three successive single-split evaluations — on the original leaky dataset, on an exact-duplicate-only fix, and on the fully remediated `Dataset_clean` — **all** produced 100% accuracy on the held-out test set. Given the dataset-quality findings in §8, this was diagnosed as consistent with a combination of residual leakage (first two attempts) and, even after leakage was fully closed, an inherently thin/near-tautological class-separation signal (§9.3) rather than genuine, well-evidenced generalisation.

### 9.2 5-fold grouped stratified cross-validation

Rather than trust any single split, the model is evaluated with `StratifiedGroupKFold(n_splits=5)` over the entire pooled, leak-safe dataset (`models/train.py::cross_validate`), using the same union-find groups as §8.6 so no fold's train/test boundary can cross a cell-ID or content-duplicate group. Each fold trains an independent model (fresh ResNet-18, same hyperparameters, seed offset by fold index) and is evaluated exactly once on its held-out fold; a further **grouped** inner split (`GroupShuffleSplit`, 12% of each fold's training pool) provides early-stopping validation without touching the fold's test data.

### 9.3 Results

Executed on Google Colab (Tesla T4 GPU); results retrieved directly from `cv_report.txt`:

```
5-fold grouped stratified cross-validation, seed=42

Mean +/- std across 5 folds:
  accuracy:            1.000 +/- 0.000
  sleeping precision:  1.000 +/- 0.000
  sleeping recall:     1.000 +/- 0.000
  sleeping f1:         1.000 +/- 0.000

Pooled out-of-fold report:
              precision    recall  f1-score   support

     healthy       1.00      1.00      1.00      1000
    sleeping       1.00      1.00      1.00       152

    accuracy                           1.00      1152
   macro avg       1.00      1.00      1.00      1152
weighted avg       1.00      1.00      1.00      1152

Pooled confusion matrix (rows=true, cols=pred, order=[healthy, sleeping]):
[[1000    0]
 [   0  152]]
```

**Interpretation**: zero variance across five independently-trained, group-disjoint folds is strong evidence that leakage has been eliminated — a leakage-driven perfect score would be expected to vary across folds, since different folds hold out different leaked pairs. The *persistence* of a perfect score after leakage closure instead points to a dataset-level property: the traffic-collapse signal, as rendered by the plot template (§6.2), is close to trivially separable pixel-wise (a flat line pinned to the axis floor vs. a fluctuating line filling the frame), and the sleeping class's low genuine diversity (45 distinct patterns, §8.5) means the model has limited opportunity to be tested on truly novel presentations. **This score should not be reported as a real-world generalisation estimate without this caveat.**

### 9.4 Production format-mismatch defect (discovered via real-world testing)

Testing the deployed model against `utils/plotter.py`'s live output initially produced a **100% failure rate — the model collapsed to always predicting a single class**, regardless of input. Root-cause investigation (not assumption) found three independent, additive mismatches between the live plot template and the training data:

1. **Colour theme**: the live plotter used a dark background with cyan/orange/green lines (an unrelated UI redesign); training images were white-background, green/blue.
2. **Image dimensions**: live output 960×420 with a visible top margin; training images 885×345 flush-cropped.
3. **Traffic-axis autoscale** (the dominant cause, §6.2): plain matplotlib autoscale centres a near-constant series symmetrically, placing a flat "sleeping" line in the middle of the frame instead of pinned to the bottom.

All three were corrected in `utils/plotter.py` and `utils/config.py` (`PLOT_DPI=100, PLOT_W_IN=8.9, PLOT_H_IN=3.5`), then verified against **real, labelled KPI data** pulled from `Sleeping-Cell-KPI-Data/{healthy_cells,sleeping_cells_}.xlsx` (not synthetic test cases) run through the actual `generate_plots()` → `SleepingCellClassifier.predict()` path: **20/20 correct**, with confident, well-separated probabilities (sleeping cells ≈0.9997–0.9999, healthy cells ≈0.0000–0.0022), replacing the prior degenerate collapsed output.

This finding underscores that the classifier's validity is coupled tightly to the exact visual template it was trained on — a conclusion the cross-validation results in §9.3 could not have surfaced on their own, since CV was run entirely within the (internally template-consistent) training dataset.

---

## 10. Production Deployment

### 10.1 Active model

The currently wired model (`.env`: `MODEL_MOCK=0`, `MODEL_WEIGHTS=models/weights/sleeping_cell_model_fold4.pt`) is fold 4's classifier from the 5-fold CV run (§9.2) — one of five independently-trained, group-disjoint models, selected as a pragmatic, already-available, verified-working checkpoint (§9.4).

### 10.2 Recommended production training strategy

No single CV fold model is the principled long-term production artifact — each was trained on only ~80% of an already-small dataset (152 sleeping images total). The recommended approach, not yet executed at time of writing: train one final model on the **entire** pooled, deduplicated dataset (all of `Dataset_clean`, no permanent holdout), using a small grouped validation carve-out for early stopping only. Under this framing, §9.3's cross-validation numbers serve as the reported generalisation estimate, while the production model is trained to maximise use of the limited sleeping-class data rather than withholding a redundant slice of it.

---

## 11. Reporting Pipeline

`utils/reporter.py::build_report_csv()` filters `classify_plots()` output to cells with `final == 1` (confirmed sleeping), enriches each row with the original site metadata (site name, region, tech, vendor), and records per-stream (CS/PS) probability, verdict, and which stream(s) triggered the sleeping classification (`streams_down`). `summarise()` computes total/sleeping/healthy counts and the fault rate. The compiled CSV is offered as a direct download and, if the pipeline detected any sleeping cells, can be emailed to the NOC team via the same provider-routed `send_report_email()` used elsewhere.

---

## 12. Configuration Reference

All runtime behaviour is centralised in `utils/config.py`, environment-variable driven via `python-dotenv` with safe non-production defaults:

| Setting | Default | Purpose |
|---|---|---|
| `AUTH_MODE` | `OAUTH` | `DEMO` or `OAUTH` login |
| `NMS_MOCK` | `1` | Synthetic vs. real NMS integration |
| `MODEL_ARCH` | `resnet18` | `resnet18` or `resnet50` |
| `MODEL_MOCK` | `1` | Rule-based/random mock vs. real ResNet inference |
| `MODEL_WEIGHTS` | `models/weights/sleeping_cell_model.pt` | Weights file path |
| `DECISION_THRESHOLD` | `0.5` | Sigmoid cutoff for the sleeping label |
| `EMAIL_SUBJECT_KEYWORD` | `sleeping cell` | Case-insensitive alert-email subject match |
| `OBS_DAYS` | `7` | KPI observation window |
| `PLOT_DPI` / `PLOT_W_IN` / `PLOT_H_IN` | `100` / `8.9` / `3.5` | Plot template — must match training data exactly (§6) |

---

## 13. Known Limitations & Recommendations

1. **Sleeping-class diversity is thin** (45 genuinely distinct patterns from 152 images) — the reported 100% CV accuracy is internally consistent but should not be read as a real-world generalisation guarantee; more varied real sleeping-cell examples would materially strengthen the evaluation.
2. **Template coupling** — the classifier's correctness is contingent on `utils/plotter.py` never drifting from the exact training-data template (§6). Any future UI/styling change to this module must be re-verified against the classifier, ideally with an automated regression check (ffixture rendering a known-flat and known-fluctuating series, asserting the classifier's verdict) rather than manual inspection.
3. **No production model trained on 100% of available data** — the active model (fold 4) was trained on ~80% of the dataset; §10.2's recommended final-training run has not yet been executed.
4. **Real-world validation set is small** — the 20/20 verification (§9.4) used a limited sample from `Sleeping-Cell-KPI-Data`; broader validation against a larger, independent real-data sample would further de-risk the deployment.
5. **`_rule_verdict()`'s mock-mode threshold** (`ratio < 0.10`, `models/classifier.py:206`) was adjusted from an earlier `0.30` during this project; its sensitivity to further tuning has not been formally evaluated.
