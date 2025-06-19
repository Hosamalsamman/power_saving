import os
from flask import Flask, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, DataError
from flask_cors import CORS
from models import *
from flask_login import login_user, LoginManager, current_user, logout_user
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

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
CORS(app)
CORS(app, origins=["http://localhost:5000"])

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(emp_code):
    return db.get_or_404(User, emp_code)


# Connect to Database
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_URI")
db.init_app(app)

with app.app_context():
    db.create_all()


# Create my own decorators and functions
def get_season(month):
    if month in range(4, 11):          # 11 is exclusive, so covers 4 to 10
        return "summer"
    else:
        return "winter"


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
    station = db.session.get(Station, station_id)

    if request.method == "POST":
        data = request.get_json()
        station.station_name = data['name']
        station.branch_id = data['branch_id']
        station.station_type = data['station_type']
        station.station_water_capacity = data['station_water_capacity']
        station.water_source_id = data['water_source_id']

        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            return jsonify({
                "response": {
                    "success": "تم تعديل بيانات المحطة بنجاح"
                }
            }), 200
    return jsonify({"response": {"success": "صل ع النبي"}})


@app.route("/new-station", methods=["GET", "POST"])
def add_new_station():
    branches = db.session.query(Branch).all()
    branches_list = [branch.to_dict() for branch in branches]

    sources = db.session.query(WaterSource).all()
    sources_list = [source.to_dict() for source in sources]
    if request.method == "POST":
        data = request.get_json()
        print(data)
        new_station = Station(
            station_name=data['name'],
            branch_id=data['branch_id'],
            station_type=data['station_type'],
            station_water_capacity=data['station_water_capacity'],
            water_source_id=data['water_source_id'],
        )
        db.session.add(new_station)
        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            print(e)
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
    tech = db.session.get(Technology, tech_id)
    if request.method == "POST":
        data = request.get_json()
        tech.technology_name = data['technology_name']
        tech.power_per_water = data['power_per_water']

        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            return jsonify({
                "response": {
                    "success": "تم تعديل بيانات تقنية الترشيح بنجاح"
                }
            }), 200
    return jsonify({"respose": "اذكر الله"})   # current_user_permissions=current_user_permissions


@app.route("/new-tech", methods=["GET", "POST"])
def add_new_tech():
    if request.method == "POST":
        data = request.get_json()
        print(data)
        new_tech = Technology(
            technology_name=data['technology_name'],
            power_per_water=data['power_per_water'],
        )

        db.session.add(new_tech)
        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            db.session.rollback()
            print(e)
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            response = {
                "response": {
                    "success": "تم إضافة تقنية الترشيح بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify({"response": "user permissions will be instead of this response"})   # current_user_permissions=current_user_permissions


@app.route("/gauges")
def gauges():
    all_gauges = db.session.query(Gauge).all()
    gauges_list = [gauge.to_dict() for gauge in all_gauges]

    return jsonify(gauges_list)


@app.route("/edit-gauge/<account_number>", methods=["GET", "POST"])
def edit_gauge(account_number):
    gauge = db.session.get(Gauge, account_number)

    if request.method == "POST":
        data = request.get_json()
        print(data)
        gauge.meter_id = data['meter_id']
        gauge.meter_factor = data['meter_factor']
        gauge.voltage_id = data['voltage_id']
        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            return jsonify({
                "response": {
                    "success": "تم تعديل بيانات العداد بنجاح"
                }
            }), 200
    return jsonify({"response": "سبحان الله"})


@app.route("/new-gauge", methods=["GET", "POST"])
def add_new_gauge():
    voltage_types = db.session.query(Voltage).all()
    v_t_list = [v_t.to_dict() for v_t in voltage_types]
    if request.method == "POST":
        data = request.get_json()
        new_gauge = Gauge(
            account_number=data['account_number'],
            meter_id=data['meter_id'],
            meter_factor=data['meter_factor'],
            final_reading=data['final_reading'],
            voltage_id=data['voltage_id']
        )
        db.session.add(new_gauge)

        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
            db.session.rollback()
            return jsonify(
                {"error": "خطأ في تكامل البيانات: قد تكون البيانات مكررة أو غير صالحة", "details": str(e)}), 400
        except DataError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في نوع البيانات أو الحجم", "details": str(e)}), 404
        except SQLAlchemyError as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "خطأ في قاعدة البيانات", "details": str(e)}), 500
        except Exception as e:
            print(e)
            db.session.rollback()
            return jsonify({"error": "حدث خطأ غير متوقع", "details": str(e)}), 503
        else:
            response = {
                "response": {
                    "success": "تم إضافة العداد بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(v_t_list)


@app.route("/stg-relations")
def stg_relations():
    all_stgs = db.session.query(StationGaugeTechnology).all()
    stgs_list = [stg.to_dict() for stg in all_stgs]

    return jsonify(stgs_list)


@app.route("/new-relation", methods=["GET", "POST"])
def add_new_stg():
    all_stations = db.session.query(Station).all()
    stations_list = [station.to_dict() for station in all_stations]

    all_gauges = db.session.query(Gauge).all()
    gauges_list = [gauge.to_dict() for gauge in all_gauges]

    all_techs = db.session.query(Technology).all()
    techs_list = [tech.to_dict() for tech in all_techs]

    if request.method == "POST":
        data = request.get_json()
        print(data)
        new_stg = StationGaugeTechnology(
            station_id=data['station_id'],
            technology_id=data['technology_id'],
            account_number=data['account_number'],
            relation_status=True
        )

        db.session.add(new_stg)
        try:
            db.session.commit()
        except IntegrityError as e:
            print(e)
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
                    "success": "تم ربط البيانات بنجاح"
                }
            }
            return jsonify(response), 200

    return jsonify(stations=stations_list, gauges=gauges_list, techs=techs_list)


