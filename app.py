import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template , redirect, url_for
import uuid
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VideoGrant
from dotenv import load_dotenv
load_dotenv()
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

app = Flask(__name__, template_folder='templates', static_folder='static')

socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "telemedicine.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JSON_SORT_KEYS"] = False

# Load credentials from environment variables (NOT hardcoded in code)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_API_KEY_SID = os.getenv("TWILIO_API_KEY_SID")
TWILIO_API_KEY_SECRET = os.getenv("TWILIO_API_KEY_SECRET")

CORS(app)
db = SQLAlchemy(app)

# Database Models
class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialty = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    experience_years = db.Column(db.Integer, default=0)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(50), nullable=False)
    doctor = db.Column(db.String(120), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    time = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Consultation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    symptoms = db.Column(db.Text, nullable=False)
    mode = db.Column(db.String(10), nullable=False)
    room_name = db.Column(db.String(120), nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def seed_doctors():
    if Doctor.query.count() > 0:
        return
    
    seed_data = [
        ("Nagpur", "Dr. Anjali Deshmukh", "General Physician", 10),
        ("Nagpur", "Dr. Rajesh Patil", "Cardiologist", 12),
        ("Nagpur", "Dr. Kiran Agrawal", "Orthopedic Surgeon", 15),
        ("Nagpur", "Dr. Meera Joshi", "ENT Specialist", 7),
        ("Yavatmal", "Dr. Sneha Kulkarni", "Pediatrician", 8),
        ("Yavatmal", "Dr. Amit Joshi", "Dermatologist", 6),
        ("Yavatmal", "Dr. Nikhil More", "Neurologist", 11),
        ("Yavatmal", "Dr. Kavita Rathi", "Gynecologist", 9),
        ("Akola", "Dr. Priya Shinde", "Gynecologist", 9),
        ("Akola", "Dr. Suresh Bhoyar", "General Surgeon", 14),
        ("Akola", "Dr. Ramesh Kale", "Psychiatrist", 10),
        ("Akola", "Dr. Manisha Wagh", "Ophthalmologist", 8),
    ]
    
    for city, name, spec, exp in seed_data:
        db.session.add(Doctor(city=city, name=name, specialty=spec, experience_years=exp))
    
    db.session.commit()
    print("Doctors data seeded successfully!")

# Routes for serving HTML pages
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/doctors")
def doctors():
    return render_template("doctors.html")

@app.route("/appointment")
def appointment():
    return render_template("appointment.html")

@app.route("/consult")
def consult():
    return render_template("consult.html")

@app.route("/appointment-details")
def appointment_details():
    return render_template("appointment-details.html")

# call route
@app.route("/video_call/<room_name>")
def video_call(room_name):
    # render call.html and pass the room_name provided by server
    return render_template("call.html", room_name=room_name)

# API Endpoints
@app.route("/api/health")
def health():
    return jsonify(status="ok")

@app.route("/api/doctors")
def api_doctors():
    city = request.args.get("city")
    q = Doctor.query
    if city:
        q = q.filter_by(city=city)
    
    doctors = [{
        "id": d.id,
        "name": d.name,
        "specialty": d.specialty,
        "city": d.city,
        "experience_years": d.experience_years,
    } for d in q.order_by(Doctor.city, Doctor.name).all()]
    
    return jsonify(doctors=doctors)

@app.route("/api/appointments", methods=["POST", "GET"])
def api_appointments():
    if request.method == "GET":
        city = request.args.get("city")
        q = Appointment.query
        if city:
            q = q.filter_by(city=city)
        
        data = [{
            "id": a.id,
            "patient_name": a.patient_name,
            "city": a.city,
            "doctor": a.doctor,
            "date": a.date,
            "time": a.time,
            "created_at": a.created_at.isoformat() + "Z",
        } for a in q.order_by(Appointment.created_at.desc()).all()]
        
        return jsonify(appointments=data)
    
    data = request.get_json()
    if not data:
        return jsonify(error="No data provided"), 400
    required = ["patient_name", "city", "doctor", "date", "time"]
    missing = [k for k in required if k not in data or not data[k]]
    
    if missing:
        return jsonify(error=f"Missing fields: {', '.join(missing)}"), 400

    appt = Appointment(
        patient_name=data["patient_name"].strip(),
        city=data["city"],
        doctor=data["doctor"],
        date=data["date"],
        time=data["time"],
    )
    
    db.session.add(appt)
    db.session.commit()
    
    return jsonify(message="Appointment confirmed", id=appt.id,
        appointment={
            "patient_name": appt.patient_name,
            "city": appt.city,
            "doctor": appt.doctor,
            "date": appt.date,
            "time": appt.time
        }
            ), 201


@app.route("/api/consultations", methods=["POST", "GET"])
def api_consultations():
    if request.method == "GET":
        data = [{
            "id": c.id,
            "patient_name": c.patient_name,
            "age": c.age,
            "symptoms": c.symptoms,
            "mode": c.mode,
            "created_at": c.created_at.isoformat() + "Z",
        } for c in Consultation.query.order_by(Consultation.created_at.desc()).all()]
        
        return jsonify(consultations=data)
    
    data = request.get_json()
    if not data:
        return jsonify(error="No data provided"), 400
    required = ["patient_name", "age", "symptoms", "mode"]
    missing = [k for k in required if k not in data or not data[k]]
    
    if missing:
        return jsonify(error=f"Missing fields: {', '.join(missing)}"), 400

    try:
        age = int(data["age"])
    except ValueError:
        return jsonify(error="Age must be a number"), 400
    # Generate a room name only for video/audio modes
    room_name = None
    if data["mode"] in ("video", "audio"):
        # unique but readable room name
        room_name = f"telemed_{uuid.uuid4().hex[:10]}"

    cons = Consultation(
        patient_name=data["patient_name"].strip(),
        age=age,
        symptoms=data["symptoms"].strip(),
        mode=data["mode"],
        room_name=room_name
    )
    
    db.session.add(cons)
    db.session.commit()
    
    # Build response including room info (if any)
    resp = {
        "message": "Consultation submitted",
        "id": cons.id,
        "consultation": {
            "patient_name": cons.patient_name,
            "age": cons.age,
            "mode": cons.mode,
        }
    }

    if room_name:
        # URL patient/doctor should open to join the same room
        resp["room_name"] = room_name
        resp["room_url"] = url_for("video_call", room_name=room_name, _external=False)

    return jsonify(resp), 201

    return jsonify(message="Consultation submitted", id=cons.id,
        consultation={
            "patient_name": cons.patient_name,
            "age": cons.age,
            "mode": cons.mode
        }), 201



@app.route("/get_video_token", methods=["POST"])
def get_video_token():
    data = request.get_json()
    identity = data.get("identity")  # Example: patient or doctor username

    # Create access token
    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY_SID,
        TWILIO_API_KEY_SECRET,
        identity=identity
    )

    # Grant access to Video
    video_grant = VideoGrant()
    token.add_grant(video_grant)

    return jsonify({"token": token.to_jwt().decode("utf-8")})


# Admin views
@app.route("/admin/appointments")
def admin_appts():
    rows = Appointment.query.order_by(Appointment.created_at.desc()).all()
    html = [
        "<h2>Appointments</h2>",
        "<table border=1 cellpadding=6>",
        "<tr><th>ID</th><th>Patient</th><th>City</th><th>Doctor</th><th>Date</th><th>Time</th><th>Created</th></tr>",
    ]
    
    for a in rows:
        html.append(
            f"<tr><td>{a.id}</td><td>{a.patient_name}</td><td>{a.city}</td><td>{a.doctor}</td><td>{a.date}</td><td>{a.time}</td><td>{a.created_at}</td></tr>"
        )
    
    html.append("</table>")
    return "".join(html)

@app.route("/admin/consultations")
def admin_cons():
    rows = Consultation.query.order_by(Consultation.created_at.desc()).all()
    html = [
        "<h2>Consultations</h2>",
        "<table border=1 cellpadding=6>",
        "<tr><th>ID</th><th>Patient</th><th>Age</th><th>Mode</th><th>Symptoms</th><th>Created</th></tr>",
    ]
    
    for c in rows:
        html.append(
            f"<tr><td>{c.id}</td><td>{c.patient_name}</td><td>{c.age}</td><td>{c.mode}</td><td>{c.symptoms[:50]}...</td><td>{c.created_at}</td></tr>"
        )
    
    html.append("</table>")
    return "".join(html)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_doctors()
    
    print("Starting Telemedicine Platform...")
    print("Access the application at: http://localhost:5000")
    print("Admin views:")
    print("  - Appointments: http://localhost:5000/admin/appointments")
    print("  - Consultations: http://localhost:5000/admin/consultations")
    
    
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)