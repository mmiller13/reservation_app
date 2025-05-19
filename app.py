from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# Initialize Flask App
app = Flask(__name__)

# Configure SQLite Database
# The DATABASE_URL environment variable will be set via the `docker run` command
# to point to a file within the mounted volume.
# If DATABASE_URL is not set, it defaults to 'sqlite:///reservations.db' in the app's root.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///reservations.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_very_secret_key_for_flashing_messages' # Change this in a real app

db = SQLAlchemy(app)

# Define Reservation Model
class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reservation_date = db.Column(db.String(10), nullable=False) # Store as YYYY-MM-DD string
    reservation_time = db.Column(db.String(5), nullable=False)  # Store as HH:MM string
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    num_people = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Reservation {self.name} - {self.reservation_date} {self.reservation_time}>'

# Routes
@app.route('/')
def index():
    reservations = Reservation.query.order_by(Reservation.reservation_date, Reservation.reservation_time).all()
    return render_template('index.html', reservations=reservations)

@app.route('/add', methods=['GET', 'POST'])
def add_reservation():
    if request.method == 'POST':
        try:
            reservation_date_str = request.form['reservation_date']
            reservation_time_str = request.form['reservation_time']
            name = request.form['name']
            phone = request.form['phone']
            num_people = int(request.form['num_people'])

            # Basic validation (can be expanded)
            if not all([reservation_date_str, reservation_time_str, name, phone, num_people]):
                flash('All fields are required!')
                return redirect(url_for('add_reservation'))
            
            if num_people < 1:
                flash('Number of people must be at least 1.')
                return redirect(url_for('add_reservation'))

            new_reservation = Reservation(
                reservation_date=reservation_date_str,
                reservation_time=reservation_time_str,
                name=name,
                phone=phone,
                num_people=num_people
            )
            db.session.add(new_reservation)
            db.session.commit()
            flash('Reservation added successfully!')
            return redirect(url_for('index'))
        except ValueError:
            flash('Invalid input for number of people.')
            return redirect(url_for('add_reservation'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}')
            return redirect(url_for('add_reservation'))
            
    return render_template('add_reservation.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Create database tables if they don't exist
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True is for development