@app.route("/edit-relation/<relation_id>", methods=["GET", "POST"])
def cancel_relation(relation_id):
    current_relation = db.session.query(StationGaugeTechnology).filter(StationGaugeTechnology.station_guage_technology_id == relation_id).first()
    current_relation.relation_status = not current_relation.relation_status
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
                "success": "تم تعديل البيانات بنجاح"
            }
        }
        return jsonify(response), 200


@app.route("/new-bill/<account_number>", methods=["GET", "POST"])
def add_new_bill(account_number):
    show_percent = False
    gauge_sgts = db.session.query(StationGaugeTechnology).filter(
        (StationGaugeTechnology.account_number == account_number) & (
                    StationGaugeTechnology.relation_status is True)).all()
    if len(gauge_sgts) > 1:
        show_percent = True
    gauge_sgt_list = [r.to_dict() for r in gauge_sgts]
    if request.method == "POST":
        data = request.get_json()
        if not gauge_sgts:
            return jsonify({"error": "هذا العداد غير مرتبط بمحطة، برجاء ربط العداد أولا"}), 400
        new_bill = GuageBill(
            account_number=data['account_number'],
            bill_month=data['bill_month'],
            bill_year=data['bill_year'],
            prev_reading=data['prev_reading'],
            current_reading=data['current_reading'],
            reading_factor=data['reading_factor'],
            power_consump=data['power_consump'],
            # consump_cost=data['consump_cost'],
            fixed_installment=data['fixed_installment'],
            settlements=data['settlements'],
            stamp=data['stamp'],
            prev_payments=data['prev_payments'],
            rounding=data['rounding'],
            bill_total=data['bill_total'],
            is_paid=data['is_paid']
        )
        new_bill.voltage_id = new_bill.voltage.voltage_id
        new_bill.voltage_cost = new_bill.voltage.voltage_cost
        # check prev-reading
        if new_bill.prev_reading != new_bill.guage.final_reading:
            return jsonify({"error": "القراءة السابقة غير مطابقة لآخر قراءة مسجلة لدينا"}), 400
        # check reading factor
        if new_bill.reading_factor != new_bill.guage.reading_factor:
            return jsonify({"error": "معامل العداد غير مطابق لبيانات العداد المسجلة لدينا"}), 400
        # check bill total
        calculated_bill_total = (new_bill.current_reading - new_bill.prev_reading) * new_bill.reading_factor * new_bill.voltage_cost + new_bill.fixed_installment + new_bill.settlements + new_bill.stamp - new_bill.prev_payments + new_bill.rounding

        if int(calculated_bill_total) != int(new_bill.bill_total):
            return jsonify({"error": "إجمالي الفاتورة غير مطابق لمجموع البنود المدخلة"})
        db.session.add(new_bill)
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
            new_bill.guage.final_reading = new_bill.current_reading
            db.session.commit()
            #  search station gauge technology relation then insert in technology bill the corresponding data
            # one to one relations or many to one relations
            if gauge_sgts.length == 1:
                # check if a single or multi gauges are providing for same tech
                current_tech_bill = db.session.query(TechnologyBill).filter(TechnologyBill.station_id == gauge_sgts[0].station_id, TechnologyBill.technology_id == gauge_sgts[0].technology_id, TechnologyBill.bill_month == new_bill.bill_month, TechnologyBill.bill_year == new_bill.bill_year).first()
                if current_tech_bill:
                    current_tech_bill.technology_power_consump += new_bill.power_consump
                    current_tech_bill.technology_bill_total += new_bill.bill_total
                else:
                    tech_bill = TechnologyBill(
                        station_id=gauge_sgts[0].station_id,
                        technology_id=gauge_sgts[0].technology_id,
                        bill_month=new_bill.bill_month,
                        bill_year=new_bill.bill_year,
                        technology_bill_percentage=100,
                        technology_power_consump=new_bill.power_consump,
                        technology_bill_total=new_bill.bill_total
                    )
                    db.session.add(tech_bill)
            # one to many and many to many relations
            else:
                for i in range(len(gauge_sgts)):
                    # check if a single or multi gauges are providing for same tech
                    current_tech_bill = db.session.query(TechnologyBill).filter(
                        TechnologyBill.station_id == gauge_sgts[i].station_id,
                        TechnologyBill.technology_id == gauge_sgts[i].technology_id,
                        TechnologyBill.bill_month == new_bill.bill_month,
                        TechnologyBill.bill_year == new_bill.bill_year).first()
                    if current_tech_bill:
                        current_tech_bill.technology_power_consump += new_bill.power_consump * data['percent'][i] / 100
                        current_tech_bill.technology_bill_total += new_bill.bill_total * data['percent'][i] / 100
                    else:
                        tech_bill = TechnologyBill(
                            station_guage_technology_id=gauge_sgts[i].station_guage_technology_id,
                            technology_bill_percentage=data.get('percent')[i],
                            technology_power_consump=new_bill.power_consump * data['percent'][i] / 100,
                            technology_bill_total=new_bill.bill_total * data['percent'][i] / 100
                        )
                        db.session.add(tech_bill)
            db.session.commit()
            response = {
                "response": {
                    "success": "تم إضافة الفاتورة بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(gauge_sgt_list=gauge_sgt_list, show_percent=show_percent)


@app.route("/tech-bills")
def show_tech_bills():
    all_tech_bills = db.session.query(TechnologyBill).all()
    tech_bills_list = [t_b.to_dict() for t_b in all_tech_bills]
    return jsonify(tech_bills_list)


@app.route("/edit-tech-bill/<tech_bill_id>", methods=["GET", "POST"])
def edit_tech_bill(tech_bill_id):
    bill = db.session.get(TechnologyBill, tech_bill_id)
    # make old rows uneditable
    if bill.power_per_water:
        return jsonify({"response": "لا يمكن تعديل البيانات التاريخية للنظام"}), 400

    if request.method == "POST":
        data = request.get_json()
        bill.technology_liquid_alum_consump = data['technology_liquid_chlorine_consump']
        bill.technology_solid_alum_consump = data['technology_solid_chlorine_consump']
        bill.technology_chlorine_consump = data['technology_alum_consump']
        bill.technology_water_amount = data['technology_water_amount']
        bill.power_per_water = bill.technology.power_per_water
        current_season = get_season(bill.bill_month)
        current_water_source = bill.station.water_source_id
        chemicals_ref = db.session.query(AlumChlorineReference).filter(AlumChlorineReference.technology_id == bill.technology_id,
                                                                       AlumChlorineReference.season == current_season,
                                                                       AlumChlorineReference.water_source == current_water_source).first()
        if chemicals_ref:
            bill.chlorine_range_from = chemicals_ref.chlorine_range_from
            bill.chlorine_range_to = chemicals_ref.chlorine_range_to
            bill.liquid_alum_range_from = chemicals_ref.liquid_alum_range_from
            bill.liquid_alum_range_to = chemicals_ref.liquid_alum_range_to
            bill.solid_alum_range_from = chemicals_ref.solid_alum_range_from
            bill.solid_alum_range_to = chemicals_ref.solid_alum_range_to

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
                    "success": "تم ادخال البيانات بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(bill.to_dict())


# Add route to change voltage cost
@app.route("/voltage-costs")
def voltage_costs():
    all_costs = db.session.query.get(Voltage).all()
    costs_list = [v_c.to_dict() for v_c in all_costs]
    return jsonify(costs_list)


@app.route("/edit-v-cost/<voltage_id>", methods=["get", "post"])
def edit_voltage_cost(voltage_id):
    voltage = Voltage.query.get(voltage_id)
    if request.method == "POST":
        data = request.get_json()
        voltage.voltage_cost = data['voltage_cost']
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
                    "success": "تم تعديل التعريفة بنجاح"
                }
            }
            return jsonify(response), 200

    return jsonify(voltage.to_dict())


