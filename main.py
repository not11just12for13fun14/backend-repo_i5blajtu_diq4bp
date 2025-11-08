import os
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, ValidationError
from typing import Optional
import re

from database import create_document
from schemas import Lead

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response

# Simple email sender using SMTP (works with most providers)
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
DEFAULT_TO_EMAIL = os.getenv("DEFAULT_TO_EMAIL", "ramthilakm@gmail.com")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER or "no-reply@ramgrowth.dev")

EMAIL_ENABLED = bool(SMTP_HOST and SMTP_USER and SMTP_PASS)

class LeadIn(BaseModel):
    name: str
    brand: str
    contact: str


def send_email_notification(lead: Lead):
    if not EMAIL_ENABLED:
        # Skip if SMTP not configured in the environment
        return

    subject = f"New Lead: {lead.name} · {lead.brand}"
    html = f"""
    <h2>New Lead — Website</h2>
    <p><b>Name:</b> {lead.name}</p>
    <p><b>Brand:</b> {lead.brand}</p>
    <p><b>Contact:</b> {lead.contact}</p>
    <p><b>Source:</b> {lead.source}</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = DEFAULT_TO_EMAIL

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, [DEFAULT_TO_EMAIL], msg.as_string())
    except Exception as e:
        # Log error; avoid failing the request solely due to email
        print("Email send error:", e)


@app.post("/api/leads")
async def create_lead(payload: LeadIn, background_tasks: BackgroundTasks):
    # Basic validation: allow either email or phone in contact
    contact = payload.contact.strip()
    email_like = re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact)
    phone_like = re.match(r"^[0-9+()\-\s]{7,}$", contact)

    if not (email_like or phone_like):
        raise HTTPException(status_code=400, detail="Contact must be a valid email or phone number")

    lead = Lead(name=payload.name.strip(), brand=payload.brand.strip(), contact=contact, source="website")

    # Persist to DB
    try:
        create_document("lead", lead)
    except Exception as e:
        # If DB not available, we still accept the lead to avoid lost opportunities
        print("DB insert error:", e)

    # Fire-and-forget email notification
    background_tasks.add_task(send_email_notification, lead)

    return {"ok": True, "message": "Lead captured"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
