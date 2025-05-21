from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import asc, desc
from datetime import datetime as dt_obj, date as date_obj_type, time as time_obj_type
import os
import click
import pytz
import re


# Initialize Flask App
app = Flask(__name__)

# Configure App and Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///reservations.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_very_secret_key_for_flashing_messages'
app.config['TARGET_TZ'] = 'America/New_York'

db = SQLAlchemy(app)

# --- Custom Jinja Filter ---
@app.template_filter('localdatetime')
def localdatetime_filter(utc_dt):
    if not utc_dt: return ""
    try:
        target_tz_str = app.config.get('TARGET_TZ', 'UTC')
        target_tz = pytz.timezone(target_tz_str)
        if utc_dt.tzinfo is None or utc_dt.tzinfo.utcoffset(utc_dt) is None:
            aware_utc_dt = pytz.utc.localize(utc_dt)
        else:
            aware_utc_dt = utc_dt.astimezone(pytz.utc)
        local_dt = aware_utc_dt.astimezone(target_tz)
        return local_dt.strftime('%m/%d/%Y %I:%M %p')
    except Exception as e:
        app.logger.error(f"Error formatting datetime: {e} for value {utc_dt}")
        try: return utc_dt.strftime('%m/%d/%Y %I:%M %p UTC')
        except: return str(utc_dt)

# --- Model Definitions ---
class Guest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    address_street = db.Column(db.String(200), nullable=True)
    address_city = db.Column(db.String(100), nullable=True)
    address_state = db.Column(db.String(50), nullable=True)
    address_zip = db.Column(db.String(20), nullable=True)
    guest_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=dt_obj.utcnow)
    updated_at = db.Column(db.DateTime, default=dt_obj.utcnow, onupdate=dt_obj.utcnow) # NEW
    reservations = db.relationship('Reservation', backref='guest', lazy=True)

    def __repr__(self):
        return f'<Guest {self.id}: {self.first_name} {self.last_name}>'

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    reservation_date = db.Column(db.Date, nullable=False)
    reservation_time = db.Column(db.Time, nullable=False)
    num_people = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=dt_obj.utcnow)
    updated_at = db.Column(db.DateTime, default=dt_obj.utcnow, onupdate=dt_obj.utcnow) # NEW
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id'), nullable=False)
    status = db.Column(db.String(20), default='active', nullable=False) # 'active', 'cancelled', 'completed', 'no-show'
    source = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        date_str = self.reservation_date.strftime("%m/%d/%Y") if self.reservation_date else "N/A"
        return f'<Reservation {self.id} ({self.status}) for Guest {self.guest.first_name} {self.guest.last_name} on {date_str}>'

# --- CLI command ---
@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        db.drop_all() 
        db.create_all()
    # Ensure to update this message if you made schema changes (e.g. added status to Reservation)
    click.echo("Initialized the database (Reservation status field confirmed/added).")


# --- Routes ---
@app.route('/')
def index():
    sort_by = request.args.get('sort_by', 'reservation_date')
    order = request.args.get('order', 'asc')
    view_status = request.args.get('view_status', 'active') # Default to 'active' (which means active & upcoming)

    query = Reservation.query.join(Guest)
    
    target_tz = pytz.timezone(app.config['TARGET_TZ'])
    today_local = dt_obj.now(target_tz).date()

    if view_status == 'active': # Active and upcoming
        query = query.filter(Reservation.status == 'active', Reservation.reservation_date >= today_local)
    elif view_status == 'past_active': # Active but in the past
        query = query.filter(Reservation.status == 'active', Reservation.reservation_date < today_local)
    elif view_status == 'cancelled':
        query = query.filter(Reservation.status == 'cancelled')
    elif view_status == 'all': # 'all' shows everything regardless of status or date
        pass # No additional status or date filter
    else: # Default to active if view_status is unknown or not 'all'
        query = query.filter(Reservation.status == 'active', Reservation.reservation_date >= today_local)
        view_status = 'active'


    if sort_by == 'reservation_date':
        order_logic = [desc(Reservation.reservation_date), desc(Reservation.reservation_time)] if order == 'desc' else \
                      [asc(Reservation.reservation_date), asc(Reservation.reservation_time)]
    elif sort_by == 'guest_name':
        order_logic = [desc(Guest.last_name), desc(Guest.first_name)] if order == 'desc' else \
                      [asc(Guest.last_name), asc(Guest.first_name)]
    elif sort_by == 'num_people':
        order_logic = [desc(Reservation.num_people)] if order == 'desc' else \
                      [asc(Reservation.num_people)]
    else: 
        order_logic = [asc(Reservation.reservation_date), asc(Reservation.reservation_time)]
        sort_by = 'reservation_date'
            
    query = query.order_by(*order_logic)
    reservations = query.all()
    
    return render_template('index.html', 
                           reservations=reservations, 
                           current_sort_by=sort_by, 
                           current_order=order,
                           current_view_status=view_status)

