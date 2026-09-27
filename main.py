"""
Amount calculator API for a Bolna AI voice agent (custom function `calculate_amount`).

GET /calculate?operation=add&number1=125000&number2=40000
  operation: add | subtract | multiply | divide
  number1, number2: numbers; also accepts "2.5 lakh", "1,20,000", "50k", "1 crore"

Every response contains `message`, a short sentence the agent can speak as-is.
"""

import os
import re

from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="Bolna Amount Calculator")

API_TOKEN = os.getenv("API_TOKEN", "")  # optional; if set, Bolna must send "Bearer <token>"

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5,
    "cr": 1e7, "crore": 1e7, "crores": 1e7,
    "m": 1e6, "million": 1e6,
}

OPERATIONS = {
    "add": (lambda a, b: a + b, "plus"),
    "subtract": (lambda a, b: a - b, "minus"),
    "multiply": (lambda a, b: a * b, "times"),
    "divide": (lambda a, b: a / b, "divided by"),
}


def num(value, name):
    """Parse a number the LLM may have sent as text."""
    if value is None or str(value).strip().lower() in ("", "none", "null", "nan", "undefined"):
        raise ValueError(f"missing {name}")
    if isinstance(value, (int, float)):
        return float(value)
    s = value.strip().lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([a-z]*)", s)
    if not m or (m.group(2) and m.group(2) not in _MULTIPLIERS):
        raise ValueError(f"could not understand {name}: '{value}'")
    return float(m.group(1)) * _MULTIPLIERS.get(m.group(2), 1)


def speak(x):
    """Indian digit grouping, up to 2 decimals: 125000.5 -> '1,25,000.5', -3000 -> 'minus 3,000'."""
    x = round(x, 2)
    neg, x = x < 0, abs(x)
    whole, frac = str(int(x)), f"{x % 1:.2f}"[1:].rstrip("0").rstrip(".")
    if len(whole) > 3:
        head, parts = whole[:-3], [whole[-3:]]
        while head:
            parts.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(parts)
    return f"{'minus ' if neg else ''}{whole}{frac}"


@app.get("/")
def health():
    return {"status": "ok", "operations": list(OPERATIONS)}


@app.api_route("/calculate", methods=["GET", "POST"])
async def calculate(request: Request, authorization: str = Header(default="")):
    if API_TOKEN and authorization.removeprefix("Bearer ").strip() != API_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            params.update(await request.json())
        except Exception:
            pass

    op = str(params.get("operation", "")).strip().lower()
    if op not in OPERATIONS:
        return {"error": True, "message": f"Unknown operation '{op}'. Use one of: {', '.join(OPERATIONS)}."}
    try:
        a = num(params.get("number1"), "number1")
        b = num(params.get("number2"), "number2")
        fn, word = OPERATIONS[op]
        result = fn(a, b)
    except ZeroDivisionError:
        return {"error": True, "message": "I can't divide by zero."}
    except ValueError as e:
        return {"error": True, "message": f"I need a bit more information: {e}."}

    return {
        "operation": op, "number1": a, "number2": b, "result": round(result, 2),
        "message": f"{speak(a)} {word} {speak(b)} is {speak(result)}.",
    }
