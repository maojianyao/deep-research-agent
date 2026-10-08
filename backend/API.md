# Frontend REST API

Start the backend from the repository root:

```bash
uvicorn backend.src.api.main:app --reload
```

Interactive API docs are available at `/docs`. Configure comma-separated browser origins with `FRONTEND_ORIGINS` (defaults to localhost ports 3000 and 5173).

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/research-runs` | Create and start a research run; returns `202` |
| `GET` | `/api/research-runs` | Search/filter/paginate run summaries |
| `GET` | `/api/research-runs/{run_id}` | Run detail, tasks, candidate/evidence, findings, critiques, report and events |
| `GET` | `/api/research-runs/{run_id}/progress` | Lightweight status and incremental event polling |
| `GET` | `/api/research-runs/{run_id}/report.md` | Download the Markdown report |
| `POST` | `/api/research-runs/{run_id}/cancel` | Cancel a non-terminal run |
| `POST` | `/api/research-runs/{run_id}/resume` | Resume a persisted non-terminal run after interruption |

Create body:

```json
{
  "user_request": "Compare the economic and environmental effects of ...",
  "max_iterations": 3
}
```

List query parameters: `page` (default 1), `page_size` (default 20, max 100), `status` (one of `planning`, `researching`, `reviewing_evidence`, `synthesizing`, `critic_review`, `writing`, `completed`, `needs_human_review`, `failed`, `cancelled`) and `search` (matches the original request).

Progress accepts `after_sequence` (default 0) and returns only events with a larger sequence number, so a polling UI can send the last displayed sequence and avoid repeatedly downloading all details.

The create/resume response is `{ "id": "...", "status": "planning" }`. Poll the detail endpoint while status is non-terminal. Missing runs return `404`; a report that is not ready or an attempt to cancel/resume a finished run returns `409`; invalid input returns `422`.

Research execution uses in-process background tasks and SQLite by default. For a single backend process this keeps deployment simple; multi-worker deployments need a shared job queue and shared database before enabling multiple workers.
