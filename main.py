import os
from flask import Flask, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, DataError

from models import *
from flask_login import login_user, LoginManager, current_user, logout_user
from dotenv import load_dotenv
# import secrets
#
# secret_key = secrets.token_hex(32)
# print(secret_key)
'''
Install the required packages first: 
Open the Terminal in PyCharm (bottom left). 

On Windows type:
python -m pip install -r requirements.txt

On MacOS type:
pip3 install -r requirements.txt

This will install the packages from requirements.txt for this project.
'''
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_KEY")

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


# Connect to Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI")
db.init_app(app)

with app.app_context():
    db.create_all()


# Create my own decorators


@app.route("/")
def home():
    return "this is power saving website"


@app.route("/stations")
def stations():
    all_stations = db.session.query(Station).all()
    stations_list = [station.to_dict() for station in all_stations]
    return jsonify(stations_list)


@app.route("/edit-station/<station_id>", methods=["GET", "POST"])
def edit_station(station_id):
    station = Station.query.get(station_id)

    branches = db.session.query(Branch).all()
    branches_list = [branch.to_dict() for branch in branches]

    sources = db.session.query(WaterSource).all()
    sources_list = [source.to_dict() for source in sources]
    if request.method == "POST":
        station.station_name = request.form.get('name')
        station.branch_id = request.form.get('branch_id')
        station.station_type = request.form.get('station_type')
        station.station_water_capacity = request.form.get('station_water_capacity')
        station.water_source_id = request.form.get('water_source_id')
        station.station_status = request.form.get('station_status')

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            return jsonify({
                "response": {
                    "success": "تم تعديل بيانات المحطة بنجاح"
                }
            }), 200
    return jsonify(current_station=station.to_dict(), branches=branches_list, water_sources=sources_list)


@app.route("/new-station", methods=["GET", "POST"])
def add_new_station():
    branches = db.session.query(Branch).all()
    branches_list = [branch.to_dict() for branch in branches]

    sources = db.session.query(WaterSource).all()
    sources_list = [source.to_dict() for source in sources]
    if request.method == "POST":
        new_station = Station(
            station_name=request.form.get('name'),
            branch_id=request.form.get('branch_id'),
            station_type=request.form.get('station_type'),
            station_water_capacity=request.form.get('station_water_capacity'),
            water_source_id=request.form.get('water_source_id'),
            station_status=request.form.get('station_status')
        )
        db.session.add(new_station)
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            response = {
                "response": {
                    "success": "تم إضافة المحطة بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(branches=branches_list, water_sources=sources_list)


@app.route("/technologies")
def technologies():
    all_techs = db.session.query(Technology).all()
    techs_list = [tech.to_dict() for tech in all_techs]
    return jsonify(techs_list)


@app.route("/edit-tech/<tech_id>", methods=["GET", "POST"])
def edit_tech(tech_id):
    tech = Technology.query.get(tech_id)
    current_user_permissions = [permission.to_dict() for permission in current_user.group.permissions]
    if request.method == "POST":
        tech.technology_name = request.form.get('technology_name')
        tech.power_per_water = request.form.get('power_per_water')
        if any(p.permession_name == "set alum and chlorine" for p in current_user.group.permissions):
            tech.liquid_alum_per_water = request.form.get('liquid_alum_per_water')
            tech.solid_alum_per_water = request.form.get('solid_alum_per_water')
            tech.chlorine_per_water = request.form.get('chlorine_per_water')

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            return jsonify({
                "response": {
                    "success": "تم تعديل بيانات تقنية الترشيح بنجاح"
                }
            }), 200
    return jsonify(current_tech=tech.to_dict(), current_user_permissions=current_user_permissions)


@app.route("/new-tech", methods=["GET", "POST"])
def add_new_tech():
    current_user_permissions = [permission.to_dict() for permission in current_user.group.permissions]
    if request.method == "POST":
        new_tech = Technology(
            technology_name=request.form.get('technology_name'),
            power_per_water=request.form.get('power_per_water'),
        )
        if any(p.permession_name == "set alum and chlorine" for p in current_user.group.permissions):
            new_tech.liquid_alum_per_water = float(request.form.get('liquid_alum_per_water')) or None,
            new_tech.solid_alum_per_water = float(request.form.get('solid_alum_per_water')) or None,
            new_tech.chlorine_per_water = float(request.form.get('chlorine_per_water')) or None

        db.session.add(new_tech)
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            response = {
                "response": {
                    "success": "تم إضافة تقنية الترشيح بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(current_user_permissions=current_user_permissions)


@app.route("/gauges")
def gauges():
    all_gauges = db.session.query(Gauge).all()
    gauges_list = [gauge.to_dict() for gauge in all_gauges]
    return jsonify(gauges_list)


@app.route("/edit-gauge/<gauge_id>", methods=["GET", "POST"])
def edit_gauge(gauge_id):
    gauge = Gauge.query.get(gauge_id)
    voltage_types = db.session.query(Voltage).all()
    v_t_list = [v_t.to_dict() for v_t in voltage_types]
    if request.method == "POST":
        gauge.meter_id = request.form.get('meter_id')
        gauge.meter_factor = request.form.get('meter_factor')
        gauge.voltage_id = request.form.get('voltage_id')
        gauge.account_status = request.form.get('account_status')
        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            return jsonify({
                "response": {
                    "success": "تم تعديل بيانات العداد بنجاح"
                }
            }), 200
    return jsonify(current_gauge=gauge.to_dict(), voltage_types=v_t_list)


@app.route("/new-gauge", methods=["GET", "POST"])
def add_new_gauge():
    voltage_types = db.session.query(Voltage).all()
    v_t_list = [v_t.to_dict() for v_t in voltage_types]
    if request.method == "POST":
        new_gauge = Gauge(
            account_number=request.form.get('account_number'),
            meter_id=request.form.get('meter_id'),
            meter_factor=request.form.get('meter_factor'),
            final_reading=request.form.get('final_reading'),
            voltage_id=request.form.get('voltage_id'),
            account_status=request.form.get('account_status')
        )
        db.session.add(new_gauge)

        try:
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            response = {
                "response": {
                    "success": "تم إضافة العداد بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(voltage_types=v_t_list)


if __name__ == '__main__':
    app.run(debug=True)
