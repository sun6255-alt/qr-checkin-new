from app import app, db, Administrator

with app.app_context():
    db.drop_all()  # Drop all existing tables
    db.create_all() # Create tables based on updated models

    # Create a default administrator if none exists
    if not Administrator.query.filter_by(username='admin').first():
        default_admin = Administrator(username='admin', email='admin@example.com', password_hash='password') # In a real app, hash this password!
        db.session.add(default_admin)
        db.session.commit()
        print("Default administrator 'admin' created.")
    else:
        print("Default administrator 'admin' already exists.")