@app.route("/chemicals")
def chemicals():
    chemicals = db.session.query(AlumChlorineReference).all()
    userschemicals_list = [chemical.to_dict() for chemical in chemicals]
    return jsonify(userschemicals_list)


@app.route("/edit-chemical/<chemical_id>", methods=["GET", "POST"])
def edit_chemical(chemical_id):
    chemical = db.session.query(AlumChlorineReference).filter(AlumChlorineReference.chemical_id == chemical_id).first()
    if request.method == "POST":
        data = request.get_json()
        chemical.technology_id = data['technology_id']
        chemical.water_source_id = data['water_source_id']
        chemical.season = data['season']
        chemical.chlorine_range_from = data['chlorine_range_from']
        chemical.chlorine_range_to = data['chlorine_range_to']
        chemical.solid_alum_range_from = data['solid_alum_range_from']
        chemical.solid_alum_range_to = data['solid_alum_range_to']
        chemical.liquid_alum_range_from = data['liquid_alum_range_from']
        chemical.liquid_alum_range_to = data['liquid_alum_range_to']
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
                    "success": "تم تعديل القيم بنجاح"
                }
            }
            return jsonify(response), 200

    return jsonify({"response": "اللهم صل على سيدنا محمد"})


@app.route("/new-chemical", methods=["GET", "POST"])
def new_chemical():
    if request.method == "POST":
        data = request.get_json()
        new_chemical_ref = AlumChlorineReference(
            technology_id=data['technology_id'],
            water_source_id=data['water_source_id'],
            season=data['season'],
            chlorine_range_from=data['chlorine_range_from'],
            chlorine_range_to=data['chlorine_range_to'],
            solid_alum_range_from=data['solid_alum_range_from'],
            solid_alum_range_to=data['solid_alum_range_to'],
            liquid_alum_range_from=data['liquid_alum_range_from'],
            liquid_alum_range_to=data['liquid_alum_range_to']
        )
        db.session.add(new_chemical_ref)
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
                    "success": "تم إدخال القيم المرجعية بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify({"response": "سبحان الله وبحمده، سبحان الله العظيم"})



