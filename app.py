import os
import uuid
import qrcode
import datetime
import io
import base64
import io
import datetime
import logging

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Determine the base URL for QR code generation
# For Render, RENDER_EXTERNAL_HOSTNAME is provided
# render_external_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
# if render_external_hostname:
#     app_base_url = f"https://{render_external_hostname}"
# else:
#     # Fallback for local development or other environments
#     app_base_url = "http://127.0.0.1:5000" # Default local URL

app_base_url = "https://qr-checkin-new.onrender.com" # Hardcode for Render deployment

app.config['APP_BASE_URL'] = app_base_url

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///checkin.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Models
class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey('administrator.id'), nullable=False)
    qr_code_url = db.Column(db.Text, nullable=True) # Store base64 encoded QR code image

    admin = db.relationship('Administrator', backref='activities')

class Administrator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id_number = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    birthday = db.Column(db.Date, nullable=True)
    unit = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(100), nullable=True)

class CheckIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    check_in_time = db.Column(db.DateTime, default=datetime.datetime.now)
    check_in_method = db.Column(db.String(50), nullable=True) # e.g., 'QR_CODE', 'MANUAL'

    activity = db.relationship('Activity', backref='check_ins')
    student = db.relationship('Student', backref='check_ins')

    __table_args__ = (db.UniqueConstraint('activity_id', 'student_id', name='_activity_student_uc'),)

def generate_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qrcode.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_str}"


@app.route('/')
def home():
    return redirect(url_for('create_activity_page'))

@app.route('/create-activity')
def create_activity_page():
    return render_template('activity_create.html')

@app.route('/api/activities', methods=['POST'])
def create_activity():
    # app.logger.info(f"request.scheme: {request.scheme}, request.host: {request.host}, Constructed base_url: {base_url}")
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON data'}), 400

    name = data.get('name')
    description = data.get('description')
    start_time_str = data.get('start_time')
    end_time_str = data.get('end_time')
    location = data.get('location')
    created_by = data.get('created_by') # This should be an administrator ID

    if not all([name, start_time_str, end_time_str, created_by]):
        return jsonify({'message': 'Missing required fields'}), 400

    try:
        # Attempt to parse as ISO format first (e.g., YYYY-MM-DDTHH:MM:SS)
        start_time = datetime.datetime.fromisoformat(start_time_str)
        end_time = datetime.datetime.fromisoformat(end_time_str)
    except ValueError:
        try:
            # If ISO format fails, try parsing as YYYY-MM-DD
            start_time = datetime.datetime.strptime(start_time_str, '%Y-%m-%d')
            end_time = datetime.datetime.strptime(end_time_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'message': 'Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS) or YYYY-MM-DD'}), 400

    # Check if administrator exists
    admin = Administrator.query.get(created_by)
    if not admin:
        return jsonify({'message': 'Administrator not found'}), 404

    new_activity = Activity(
        name=name,
        description=description,
        start_time=start_time,
        end_time=end_time,
        location=location,
        created_by=created_by
    )

    db.session.add(new_activity)
    db.session.commit()

    # Generate QR Code after activity is committed to get its ID
    # Use request.url_root to get the absolute base URL dynamically
    # app.logger.debug(f"request.url_root: {request.url_root}")
    # qr_data = f"{request.url_root.rstrip('/')}/activity/{new_activity.id}/signin" # Absolute URL to signin page
    app_base_url = app.config['APP_BASE_URL']
    qr_data = f"{app_base_url}/activity/{new_activity.id}/signin" # Absolute URL to signin page
    app.logger.debug(f"QR Code data generated: {qr_data}") # Re-add this line

    qr_code_base64 = generate_qr_code(qr_data)

    new_activity.qr_code_url = qr_code_base64
    db.session.commit()

    return jsonify({
        'message': 'Activity created successfully',
        'activity': {
            'id': new_activity.id,
            'name': new_activity.name,
            'description': new_activity.description,
            'start_time': new_activity.start_time.isoformat(),
            'end_time': new_activity.end_time.isoformat(),
            'location': new_activity.location,
            'created_by': new_activity.created_by,
            'qr_code_url': new_activity.qr_code_url,
        'qr_data': qr_data # Add qr_data to the response
        }
    }), 201

@app.route('/activity/<int:activity_id>/signin')
def signin_page(activity_id):
    activity = Activity.query.get(activity_id)
    if not activity:
        return render_template('404.html'), 404 # You might want to create a 404.html template
    return render_template('signin.html', activity=activity)

@app.route('/api/checkin', methods=['POST'])
def check_in():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON data'}), 400

    activity_id = data.get('activity_id')
    student_id_number = data.get('student_id_number')
    student_name = data.get('student_name')
    student_email = data.get('student_email')
    student_department = data.get('student_department')
    student_birthday_str = data.get('student_birthday')
    student_unit = data.get('student_unit')
    student_title = data.get('student_title')

    if not all([activity_id, student_id_number, student_name]):
        return jsonify({'message': 'Missing required fields (activity_id, student_id_number, student_name)'}), 400

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found'}), 404

    student = Student.query.filter_by(student_id_number=student_id_number).first()
    if not student:
        # Create new student if not found
        student = Student(
            student_id_number=student_id_number,
            name=student_name,
            email=student_email,
            department=student_department,
            birthday=datetime.datetime.strptime(student_birthday_str, '%Y-%m-%d').date() if student_birthday_str else None,
            unit=student_unit,
            title=student_title
        )
        db.session.add(student)
        db.session.commit()

    # Check if student has already checked in for this activity
    existing_check_in = CheckIn.query.filter_by(activity_id=activity_id, student_id=student.id).first()
    if existing_check_in:
        return jsonify({'message': 'Student already checked in for this activity'}), 409

    new_check_in = CheckIn(
        activity_id=activity_id,
        student_id=student.id,
        check_in_time=datetime.datetime.now(),
        check_in_method='QR_CODE' # Assuming QR code scan for now
    )

    db.session.add(new_check_in)
    db.session.commit()

    return jsonify({
        'message': 'Check-in successful',
        'check_in': {
            'id': new_check_in.id,
            'activity_id': new_check_in.activity_id,
            'student_id': new_check_in.student_id,
            'check_in_time': new_check_in.check_in_time.isoformat(),
            'check_in_method': new_check_in.check_in_method
        }
    }), 201

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 5000))