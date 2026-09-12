import json
import os
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_

app = Flask(__name__)

database_url = os.getenv("DATABASE_URL", "sqlite:///kilimobiashara.db")
# Some hosted Postgres providers use the older scheme; SQLAlchemy expects this one.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Farmer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_code = db.Column(db.String(80), unique=True, nullable=True, index=True)
    full_name = db.Column(db.String(160), nullable=False, index=True)
    phone = db.Column(db.String(40), nullable=False, unique=True, index=True)
    village = db.Column(db.String(120))
    ward = db.Column(db.String(120))
    farm_location = db.Column(db.String(240))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    visits = db.relationship("Visit", backref="farmer", lazy=True, cascade="all, delete-orphan")


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"), nullable=False, index=True)
    visit_date = db.Column(db.Date, nullable=False, index=True)
    officer_name = db.Column(db.String(160))
    progress_status = db.Column(db.String(80), nullable=False)
    followup_date = db.Column(db.Date)
    officer_notes = db.Column(db.Text)
    zone = db.Column(db.String(160))
    breeds_json = db.Column(db.Text, nullable=False, default="[]")
    feeds_json = db.Column(db.Text, nullable=False, default="[]")
    herd_size = db.Column(db.Integer)
    land_size = db.Column(db.Float)
    water = db.Column(db.String(120))
    advisory = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def parse_date(value, label, required=False):
    if not value:
        if required:
            raise ValueError(f"{label} is required.")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD.") from exc


def clean_list(value):
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def farmer_as_dict(farmer, include_visits=False):
    data = {
        "id": farmer.id, "farmerId": farmer.farmer_code or "", "farmerName": farmer.full_name,
        "farmerPhone": farmer.phone, "village": farmer.village or "", "ward": farmer.ward or "",
        "farmLocation": farmer.farm_location or "", "createdAt": farmer.created_at.isoformat(),
        "updatedAt": farmer.updated_at.isoformat(), "visitCount": len(farmer.visits),
    }
    if include_visits:
        data["visits"] = [visit_as_dict(v) for v in sorted(farmer.visits, key=lambda item: (item.visit_date, item.id), reverse=True)]
    return data


def visit_as_dict(visit):
    return {
        "id": visit.id, "visitDate": visit.visit_date.isoformat(), "officerName": visit.officer_name or "",
        "progressStatus": visit.progress_status, "followupDate": visit.followup_date.isoformat() if visit.followup_date else "",
        "officerNotes": visit.officer_notes or "", "zone": visit.zone or "",
        "breeds": json.loads(visit.breeds_json), "feeds": json.loads(visit.feeds_json),
        "herdSize": visit.herd_size, "landSize": visit.land_size, "water": visit.water or "",
        "advisory": visit.advisory, "createdAt": visit.created_at.isoformat(),
    }


def make_advisory(payload):
    """Use OpenAI when configured; provide a useful field template during setup/demo."""
    farmer = payload["farmer"]
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = f"""Create a practical dairy-farm extension advisory for Kenya. This is guidance, not a veterinary diagnosis. Use clear headings: Farm snapshot, Recommended actions, Follow-up checks, and Caution. Keep it under 350 words. Do not invent measurements. Data: {json.dumps(payload, ensure_ascii=False)}"""
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            input=prompt,
            store=False,
        )
        return response.output_text.strip()

    feeds = ", ".join(payload["feeds"])
    return (
        f"Farm snapshot\n{farmer['farmerName']} has {payload['herdSize']} animal(s) on {payload['landSize']} acre(s) of fodder land. "
        f"Current feed resources: {feeds}. Water availability: {payload['water']}.\n\n"
        "Recommended actions\n1. Confirm daily feed quantities, body condition, milk records, and reliable clean water access.\n"
        "2. Keep a simple weekly record of feed bought/harvested, milk output, health events, and costs.\n"
        "3. Discuss fodder preservation and a dry-season feeding plan at the next visit.\n\n"
        "Follow-up checks\nReview the agreed action, animal condition, feed availability, and the farmer's records on the follow-up date.\n\n"
        "Caution\nThis setup report was generated without an OpenAI API key. Confirm animal-health and ration decisions with a qualified local livestock professional."
    )


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/api/farmers")
def list_farmers():
    query = request.args.get("q", "").strip()
    statement = Farmer.query
    if query:
        needle = f"%{query}%"
        statement = statement.filter(or_(Farmer.full_name.ilike(needle), Farmer.phone.ilike(needle), Farmer.farmer_code.ilike(needle)))
    farmers = statement.order_by(Farmer.updated_at.desc()).limit(50).all()
    return jsonify(farmers=[farmer_as_dict(farmer) for farmer in farmers])


