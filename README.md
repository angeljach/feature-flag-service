## Feature Flag Service

This project is a simple Feature Flag Service built with Flask and SQLite. It allows you to create, update, delete, retrieve, and evaluate feature flags with support for targeting rules and percentage rollouts.

### Main Features

- **SQLite Database**: Stores feature flag definitions and targeting rules.
- **Flask API**: Exposes RESTful endpoints for flag management and evaluation.
- **In-memory Cache**: Caches flag configurations for fast access, with automatic refresh.
- **API Key Authentication**: Required for write operations (POST, PUT, DELETE).
- **Targeting Rules**: Supports user ID targeting and percentage rollouts.

### Endpoints

#### Create a Flag
`POST /flags` (Requires `X-API-Key` header)
```json
{
  "name": "new_checkout_flow",
  "type": "boolean", // or "string", "number", "json"
  "default_value": "true",
  "enabled": true,
  "targeting_rules": {
    "user_ids": ["user123", "user456"],
    "percentage": 50
  }
}
```

```shell
curl -X POST -H "Content-Type: application/json" -H "X-API-Key: your_super_secret_api_key" -d '{
    "name": "new_checkout_flow",
    "type": "boolean",
    "default_value": "true",
    "enabled": true,
    "targeting_rules": {
        "user_ids": ["alice", "bob"],
        "percentage": 50
    }
}' http://127.0.0.1:5000/flags
```

curl http://127.0.0.1:5000/flags

curl http://127.0.0.1:5000/flags/new_checkout_flow
curl http://127.0.0.1:5000/flags/new_dashboard



#### Get All Flags
`GET /flags`

#### Get a Single Flag
`GET /flags/<flag_name>`

#### Update a Flag
`PUT /flags/<flag_name>` (Requires `X-API-Key` header)
Partial updates allowed. Example:
```json
{
  "enabled": false,
  "targeting_rules": {"percentage": 75}
}
```

#### Delete a Flag
`DELETE /flags/<flag_name>` (Requires `X-API-Key` header)

#### Evaluate a Flag
`GET /evaluate/<flag_name>?user_id=123&country=US`
Returns the evaluated value for the given user context.

### Core Logic

- **Database Helper Functions**: Handles connection and schema initialization.
- **Cache**: Refreshes from DB if TTL expires.
- **Flag Evaluation**: Checks if flag is enabled, applies targeting rules (user IDs, percentage), and returns the correct value.
- **API Key Middleware**: Validates API key for write operations.

### Running the Service


1. Install dependencies using [uv](https://github.com/astral-sh/uv):
   ```bash
   uv add flask
   ```
   Or, to add all dependencies from `pyproject.toml` (recommended):
   ```bash
   uv add .
   ```

2. Run the service with uv:
   ```bash
   uv run main.py
   ```

The service will start on `http://localhost:5000`.

### Running Redis Locally (Optional)

If you want to run a local Redis instance for development or caching, you can use Docker:

```bash
docker run --name some-redis -p 6379:6379 -d redis
```

This will start a Redis server accessible at `localhost:6379`.

---
For more details, see the code in `main.py`.