@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        data = request.get_json()
        user = db.session.query(User).filter(User.username == data['username']).first()
        if user:
            return jsonify({"response": "يوجد حساب بهذا الاسم، جرب تسجيل الدخول بدلا من إنشاء حساب جديد"}), 401
        hash_and_salted_password = generate_password_hash(
            data['password'],
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            emp_code=data['emp_code'],
            emp_name=data['emp_name'],
            username=data['username'],
            userpassword=hash_and_salted_password,
            is_active=False
        )
        db.session.add(new_user)
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
                    "success": "تم إنشاء الحساب بنجاح، برجاء التواصل مع الإدارة العامة لتكنولوجيا المعلومات لتفعيل حسابك"
                }
            }
            return jsonify(response), 200
    return jsonify({"response": "الحمد لله"})


@app.route("/all-users")
def all_users():
    users = db.session.query(User).all()
    users_list = [user.to_dict() for user in users]
    return jsonify(users_list)


@app.route("/edit-user/<emp_code>", methods=["GET", "POST"])
def verify_user(emp_code):
    user = db.session.query(User, emp_code)
    groups = db.session.query(Group).all()
    groups_list = [group.to_dict() for group in groups]
    if request.method == "POST":
        data = request.get_json()
        user.emp_name = data['emp_name']
        user.group_id = data['group_id']
        user.is_active = data['is_active']
        if data['reset']:
            new_hashed_password = generate_password_hash(data['new_password'], method='pbkdf2:sha256', salt_length=8)
            user.userpassword = new_hashed_password
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
                    "success": "تم تعديل بيانات المستخدم بنجاح"
                }
            }
            return jsonify(response), 200

    return jsonify(groups_list)        #   {"response": "الله أكبر"}


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        data = request.get_json()
        user = db.session.query(User).filter(User.username == data['username']).first()

        if not user or not check_password_hash(user.password, data['password']):
            return jsonify({"response": "اسم مستخدم أو كلمة مرور خاطئة"}), 401
        else:
            if user.is_active:
                login_user(user)
                return jsonify(current_user=current_user.to_dict()), 200
            else:
                return jsonify({"response": "هذا الحساب غير مفعل، برجاء مراجعة الادارة العامة لتكنولوجيا المعلومات لتفعيل حسابك"}), 401
    return jsonify({"response": "لا إله إلا الله"})


