import os
import uuid
import qrcode
import datetime
import io
import base64
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://user:password@localhost/mydatabase')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Administrator(db.Model):
    __tablename__ = 'administrators'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    def __repr__(self):
        return f'<Administrator {self.username}>'

class Activity(db.Model):
    __tablename__ = 'activities'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(120))
    created_by = db.Column(db.Integer, db.ForeignKey('administrators.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    qr_code_url = db.Column(db.Text)

    creator = db.relationship('Administrator', backref='activities')
    check_ins = db.relationship('CheckIn', backref='activity', lazy=True)

    def __repr__(self):
        return f'<Activity {self.name}>'

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    student_id_number = db.Column(db.String(80), unique=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True)
    department = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    check_ins = db.relationship('CheckIn', backref='student', lazy=True)

    def __repr__(self):
        return f'<Student {self.name}>'

class CheckIn(db.Model):
    __tablename__ = 'check_ins'
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    check_in_time = db.Column(db.DateTime, default=db.func.current_timestamp())
    check_in_method = db.Column(db.String(50), default='QR_CODE')

    def __repr__(self):
        return f'<CheckIn {self.activity_id}-{self.student_id}>'

def generate_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
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
    qr_data = f'http://your-app-domain.onrender.com/checkin/{new_activity.id}' # Placeholder URL
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
            'qr_code_url': new_activity.qr_code_url
        }
    }), 201

@app.route('/api/checkin', methods=['POST'])
def check_in():
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Invalid JSON data'}), 400

    activity_id = data.get('activity_id')
    student_id = data.get('student_id')

    if not all([activity_id, student_id]):
        return jsonify({'message': 'Missing required fields (activity_id, student_id)'}), 400

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found'}), 404

    student = Student.query.get(student_id)
    if not student:
        return jsonify({'message': 'Student not found'}), 404

    # Check if student has already checked in for this activity
    existing_check_in = CheckIn.query.filter_by(activity_id=activity_id, student_id=student_id).first()
    if existing_check_in:
        return jsonify({'message': 'Student already checked in for this activity'}), 409

    new_check_in = CheckIn(
        activity_id=activity_id,
        student_id=student_id,
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