@app.route('/add', methods=['GET', 'POST'])
def add_reservation():
    if request.method == 'POST':
        try:
            # Guest details from form - NORMALIZE HERE
            raw_guest_first_name = request.form['guest_first_name']
            raw_guest_last_name = request.form['guest_last_name']
            raw_guest_phone = request.form['guest_phone']

            guest_first_name = raw_guest_first_name.strip().title() if raw_guest_first_name else ""
            guest_last_name = raw_guest_last_name.strip().title() if raw_guest_last_name else ""
            guest_phone_normalized = re.sub(r'\D', '', raw_guest_phone) if raw_guest_phone else ""


            reservation_date_str = request.form['reservation_date']
            reservation_time_str = request.form['reservation_time']
            num_people_str = request.form['num_people']
            reservation_notes = request.form['reservation_notes']

            if not all([guest_first_name, guest_last_name, guest_phone_normalized, 
                        reservation_date_str, reservation_time_str, num_people_str]):
                flash('Guest first name, last name, valid phone, date, time, and number of people are required!', 'error')
                return redirect(url_for('add_reservation'))
            
            num_people = int(num_people_str)
            if num_people < 1:
                flash('Number of people must be at least 1.', 'error')
                return redirect(url_for('add_reservation'))

            try:
                reservation_date_obj = dt_obj.strptime(reservation_date_str, '%Y-%m-%d').date()
                reservation_time_obj = dt_obj.strptime(reservation_time_str, '%H:%M').time()
            except ValueError:
                flash('Invalid date or time format. Please use YY YY-MM-DD for date and HH:MM for time.', 'error')
                return redirect(url_for('add_reservation'))

            # Find or Create Guest using NORMALIZED values
            guest = Guest.query.filter_by(
                first_name=guest_first_name, 
                last_name=guest_last_name, 
                phone=guest_phone_normalized # Query with normalized phone
            ).first()

            if not guest:
                guest = Guest(
                    first_name=guest_first_name, # Store normalized (Title Case)
                    last_name=guest_last_name,   # Store normalized (Title Case)
                    phone=guest_phone_normalized # Store normalized (digits only)
                    # email, address, guest_notes would be set here if collected
                )
                db.session.add(guest)
                db.session.flush() 

            new_reservation = Reservation(
                reservation_date=reservation_date_obj,
                reservation_time=reservation_time_obj,
                num_people=num_people,
                notes=reservation_notes,
                guest_id=guest.id,
                status='active'
                source='Staff Input' # Or 'Phone', 'Internal', etc. 
            )
            db.session.add(new_reservation)
            db.session.commit()
            flash('Reservation added successfully!', 'success')
            return redirect(url_for('index'))
        except ValueError as ve:
            db.session.rollback(); flash(f'Invalid input: {ve}', 'error'); return redirect(url_for('add_reservation'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error adding reservation: {e}\nRequest form data: {request.form}", exc_info=True)
            flash(f'An unexpected error occurred. Please check logs.', 'error'); return redirect(url_for('add_reservation'))
    return render_template('add_reservation.html')

@app.route('/reservation/<int:reservation_id>/edit', methods=['GET', 'POST'])
def edit_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status == 'cancelled':
        flash('Cannot edit a cancelled reservation.', 'error')
        return redirect(url_for('index', view_status='cancelled'))

    if request.method == 'POST':
        try:
            # NORMALIZE guest details from form before updating
            raw_guest_first_name = request.form['guest_first_name']
            raw_guest_last_name = request.form['guest_last_name']
            raw_guest_phone = request.form['guest_phone']

            guest_first_name = raw_guest_first_name.strip().title() if raw_guest_first_name else ""
            guest_last_name = raw_guest_last_name.strip().title() if raw_guest_last_name else ""
            guest_phone_normalized = re.sub(r'\D', '', raw_guest_phone) if raw_guest_phone else ""

            # Update Guest details - check if this new normalized info matches another existing guest
            # This is a simplified update: it updates the current guest.
            # A more complex scenario would involve checking if the NEW normalized details
            # match a DIFFERENT existing guest, and then deciding whether to link to them
            # or signal a potential duplicate. For now, we update the current reservation's guest.
            
            current_guest = reservation.guest
            # Check if the normalized details match another *different* existing guest
            if guest_first_name and guest_last_name and guest_phone_normalized:
                other_guest = Guest.query.filter(
                    Guest.id != current_guest.id, # Not the current guest
                    Guest.first_name == guest_first_name,
                    Guest.last_name == guest_last_name,
                    Guest.phone == guest_phone_normalized
                ).first()
                if other_guest:
                    flash(f'Warning: Another guest already exists with the name "{guest_first_name} {guest_last_name}" and phone "{raw_guest_phone}". Reservation not updated to prevent duplicate guest linkage. Please use unique guest details or find the existing guest to assign this reservation.', 'warning')
                    return render_template('edit_reservation.html', reservation=reservation) # Re-render with original data

            current_guest.first_name = guest_first_name
            current_guest.last_name = guest_last_name
            current_guest.phone = guest_phone_normalized
            # Note: email, address fields for guest are not on this form, so not updated here.

            # Update Reservation details
            reservation_date_str = request.form['reservation_date']
            reservation_time_str = request.form['reservation_time']
            
            if not all([current_guest.first_name, current_guest.last_name, current_guest.phone, 
                        reservation_date_str, reservation_time_str, request.form['num_people']]):
                flash('Guest first name, last name, valid phone, date, time, and number of people are required!', 'error')
                return render_template('edit_reservation.html', reservation=reservation)

            reservation.num_people = int(request.form['num_people'])
            if reservation.num_people < 1:
                flash('Number of people must be at least 1.', 'error')
                return render_template('edit_reservation.html', reservation=reservation)

            try:
                reservation.reservation_date = dt_obj.strptime(reservation_date_str, '%Y-%m-%d').date()
                reservation.reservation_time = dt_obj.strptime(reservation_time_str, '%H:%M').time()
            except ValueError:
                flash('Invalid date or time format. Please use YY YY-MM-DD for date and HH:MM for time.', 'error')
                return render_template('edit_reservation.html', reservation=reservation)
            reservation.notes = request.form['reservation_notes']
            
            db.session.commit()
            flash('Reservation updated successfully!', 'success')
            return redirect(url_for('index', view_status='active')) 
        except ValueError as ve:
            db.session.rollback(); flash(f'Invalid input: {ve}', 'error')
            return render_template('edit_reservation.html', reservation=reservation)
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating reservation {reservation_id}: {e}\nRequest form data: {request.form}", exc_info=True)
            flash(f'An unexpected error occurred. Please check logs.', 'error')
            return render_template('edit_reservation.html', reservation=reservation)
    # GET request: show the form pre-filled with data
    # The guest.phone will be displayed as digits-only if that's how it's stored.
    return render_template('edit_reservation.html', reservation=reservation)

@app.route('/reservation/<int:reservation_id>/cancel', methods=['POST'])
def cancel_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    try:
        reservation.status = 'cancelled'
        db.session.commit()
        flash('Reservation has been cancelled.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error cancelling reservation {reservation_id}: {e}", exc_info=True)
        flash('Error cancelling reservation. Please check logs.', 'error')
    return redirect(url_for('index', view_status='active'))

# --- NEW: Reactivate (Uncancel) Reservation Route ---
@app.route('/reservation/<int:reservation_id>/reactivate', methods=['POST'])
def reactivate_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    if reservation.status == 'cancelled':
        try:
            reservation.status = 'active'
            # You might want to add logic here if reactivating a past reservation.
            # For example, should its date be updated? For now, just reactivates.
            db.session.commit()
            flash('Reservation has been reactivated.', 'success')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error reactivating reservation {reservation_id}: {e}", exc_info=True)
            flash('Error reactivating reservation. Please check logs.', 'error')
    else:
        flash('This reservation is not currently cancelled.', 'info')
    
    return redirect(url_for('index', view_status='cancelled')) # Or view_status='active'