"""
Sample Target File: Vulnerable API Microservice
Contains real-world anti-patterns and vulnerabilities for AI Code Reviewer training:
1. SQL Injection (SEC-001)
2. Hardcoded API Secret (SEC-002)
3. Missing Network Timeout (PERF-001)
4. Dangerous eval() call (SEC-003)
5. Unshielded Destructive DDL (ARCH-001)
"""

import sqlite3
import requests

# Violation SEC-002: Hardcoded Production API Token
OPENAI_API_KEY = "sk-live-production-secret-99881122"

def get_user_profile(user_email: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Violation SEC-001: SQL Injection via f-string formatting
    query = f"SELECT id, username, balance FROM users WHERE email = '{user_email}'"
    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()
    return user

def sync_currency_rates():
    # Violation PERF-001: Missing timeout parameter on outbound HTTP call
    response = requests.get("https://api.exchangerate.host/latest")
    return response.json()

def calculate_formula(user_formula: str):
    # Violation SEC-003: Direct invocation of eval() on untrusted user string
    result = eval(user_formula)
    return {"calculated": result}

def cleanup_legacy_schema():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    # Violation ARCH-001: Destructive schema drop inside application logic
    cursor.execute("DROP TABLE legacy_audit_history;")
    conn.commit()
    conn.close()
