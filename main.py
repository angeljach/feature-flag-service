import sqlite3
import json
import random
import time
from flask import Flask, request, jsonify, g

# --- Configuration ---
DATABASE = 'feature_flags.db'
API_KEY = 'your_super_secret_api_key' # In a real app, use environment variables or a secure vault
CACHE_TTL_SECONDS = 60 # Time-to-live for cached flag configurations

app = Flask(__name__)

# --- Database Helper Functions ---
def get_db():
    """Establishes a database connection or returns the existing one."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row # This allows accessing columns by name
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database schema."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feature_flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL, -- 'boolean', 'string', 'number', 'json'
                default_value TEXT,
                enabled INTEGER DEFAULT 0, -- 0 for false, 1 for true
                targeting_rules TEXT -- JSON string for complex rules
            )
        ''')
        db.commit()
        print(f"Database '{DATABASE}' initialized successfully.")

# --- In-memory Cache for Flag Configurations ---
# This dictionary will store flag configurations and their last update time
# for quick lookups.
flag_cache = {}
last_cache_refresh = 0

def refresh_cache():
    """Refreshes the in-memory cache from the database."""
    global flag_cache, last_cache_refresh
    current_time = time.time()
    if current_time - last_cache_refresh < CACHE_TTL_SECONDS:
        return # Cache is still fresh enough

    print("Refreshing feature flag cache...")
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM feature_flags')
    flags = cursor.fetchall()

    new_cache = {}
    for flag in flags:
        flag_dict = dict(flag)
        # Parse targeting rules from JSON string back to a Python object
        if flag_dict['targeting_rules']:
            flag_dict['targeting_rules'] = json.loads(flag_dict['targeting_rules'])
        else:
            flag_dict['targeting_rules'] = {}
        new_cache[flag_dict['name']] = flag_dict
    
    flag_cache = new_cache
    last_cache_refresh = current_time
    print(f"Cache refreshed. {len(flag_cache)} flags loaded.")

# --- Feature Flag Evaluation Logic ---
def evaluate_flag(flag_name, user_context=None):
    """
    Evaluates a feature flag based on its rules and user context.
    
    Args:
        flag_name (str): The name of the feature flag.
        user_context (dict, optional): A dictionary containing user attributes
                                       (e.g., {'user_id': '123', 'country': 'US'}).
                                       Defaults to None.

    Returns:
        tuple: (evaluated_value, flag_found_status)
               evaluated_value: The value of the flag for the given context.
               flag_found_status: True if the flag exists, False otherwise.
    """
    refresh_cache() # Ensure cache is up-to-date

    flag_config = flag_cache.get(flag_name)
    if not flag_config:
        print(f"Flag '{flag_name}' not found in cache.")
        return None, False

    # 1. Check if the flag is globally enabled/disabled
    if not flag_config['enabled']:
        print(f"Flag '{flag_name}' is globally disabled.")
        return flag_config['default_value'], True

    # 2. Evaluate targeting rules
    rules = flag_config.get('targeting_rules', {})
    
    # Simple User ID targeting
    if 'user_ids' in rules and user_context and 'user_id' in user_context:
        if user_context['user_id'] in rules['user_ids']:
            print(f"Flag '{flag_name}' enabled for user_id '{user_context['user_id']}' via user_ids rule.")
            return flag_config['default_value'], True

    # Simple Percentage Rollout
    if 'percentage' in rules and isinstance(rules['percentage'], (int, float)):
        if user_context and 'user_id' in user_context:
            # Use user_id to ensure consistent bucketing for percentage rollouts
            # A simple hash or modulo can be used for deterministic assignment
            seed = int(user_context['user_id']) if user_context['user_id'].isdigit() else sum(ord(c) for c in user_context['user_id'])
            random.seed(seed) # Seed the random generator for consistency per user
            
            if random.uniform(0, 100) < rules['percentage']:
                print(f"Flag '{flag_name}' enabled for user_id '{user_context['user_id']}' via percentage rule ({rules['percentage']}%).")
                return flag_config['default_value'], True
            else:
                print(f"Flag '{flag_name}' disabled for user_id '{user_context['user_id']}' via percentage rule.")
                return flag_config['default_value'], True
        else:
            # If no user_id for percentage, default to global enabled state
            print(f"Flag '{flag_name}' defaulting to global enabled state for percentage rule (no user_id).")
            return flag_config['default_value'], True

    # If no specific targeting rules apply, or no user context provided,
    # fall back to the global enabled state.
    print(f"Flag '{flag_name}' enabled globally (no specific rule applied or matched).")
    return flag_config['default_value'], True

# --- API Key Authentication Middleware ---
@app.before_request
def authenticate_api_key():
    """
    Checks for a valid API_KEY for POST, PUT, DELETE requests.
    This is a basic security measure for write operations.
    """
    if request.method in ['POST', 'PUT', 'DELETE']:
        if request.headers.get('X-API-Key') != API_KEY:
            return jsonify({"error": "Unauthorized: Invalid API Key"}), 401

# --- API Endpoints ---

@app.route('/flags', methods=['POST'])
def create_flag():
    """
    Creates a new feature flag.
    Requires X-API-Key header for authentication.
    Example JSON body:
    {
        "name": "new_checkout_flow",
        "type": "boolean",
        "default_value": "true",
        "enabled": true,
        "targeting_rules": {
            "user_ids": ["user123", "user456"],
            "percentage": 50
        }
    }
    """
    data = request.get_json()
    if not data or 'name' not in data or 'type' not in data:
        return jsonify({"error": "Missing required fields: name, type"}), 400

    name = data['name']
    flag_type = data['type']
    default_value = data.get('default_value')
    enabled = 1 if data.get('enabled', False) else 0
    
    # Convert targeting_rules dict to JSON string for storage
    targeting_rules = json.dumps(data.get('targeting_rules', {}))

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute(
            'INSERT INTO feature_flags (name, type, default_value, enabled, targeting_rules) VALUES (?, ?, ?, ?, ?)',
            (name, flag_type, default_value, enabled, targeting_rules)
        )
        db.commit()
        refresh_cache() # Invalidate/refresh cache after write
        return jsonify({"message": "Flag created successfully", "id": cursor.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Flag with name '{name}' already exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/flags', methods=['GET'])
def get_all_flags():
    """Retrieves all feature flags."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM feature_flags')
    flags = cursor.fetchall()
    
    # Convert row objects to dictionaries and parse JSON rules
    result = []
    for flag in flags:
        flag_dict = dict(flag)
        if flag_dict['targeting_rules']:
            flag_dict['targeting_rules'] = json.loads(flag_dict['targeting_rules'])
        else:
            flag_dict['targeting_rules'] = {}
        result.append(flag_dict)
    
    return jsonify(result), 200