@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if request.method == "POST":
        data = request.get_json()
        if check_password_hash(current_user.userpassword, data['old_password']):
            current_user.userpassword = generate_password_hash(data['new_password'], method='pbkdf2:sha256', salt_length=8)
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
                        "success": "تم تغيير كلمة المرور بنجاح"
                    }
                }
                return jsonify(response), 200
        else:
            return jsonify({"response": "كلمة السر الحالية خاطئة"}), 401
    return jsonify({"response": "سبحان الله وبحمده، سبحان الله العظيم"})


@app.route("/logout")
def logout():
    logout_user()
    return jsonify({"response": "لا حول ولا قوة إلا بالله العلي العظيم"})


@app.route("/groups")
def groups():
    groups = db.session.query(Group).all()
    groups_list = [group.to_dict() for group in groups]
    return jsonify(groups_list)


@app.route("/edit-group/<group_id>", methods=["GET", "POST"])
def edit_group(group_id):
    group = db.session.get(Group, group_id)
    if request.method == "POST":
        data = request.get_json()
        group.group_name = data['group_name']
        group.group_notification = data['group_notification']
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
                    "success": "تم تعديل بيانات المجموعة بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify({"response": "ربنا آتنا في الدنيا حسنة وفي الآخرة حسنة وقنا عذاب النار"})


@app.route("/new-group", methods=["GET", "POST"])
def add_new_group():
    if request.method == "POST":
        data = request.get_json()
        new_group = Group(
            group_name=data['group_name'],
            group_notification=data['group_notification']
        )
        db.session.add(new_group)
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
                    "success": "تم إضافة المجموعة بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify({"response": "اللهم اعنا على ذكرك وشكرك وحسن عبادتك"})


@app.route("/permissions")
def all_permissions():
    permissions = db.session.query(Permission).all()
    permissions_list = [permission.to_dict() for permission in permissions]
    return jsonify(permissions_list)


@app.route("/new-permission", methods=["GET", "POST"])
def add_new_permission():
    if request.method == "POST":
        data = request.get_json()
        new_permission = Permission(
            permession_name=data['permession_name']
        )
        db.session.add(new_permission)
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
                    "success": "تم إضافة الصلاحية بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify({"response": "سبحان الله"})


@app.route("/delete-permission/<permission_id>", methods=["GET", "POST"])
def delete_permission(permission_id):
    permission = db.session.get(Permission, permission_id)
    db.session.delete(permission)
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
                "success": "تم حذف الصلاحية من قاعدة البيانات بنجاح"
            }
        }
        return jsonify(response), 200


@app.route("/group-permissions")
def all_group_permissions():
    group_permissions = db.session.query(Permission).all()
    group_permissions_list = [g_p.to_dict() for g_p in group_permissions]
    return jsonify(group_permissions_list)


@app.route("/new-group-permission", methods=["GET", "POST"])
def new_group_permission():
    groups = db.session.query(Group).all()
    groups_list = [group.to_dict() for group in groups]
    permissions = db.session.query(Permission).all()
    permissions_list = [permission.to_dict() for permission in permissions]
    if request.method == "POST":
        data = request.get_json()
        new_g_p = GroupPermission(
            group_id=data['group_id'],
            permession_id=data['permession_id']
        )
        db.session.add(new_g_p)
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
                    "success": "تم إضافة الصلاحية للمجموعة بنجاح"
                }
            }
            return jsonify(response), 200

    return jsonify(groups=groups_list, permissions=permissions_list)


@app.route("/delete-group-permission/<group_id>/<permission_id>", methods=["GET", "post"])
def delete_group_permission(group_id, permission_id):
    g_p = db.session.get(GroupPermission, (group_id, permission_id))
    db.session.delete(g_p)
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
                "success": "تم حذف الصلاحية من المجموعة بنجاح"
            }
        }
        return jsonify(response), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