@app.get("/api/farmers/<int:farmer_id>")
def get_farmer(farmer_id):
    farmer = db.get_or_404(Farmer, farmer_id)
    return jsonify(farmer=farmer_as_dict(farmer, include_visits=True))


@app.post("/api/advise")
def advise():
    payload = request.get_json(silent=True) or {}
    farmer_data = payload.get("farmer") or {}
    name = str(farmer_data.get("farmerName", "")).strip()
    phone = str(farmer_data.get("farmerPhone", "")).strip()
    if not name or not phone:
        return jsonify(success=False, error="Farmer full name and phone number are required."), 400
    try:
        visit_date = parse_date(farmer_data.get("visitDate"), "Visit date", required=True)
        followup_date = parse_date(farmer_data.get("followupDate"), "Follow-up date")
        breeds, feeds = clean_list(payload.get("breeds")), clean_list(payload.get("feeds"))
        if not breeds or not feeds:
            raise ValueError("Select at least one breed and one feed resource.")
        herd_size = int(payload.get("herdSize"))
        land_size = float(payload.get("landSize"))
        if herd_size < 1 or land_size <= 0:
            raise ValueError("Herd size and fodder land size must be greater than zero.")
    except (TypeError, ValueError) as exc:
        return jsonify(success=False, error=str(exc)), 400

    farmer_code = str(farmer_data.get("farmerId", "")).strip() or None
    farmer = Farmer.query.filter_by(phone=phone).first()
    if farmer_code:
        code_match = Farmer.query.filter_by(farmer_code=farmer_code).first()
        if code_match and farmer and code_match.id != farmer.id:
            return jsonify(success=False, error="That farmer ID already belongs to a different phone number."), 409
        farmer = code_match or farmer
    if not farmer:
        farmer = Farmer(full_name=name, phone=phone, farmer_code=farmer_code)
        db.session.add(farmer)
    else:
        farmer.full_name, farmer.phone = name, phone
        if farmer_code:
            farmer.farmer_code = farmer_code
    farmer.village = str(farmer_data.get("village", "")).strip() or None
    farmer.ward = str(farmer_data.get("ward", "")).strip() or None
    farmer.farm_location = str(farmer_data.get("farmLocation", "")).strip() or None

    normalized = {"farmer": farmer_data, "zone": str(payload.get("zone", "")), "breeds": breeds, "feeds": feeds,
                  "herdSize": herd_size, "landSize": land_size, "water": str(payload.get("water", ""))}
    try:
        advisory = make_advisory(normalized)
    except Exception:
        app.logger.exception("Advisory generation failed")
        return jsonify(success=False, error="The advisory service could not be reached. The farmer profile was not changed."), 502

    visit = Visit(farmer=farmer, visit_date=visit_date, officer_name=str(farmer_data.get("officerName", "")).strip() or None,
                  progress_status=str(farmer_data.get("progressStatus", "Initial assessment")), followup_date=followup_date,
                  officer_notes=str(farmer_data.get("officerNotes", "")).strip() or None, zone=normalized["zone"],
                  breeds_json=json.dumps(breeds), feeds_json=json.dumps(feeds), herd_size=herd_size, land_size=land_size,
                  water=normalized["water"], advisory=advisory)
    db.session.add(visit)
    db.session.commit()
    return jsonify(success=True, advisory=advisory, farmer=farmer_as_dict(farmer), visit=visit_as_dict(visit))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
