"""
Sample Target File: Clean, Enterprise-Grade Secure API Microservice
Follows FDE Architecture Standards and passes all compliance gates:
- Uses os.getenv for environment secrets (SEC-002)
- Uses parameterized query placeholders (?, param) (SEC-001)
- Specifies explicit network timeout=5.0 (PERF-001)
- Avoids dangerous eval() in favor of safe parsing (SEC-003)
- Isolates schema alterations to migrations (ARCH-001)
"""

import os
import sqlite3
import requests
import ast
from typing import Optional, Dict, Any

# Compliant SEC-002: Credentials fetched from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

def get_user_profile(user_email: str) -> Optional[Dict[str, Any]]:
    """Compliant SEC-001: Parameterized query protects against SQL injection."""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    query = "SELECT id, username, balance FROM users WHERE email = ?"
    cursor.execute(query, (user_email,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"id": row[0], "username": row[1], "balance": row[2]}
    return None

def sync_currency_rates() -> Dict[str, Any]:
    """Compliant PERF-001: Explicit network timeout prevents thread starvation."""
    response = requests.get("https://api.exchangerate.host/latest", timeout=5.0)
    response.raise_for_status()
    return response.json()

def calculate_formula(user_literal: str) -> Dict[str, Any]:
    """Compliant SEC-003: Uses ast.literal_eval for safe literal evaluation."""
    safe_result = ast.literal_eval(user_literal)
    return {"calculated": safe_result}
