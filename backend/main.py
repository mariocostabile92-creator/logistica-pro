from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from optimizer import optimize_route
from openpyxl import load_workbook

import io
import uuid
import hashlib
import secrets

from database import (
    init_db,
    get_user_by_email,
    get_user_by_token,
    create_user,
    update_user_token,
    update_user_password,
    save_route_history,
    get_route_history,
    delete_route_history,
    save_delivery_report,
    get_delivery_reports,
    delete_delivery_reports,
    get_user_analytics,
)

app = FastAPI(
    title="Logistica Pro MVP",
    version="3.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

# 🔥 NUOVO ENDPOINT ROOT
@app.get("/")
def home():
    return {
        "status": "online",
        "app": "Logistica Pro",
        "message": "Backend attivo su Render 🚀"
    }

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ResetPasswordRequest(BaseModel):
    email: str
    recovery_code: str
    new_password: str

class RouteRequest(BaseModel):
    depot: str
    deliveries: list[str]

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def create_token():
    return secrets.token_hex(32)

def create_recovery_code():
    return str(uuid.uuid4())[:8].upper()

def get_current_user(authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token mancante")

    token = authorization.replace("Bearer ", "")
    user = get_user_by_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="Token non valido")

    return user

# =========================
# AUTH
# =========================

@app.post("/register")
def register(request: RegisterRequest):
    email = request.email.lower().strip()

    if get_user_by_email(email):
        raise HTTPException(400, "Email già registrata")

    user_id = str(uuid.uuid4())
    recovery_code = create_recovery_code()
    token = create_token()

    create_user(
        user_id,
        email,
        hash_password(request.password),
        recovery_code,
        token
    )

    return {
        "token": token,
        "recovery_code": recovery_code
    }

@app.post("/login")
def login(request: LoginRequest):
    user = get_user_by_email(request.email.lower())

    if not user or user["password_hash"] != hash_password(request.password):
        raise HTTPException(401, "Credenziali errate")

    token = create_token()
    update_user_token(request.email, token)

    return {"token": token}

@app.post("/reset-password")
def reset_password(request: ResetPasswordRequest):
    user = get_user_by_email(request.email.lower())

    if not user or user["recovery_code"] != request.recovery_code:
        raise HTTPException(400, "Codice non valido")

    token = create_token()

    update_user_password(
        request.email,
        hash_password(request.new_password),
        create_recovery_code(),
        token
    )

    return {"token": token}

# =========================
# ROUTE
# =========================

@app.post("/optimize-route")
def optimize(request: RouteRequest, authorization: str = Header(None)):
    user = get_current_user(authorization)

    result = optimize_route(
        request.depot,
        request.deliveries
    )

    save_route_history(
        user["id"],
        request.depot,
        request.deliveries,
        result
    )

    return result

# =========================
# EXCEL IMPORT
# =========================

@app.post("/import-excel")
async def import_excel(file: UploadFile = File(...), authorization: str = Header(None)):
    get_current_user(authorization)

    content = await file.read()
    workbook = load_workbook(io.BytesIO(content))
    sheet = workbook.active

    deliveries = []

    for row in sheet.iter_rows(values_only=True):
        for cell in row:
            if cell and isinstance(cell, str) and "," in cell:
                deliveries.append(cell.strip())

    return {
        "addresses": deliveries,
        "count": len(deliveries)
    }

# =========================
# STORICO
# =========================

@app.get("/storico")
def storico(authorization: str = Header(None)):
    user = get_current_user(authorization)
    return get_route_history(user["id"])

@app.delete("/storico")
def delete_storico(authorization: str = Header(None)):
    user = get_current_user(authorization)
    delete_route_history(user["id"])
    return {"message": "ok"}

# =========================
# REPORT
# =========================

@app.post("/save-report")
def save_report(payload: dict, authorization: str = Header(None)):
    user = get_current_user(authorization)

    save_delivery_report(user["id"], payload)

    return {"message": "salvato"}

@app.get("/reports")
def reports(authorization: str = Header(None)):
    user = get_current_user(authorization)
    return get_delivery_reports(user["id"])

# =========================
# ANALYTICS
# =========================

@app.get("/analytics")
def analytics(authorization: str = Header(None)):
    user = get_current_user(authorization)
    return get_user_analytics(user["id"])