@app.route('/flags/<string:flag_name>', methods=['GET'])
def get_flag(flag_name):
    """Retrieves a single feature flag by name."""
    refresh_cache() # Ensure cache is up-to-date
    flag_config = flag_cache.get(flag_name)

    if flag_config:
        # Return a copy to avoid modifying cached object directly
        return jsonify(flag_config), 200
    else:
        return jsonify({"error": f"Flag '{flag_name}' not found"}), 404

@app.route('/flags/<string:flag_name>', methods=['PUT'])
def update_flag(flag_name):
    """
    Updates an existing feature flag.
    Requires X-API-Key header for authentication.
    Example JSON body (partial updates allowed):
    {
        "enabled": true,
        "targeting_rules": {
            "percentage": 75
        }
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided for update"}), 400

    db = get_db()
    cursor = db.cursor()

    # Build update query dynamically
    set_clauses = []
    params = []

    if 'name' in data: # Allow changing name, but ensure uniqueness
        set_clauses.append("name = ?")
        params.append(data['name'])
    if 'type' in data:
        set_clauses.append("type = ?")
        params.append(data['type'])
    if 'default_value' in data:
        set_clauses.append("default_value = ?")
        params.append(data['default_value'])
    if 'enabled' in data:
        set_clauses.append("enabled = ?")
        params.append(1 if data['enabled'] else 0)
    if 'targeting_rules' in data:
        set_clauses.append("targeting_rules = ?")
        params.append(json.dumps(data['targeting_rules']))

    if not set_clauses:
        return jsonify({"error": "No valid fields to update"}), 400

    query = f"UPDATE feature_flags SET {', '.join(set_clauses)} WHERE name = ?"
    params.append(flag_name)

    try:
        cursor.execute(query, tuple(params))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": f"Flag '{flag_name}' not found"}), 404
        refresh_cache() # Invalidate/refresh cache after write
        return jsonify({"message": f"Flag '{flag_name}' updated successfully"}), 200
    except sqlite3.IntegrityError:
        return jsonify({"error": f"New name '{data['name']}' already exists for another flag"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/flags/<string:flag_name>', methods=['DELETE'])
def delete_flag(flag_name):
    """
    Deletes a feature flag.
    Requires X-API-Key header for authentication.
    """
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute('DELETE FROM feature_flags WHERE name = ?', (flag_name,))
        db.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": f"Flag '{flag_name}' not found"}), 404
        refresh_cache() # Invalidate/refresh cache after write
        return jsonify({"message": f"Flag '{flag_name}' deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/evaluate/<string:flag_name>', methods=['GET'])
def evaluate(flag_name):
    """
    Evaluates a feature flag for a given user context.
    User context can be passed as query parameters (e.g., ?user_id=123&country=US).
    """
    user_context = dict(request.args) # Get all query parameters as user context
    
    evaluated_value, flag_found = evaluate_flag(flag_name, user_context)

    if flag_found:
        # Attempt to convert default_value based on stored type
        # This is a simplification; a full system would handle type casting more robustly
        flag_config = flag_cache.get(flag_name)
        if flag_config:
            if flag_config['type'] == 'boolean':
                return jsonify({"flag_name": flag_name, "value": bool(int(evaluated_value)) if evaluated_value is not None else False}), 200
            elif flag_config['type'] == 'number':
                try:
                    return jsonify({"flag_name": flag_name, "value": float(evaluated_value) if evaluated_value is not None else None}), 200
                except (ValueError, TypeError):
                    return jsonify({"flag_name": flag_name, "value": None}), 200 # Or handle error
            elif flag_config['type'] == 'json':
                try:
                    return jsonify({"flag_name": flag_name, "value": json.loads(evaluated_value) if evaluated_value is not None else None}), 200
                except json.JSONDecodeError:
                    return jsonify({"flag_name": flag_name, "value": None}), 200 # Or handle error
            else: # string or other types
                return jsonify({"flag_name": flag_name, "value": evaluated_value}), 200
        else: # Should not happen if flag_found is True
            return jsonify({"error": "Internal error: Flag config missing after found"}), 500
    else:
        return jsonify({"error": f"Flag '{flag_name}' not found"}), 404

# --- Main Execution ---
if __name__ == '__main__':
    init_db() # Initialize the database when the app starts
    with app.app_context():
        refresh_cache() # Initial cache warm-up
    app.run(debug=True, port=5000) # Run the Flask app
