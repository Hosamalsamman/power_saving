import os
from decimal import Decimal

from flask import Flask, jsonify, render_template, request
from sqlalchemy import and_, or_, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, DataError
from flask_cors import CORS
from models import *
from flask_login import login_user, LoginManager, current_user, logout_user, login_required
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # ← force headless, non‑GUI backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io
import base64
import arabic_reshaper
from bidi.algorithm import get_display
import seaborn as sns
from sklearn.linear_model import LinearRegression
import pyodbc

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
    if month in range(4, 11):  # 11 is exclusive, so covers 4 to 10
        return "summer"
    else:
        return "winter"


@app.route("/")
def home():
    current_year = datetime.now().year
    current_year_tech_bills = db.session.query(TechnologyBill).filter(
        TechnologyBill.bill_year == current_year,
        TechnologyBill.technology_bill_percentage != None
    ).all()
    if current_year_tech_bills:
        bills_list = [row.to_dict() for row in current_year_tech_bills]
        df_bills = pd.DataFrame(bills_list)
        df_bills.fillna(0, inplace=True)
        df_bills.infer_objects(copy=False)
        # Show all columns
        pd.set_option('display.max_columns', None)
        df_bills.technology_bill_total = pd.to_numeric(df_bills.technology_bill_total)
        totals = {
            "power": float(df_bills['technology_power_consump'].sum()),
            "water": float(df_bills['technology_water_amount'].sum()),
            "money": float(df_bills['technology_bill_total'].sum()),
            "chlorine": float(df_bills['technology_chlorine_consump'].sum()),
            "solid_alum": float(df_bills['technology_solid_alum_consump'].sum()),
            "liquid_alum": float(df_bills['technology_liquid_alum_consump'].sum())
        }
        current_month = datetime.now().month - 1
        if current_month == 0:
            current_month = 12
            current_year -= 1
        current_month_bills = db.session.query(TechnologyBill).filter(
            TechnologyBill.bill_month == current_month,
            TechnologyBill.bill_year == current_year).all()
        over_power_consump = []
        over_chlorine_consump = []
        over_solid_alum_consump = []
        over_liquid_alum_consump = []
        for bill in current_month_bills:
            if bill.power_per_water:
                if bill.technology_bill_percentage and (bill.technology_power_consump / bill.technology_water_amount > bill.power_per_water):
                    over_power_consump.append(bill.to_dict())
                if bill.chlorine_range_to and ((bill.technology_chlorine_consump / bill.technology_water_amount) > bill.chlorine_range_to or (
                        bill.technology_chlorine_consump / bill.technology_water_amount) < bill.chlorine_range_from):
                    over_chlorine_consump.append(bill.to_dict())
                if bill.solid_alum_range_to and ((bill.technology_solid_alum_consump / bill.technology_water_amount) > bill.solid_alum_range_to or (
                        bill.technology_solid_alum_consump / bill.technology_water_amount) < bill.solid_alum_range_from):
                    over_solid_alum_consump.append(bill.to_dict())
                if bill.liquid_alum_range_to and ((bill.technology_liquid_alum_consump / bill.technology_water_amount) > bill.liquid_alum_range_to or (
                        bill.technology_liquid_alum_consump / bill.technology_water_amount) < bill.liquid_alum_range_from):
                    over_liquid_alum_consump.append(bill.to_dict())

        return jsonify(
            power=totals['power'],
            water=totals['water'],
            money=totals['money'],
            chlorine=totals['chlorine'],
            solid_alum=totals['solid_alum'],
            liquid_alum=totals['liquid_alum'],
            over_power_consump=over_power_consump,
            over_chlorine_consump=over_chlorine_consump,
            over_solid_alum_consump=over_solid_alum_consump,
            over_liquid_alum_consump=over_liquid_alum_consump
        )

    return jsonify({"message": "برجاء تسجيل الفواتير لمتابعة الاستهلاكات السنوية"})


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
        print(data)
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
        print(data)
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
    return jsonify({"respose": "اذكر الله"})  # current_user_permissions=current_user_permissions


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
    return jsonify({
        "response": "user permissions will be instead of this response"})  # current_user_permissions=current_user_permissions


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
        print(data)
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
    current_relation = db.session.query(StationGaugeTechnology).filter(
        StationGaugeTechnology.station_guage_technology_id == relation_id).first()
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
    # show_percent = False
    gauge_sgts = db.session.query(StationGaugeTechnology).filter(
        and_(
            StationGaugeTechnology.account_number == account_number,
            StationGaugeTechnology.relation_status == True
        )
    ).all()

    # if len(gauge_sgts) > 1:
    #     show_percent = True
    gauge_sgt_list = [r.to_dict() for r in gauge_sgts]
    print(gauge_sgt_list)
    if not gauge_sgts:
        return jsonify(gauge_sgt_list=gauge_sgt_list,
                       error={"error": "هذا العداد غير مرتبط بمحطة، برجاء ربط العداد أولا"}), 409
    if request.method == "POST":
        data = request.get_json()
        print(data)

        gauge = db.session.get(Gauge, account_number)
        new_bill = GuageBill(
            account_number=account_number,
            bill_month=data['bill_month'],
            bill_year=data['bill_year'],
            prev_reading=data['prev_reading'],
            current_reading=data['current_reading'],
            reading_factor=data['reading_factor'],
            power_consump=data['power_consump'],
            voltage_id=gauge.voltage_id,
            voltage_cost=gauge.voltage.voltage_cost,
            consump_cost=data['power_consump'] * gauge.voltage.voltage_cost,
            fixed_installment=data['fixed_installment'],
            settlements=data['settlements'],
            settlement_qty=data['settlement_qty'],
            stamp=data['stamp'],
            prev_payments=data['prev_payments'],
            rounding=data['rounding'],
            bill_total=data['bill_total'],
            is_paid=data['is_paid'],
            notes=data['notes'],
            delay_month=data['delay_month'],
            delay_year=data['delay_year']
        )
        # check prev-reading
        if new_bill.prev_reading != gauge.final_reading:
            return jsonify({"error": "القراءة السابقة غير مطابقة لآخر قراءة مسجلة لدينا"}), 410
        # check reading factor
        if new_bill.reading_factor != gauge.meter_factor:
            return jsonify({"error": "معامل العداد غير مطابق لبيانات العداد المسجلة لدينا"}), 411
        # check bill total
        # print(f"{gauge.voltage.voltage_cost} type{type(gauge.voltage.voltage_cost)}")
        reading_diff = new_bill.current_reading - new_bill.prev_reading
        if reading_diff < 0:
            # Calculate how many digits the previous reading has
            num_digits = len(str(int(new_bill.prev_reading)))
            # Compute the rollover value (e.g., 9999 for 4 digits)
            rollover = 10 ** num_digits - 1
            reading_diff += rollover

        calculated_bill_total = (
                (Decimal(str(reading_diff))) *
                Decimal(str(new_bill.reading_factor)) *
                Decimal(str(new_bill.voltage_cost)) +
                Decimal(str(gauge.voltage.fixed_fee)) +
                Decimal(str(new_bill.fixed_installment)) +
                Decimal(str(new_bill.settlements)) +
                Decimal(str(new_bill.stamp)) -
                Decimal(str(new_bill.prev_payments)) +
                Decimal(str(new_bill.rounding))
        )
        # Convert all values to Decimal
        current_reading = Decimal(new_bill.current_reading)
        prev_reading = Decimal(new_bill.prev_reading)
        reading_factor = Decimal(new_bill.reading_factor)
        voltage_cost = Decimal(new_bill.voltage_cost)
        fixed_installment = Decimal(new_bill.fixed_installment)
        settlements = Decimal(new_bill.settlements)
        stamp = Decimal(str(new_bill.stamp))
        prev_payments = Decimal(new_bill.prev_payments)
        rounding = Decimal(str(new_bill.rounding))

        # Print all values
        print(f"power consump       : {reading_diff * reading_factor}")
        print(f"Current Reading     : {current_reading}")
        print(f"Previous Reading    : {prev_reading}")
        print(f"Reading Factor      : {reading_factor}")
        print(f"Voltage Cost        : {voltage_cost}")
        print(f"Fixed Installment   : {fixed_installment}")
        print(f"Settlements         : {settlements}")
        print(f"Stamp               : {stamp}")
        print(f"Previous Payments   : {prev_payments}")
        print(f"Rounding            : {rounding}")
        print(calculated_bill_total)
        if int(calculated_bill_total) - int(new_bill.bill_total) not in range(-1, 2):
            return jsonify({
                "error": "إجمالي الفاتورة غير مطابق لمجموع البنود المدخلة، برجاء مراجعة بنود الفاتورة وتعريفة الجهد لهذا العداد"}), 412

        # # check sum of power consump and bill total for all techs == power consump and bill total for the gauge
        # if show_percent:
        #     if (not data['percent_power']
        #             or not data['percent_money']
        #             or (round(sum(data['percent_power'])) != round(data['power_consump']))
        #             or (round(sum(data['percent_money'])) != round(data['bill_total']))):
        #         return jsonify({"error": "توزيع كميات الطاقة أو القيمة لا يساوي المجموع المدخل"}), 413

        db.session.add(new_bill)
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
            print(e)
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
            if len(gauge_sgts) == 1:
                # check if a single or multi gauges are providing for same tech
                current_tech_bill = db.session.query(TechnologyBill).filter(
                    TechnologyBill.station_id == gauge_sgts[0].station_id,
                    TechnologyBill.technology_id == gauge_sgts[0].technology_id,
                    TechnologyBill.bill_month == new_bill.bill_month,
                    TechnologyBill.bill_year == new_bill.bill_year).first()
                if current_tech_bill:
                    current_tech_bill.technology_power_consump += new_bill.power_consump
                    current_tech_bill.technology_bill_total += new_bill.bill_total
                else:
                    tech_bill = TechnologyBill(
                        station_id=gauge_sgts[0].station_id,
                        technology_id=gauge_sgts[0].technology_id,
                        bill_month=new_bill.bill_month,
                        bill_year=new_bill.bill_year,
                        technology_power_consump=new_bill.power_consump,
                        technology_bill_total=new_bill.bill_total,
                        technology_bill_percentage=100
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
                        if not current_tech_bill.technology_bill_percentage:
                            current_tech_bill.technology_power_consump += new_bill.power_consump  #add it any way and divide it according to water amount
                            current_tech_bill.technology_bill_total += new_bill.bill_total  #add it any way and divide it according to water amount
                        else:
                            current_tech_bill.technology_power_consump += new_bill.power_consump * current_tech_bill.technology_bill_percentage / 100
                            current_tech_bill.technology_bill_total += Decimal(float(new_bill.bill_total) * current_tech_bill.technology_bill_percentage / 100)
                    else:
                        tech_bill = TechnologyBill(
                            station_id=gauge_sgts[i].station_id,
                            technology_id=gauge_sgts[i].technology_id,
                            bill_month=new_bill.bill_month,
                            bill_year=new_bill.bill_year,
                            technology_power_consump=new_bill.power_consump,    #add it any way and divide it according to water amount
                            technology_bill_total=new_bill.bill_total           #add it any way and divide it according to water amount
                        )
                        db.session.add(tech_bill)
            db.session.commit()
            response = {
                "response": {
                    "success": "تم إضافة الفاتورة بنجاح"
                }
            }
            return jsonify(response), 200
    return jsonify(gauge_sgt_list=gauge_sgt_list)  #, show_percent=show_percent


@app.route("/tech-bills")
def show_null_tech_bills():
    # Comprehensive check for various "empty" values
    all_tech_bills = db.session.query(TechnologyBill).filter(
        TechnologyBill.technology_water_amount == None
    ).all()
    tech_bills_list = [t_b.to_dict() for t_b in all_tech_bills]
    print(tech_bills_list)
    return jsonify(tech_bills_list)


@app.route("/edit-tech-bill/<tech_bill_id>", methods=["GET", "POST"])
def edit_tech_bill(tech_bill_id):
    bill = db.session.query(TechnologyBill).filter(TechnologyBill.tech_bill_id == tech_bill_id).first()
    # make old rows uneditable
    # if bill.technology_bill_percentage:
    #     return jsonify({"response": "لا يمكن تعديل البيانات التاريخية للنظام"}), 420

    if request.method == "POST":
        data = request.get_json()
        # if data['technology_water_amount'] == 0:
        #     return jsonify({"error": "يجب أن تكون كمية المياه المنتجة اكبر من صفر"})
        # if data['technology_chlorine_consump'] == 0:
        #     return jsonify({"error": "يجب أن تكون كمية الكلور المستهلكة اكبر من صفر"})
        bill.technology_liquid_alum_consump = data['technology_liquid_alum_consump']
        bill.technology_solid_alum_consump = data['technology_solid_alum_consump']
        bill.technology_chlorine_consump = data['technology_chlorine_consump']
        bill.technology_water_amount = data['technology_water_amount']
        bill.power_per_water = bill.technology.power_per_water
        current_season = get_season(bill.bill_month)
        current_water_source = bill.station.water_source_id
        chemicals_ref = db.session.query(AlumChlorineReference).filter(
            AlumChlorineReference.technology_id == bill.technology_id,
            AlumChlorineReference.season == current_season,
            AlumChlorineReference.water_source_id == current_water_source).first()
        if chemicals_ref:
            bill.chlorine_range_from = chemicals_ref.chlorine_range_from
            bill.chlorine_range_to = chemicals_ref.chlorine_range_to
            bill.liquid_alum_range_from = chemicals_ref.liquid_alum_range_from
            bill.liquid_alum_range_to = chemicals_ref.liquid_alum_range_to
            bill.solid_alum_range_from = chemicals_ref.solid_alum_range_from
            bill.solid_alum_range_to = chemicals_ref.solid_alum_range_to

        if not bill.technology_bill_percentage:
            # get related tech bills of related gauge
            sgt = db.session.query(StationGaugeTechnology).filter(
                StationGaugeTechnology.station_id == bill.station_id,
                StationGaugeTechnology.technology_id == bill.technology_id).first()
            print(sgt.to_dict())
            gauge_sgts = db.session.query(StationGaugeTechnology).filter(
                StationGaugeTechnology.account_number == sgt.account_number,
                StationGaugeTechnology.relation_status == True).all()
            print(gauge_sgts)
            related_bills = []
            for gauge_sgt in gauge_sgts:
                related_bill = db.session.query(TechnologyBill).filter(
                    TechnologyBill.station_id == gauge_sgt.station_id,
                    TechnologyBill.technology_id == gauge_sgt.technology_id,
                    TechnologyBill.bill_month == bill.bill_month,
                    TechnologyBill.bill_year == bill.bill_year
                ).first()
                related_bills.append(related_bill)
            print(related_bills)
            # check if all bills have water amount values
            # calculate total amount
            should_calculate = True
            total_water_amount = 0
            for this_bill in related_bills:
                if this_bill.technology_water_amount:
                    total_water_amount += this_bill.technology_water_amount
                else:
                    should_calculate = False
            # calculate percent for each tech bill
            # apply for power and bill
            if should_calculate:
                for each_bill in related_bills:
                    each_bill.technology_bill_percentage = float(Decimal(str(each_bill.technology_water_amount)) / Decimal(str(total_water_amount)) * 100)
                    each_bill.technology_power_consump = float(Decimal(str(each_bill.technology_water_amount)) / Decimal(str(total_water_amount)) * Decimal(str(each_bill.technology_power_consump)))
                    each_bill.technology_bill_total = float(Decimal(str(each_bill.technology_water_amount)) / Decimal(str(total_water_amount)) * Decimal(str(each_bill.technology_bill_total)))

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
            print(e)
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
    all_costs = db.session.query(Voltage).all()
    costs_list = [v_c.to_dict() for v_c in all_costs]
    return jsonify(costs_list)


@app.route("/edit-v-cost/<voltage_id>", methods=["get", "post"])
def edit_voltage_cost(voltage_id):
    voltage = Voltage.query.get(voltage_id)
    if request.method == "POST":
        data = request.get_json()
        print(data)
        voltage.voltage_cost = data['voltage_cost']
        voltage.fixed_fee = data['fixed_fee']
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
        if chemical.chlorine_range_from > chemical.chlorine_range_to or chemical.solid_alum_range_from > chemical.solid_alum_range_to or chemical.liquid_alum_range_from > chemical.liquid_alum_range_to:
            return jsonify({"error": "قيمة من يجب أن تكون أصغر من قيمة إلى"}), 404
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
    all_techs = db.session.query(Technology).all()
    techs_list = [tech.to_dict() for tech in all_techs]

    water_sources = db.session.query(WaterSource).all()
    sources_list = [source.to_dict() for source in water_sources]
    if request.method == "POST":
        data = request.get_json()
        print(data)
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
        if new_chemical_ref.chlorine_range_from > new_chemical_ref.chlorine_range_to or new_chemical_ref.solid_alum_range_from > new_chemical_ref.solid_alum_range_to or new_chemical_ref.liquid_alum_range_from > new_chemical_ref.liquid_alum_range_to:
            return jsonify({"error": "قيمة من يجب أن تكون أصغر من قيمة إلى"}), 404
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
    return jsonify(techs=techs_list, water_sources=sources_list)


@app.route("/station-techs")
def show_station_techs():
    stations = db.session.query(Station).all()
    stations_list = []
    for i in range(len(stations)):
        stations_list.append(stations[i].to_dict())
        stations_list[i]['techs'] = []
        for station_tech in stations[i].station_techs:
            if station_tech.technology.to_dict() not in stations_list[i]['techs']:
                stations_list[i]['techs'].append(station_tech.technology.to_dict())

    return jsonify(stations_list)


@app.route("/analysis-single/<station_id>/<tech_id>")
def show_charts(station_id, tech_id):
    tech_bills = db.session.query(TechnologyBill).filter(
        TechnologyBill.station_id == station_id,
        TechnologyBill.technology_id == tech_id
    ).all()
    bills_list = [row.to_dict() for row in tech_bills]
    df_bills = pd.DataFrame(bills_list)
    df_bills.dropna(inplace=True)
    df_bills.infer_objects(copy=False)
    # Show all columns
    pd.set_option('display.max_columns', None)
    df_bills.technology_bill_total = pd.to_numeric(df_bills.technology_bill_total)
    # add date column
    df_bills['date'] = pd.to_datetime(
        dict(
            year=df_bills['bill_year'],
            month=df_bills['bill_month'],
            day=1  # first of each month
        )
    )
    df_bills = df_bills.sort_values('date')
    print(df_bills)

    # power plot
    plt.figure(figsize=(12, 6), dpi=120)
    plt.title(get_display(arabic_reshaper.reshape('منحنى تغير معامل القدرة عبر الزمن')), fontsize=18)
    plt.xticks(fontsize=14, rotation=45)
    plt.yticks(fontsize=14)
    ax1 = plt.gca()  # get current axes
    ax2 = ax1.twinx()  # Create another axis that shares the same x-axis

    ax1.set_xticks(df_bills.date)
    ax1.set_xticklabels(
        [d.strftime('%m/%Y') for d in df_bills.date],
        rotation=45,
        fontsize=12
    )

    ax1.plot(df_bills.date, (df_bills.technology_power_consump / df_bills.technology_water_amount), color='blue',
             linewidth=3, marker="o", label=get_display(arabic_reshaper.reshape('معامل القدرة الفعلي')))
    ax2.plot(df_bills.date, df_bills.power_per_water, 'green', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('معامل القدرة القياسي')))
    ax1.grid(color='grey', linestyle='--')
    ax1.set_xlabel('شهر/سنة', fontsize=14)
    ax1.set_ylabel(get_display(arabic_reshaper.reshape('معامل القدرة الفعلي')), color='blue', fontsize=14)
    ax2.set_ylabel(get_display(arabic_reshaper.reshape('معامل القدرة القياسي')), color='green', fontsize=14)
    # ax1.set_xlim([df_bills.date.min(), df_bills.date.max()])
    # ax1.set_ylim([
    #     (df_bills.technology_power_consump / df_bills.technology_water_amount).min(),
    #     (df_bills.technology_power_consump / df_bills.technology_water_amount).max()
    # ])
    for x, y in zip(df_bills.date, df_bills.technology_power_consump / df_bills.technology_water_amount):
        ax1.text(x, y, f"{y:.4f}", fontsize=9, color='blue', ha='center', va='bottom')
    # Combine y-limits
    y_min = min((df_bills.technology_power_consump / df_bills.technology_water_amount).min(),
                df_bills.power_per_water.min())
    y_max = max((df_bills.technology_power_consump / df_bills.technology_water_amount).max(),
                df_bills.power_per_water.max())
    y_pad = (y_max - y_min) * 0.1
    y_min -= y_pad
    y_max += y_pad
    ax1.set_ylim(y_min, y_max)
    ax2.set_ylim(y_min, y_max)

    # Improve ticks
    ax1.tick_params(axis='y', labelcolor='blue')
    ax2.tick_params(axis='y', labelcolor='green')

    # Axis labels
    ax1.set_xlabel(get_display(arabic_reshaper.reshape('شهر/سنة')), fontsize=14)
    ax1.set_ylabel(get_display(arabic_reshaper.reshape('معامل القدرة الفعلي')), fontsize=14, color='blue')
    ax2.set_ylabel(get_display(arabic_reshaper.reshape('معامل القدرة القياسي')), fontsize=14, color='green')

    # Grid
    ax1.grid(color='grey', linestyle='--', alpha=0.5)

    # Legend (outside)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc='center left',
        bbox_to_anchor=(1.05, 1),
        fontsize=12
    )

    # Make room for legend
    plt.subplots_adjust(right=0.78)
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=120)
    img.seek(0)
    power_plot = base64.b64encode(img.read()).decode('utf-8')
    plt.close()
    ###########################################################################################################
    # chlorine plot
    plt.figure(figsize=(12, 6), dpi=120)
    plt.title(get_display(arabic_reshaper.reshape('منحنى تغير نسبة استهلاك الكلور عبر الزمن')), fontsize=18)
    plt.xticks(fontsize=14, rotation=45)
    plt.yticks(fontsize=14)
    ax1 = plt.gca()  # get current axes
    ax2 = ax1.twinx()  # Create another axis that shares the same x-axis

    ax1.set_xticks(df_bills.date)
    ax1.set_xticklabels(
        [d.strftime('%m/%Y') for d in df_bills.date],
        rotation=45,
        fontsize=12
    )

    ax1.plot(df_bills.date, (df_bills.technology_chlorine_consump / df_bills.technology_water_amount), color='blue',
             linewidth=3, marker="o", label=get_display(arabic_reshaper.reshape('الكلور الفعلي')))
    ax2.plot(df_bills.date, df_bills.chlorine_range_from, 'green', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('الحد الأدنى الموصى به')))
    ax2.plot(df_bills.date, df_bills.chlorine_range_to, 'red', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('الحد الأقصى الموصى به')))
    ax1.grid(color='grey', linestyle='--')
    ax1.set_xlabel(get_display(arabic_reshaper.reshape('شهر/سنة')), fontsize=14)
    ax1.set_ylabel(get_display(arabic_reshaper.reshape('معامل استهلاك الكلور الفعلي')), color='blue', fontsize=14)
    ax2.set_ylabel(get_display(arabic_reshaper.reshape('معامل استهلاك الكلور القياسي')), color='green', fontsize=14)
    ax2.set_yticks(ax1.get_yticks())
    ax2.fill_between(df_bills.date,
                     df_bills.chlorine_range_from,
                     df_bills.chlorine_range_to,
                     color='green', alpha=0.1, label=get_display(arabic_reshaper.reshape('النطاق الموصى به')))
    for x, y in zip(df_bills.date, df_bills.technology_chlorine_consump / df_bills.technology_water_amount):
        ax1.text(x, y, f"{y:.4f}", fontsize=9, color='blue', ha='center', va='bottom')
        # ax1.set_xlim([df_bills.date.min(), df_bills.date.max()])
        # Get min and max of both series
        # Combine y-limits
        y_min = min((df_bills.technology_chlorine_consump / df_bills.technology_water_amount).min(),
                    df_bills.chlorine_range_from.min())
        y_max = max((df_bills.technology_chlorine_consump / df_bills.technology_water_amount).max(),
                    df_bills.chlorine_range_to.max())
        y_pad = (y_max - y_min) * 0.1
        y_min -= y_pad
        y_max += y_pad
        ax1.set_ylim(y_min, y_max)
        ax2.set_ylim(y_min, y_max)

        # Improve ticks
        ax1.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='green')

    # Add combined legend
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines + lines2, labels + labels2,
        loc='center left',
        bbox_to_anchor=(1.05, 1),
        fontsize=12,
        borderaxespad=0.
    )
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=120)
    img.seek(0)
    chlorine_plot = base64.b64encode(img.read()).decode('utf-8')
    plt.close()
    ###########################################################################################################
    # solid alum plot
    plt.figure(figsize=(12, 6), dpi=120)
    plt.title(get_display(arabic_reshaper.reshape('منحنى تغير نسبة استهلاك الشبة الصلبة عبر الزمن')), fontsize=18)
    plt.xticks(fontsize=14, rotation=45)
    plt.yticks(fontsize=14)
    ax1 = plt.gca()  # get current axes
    ax2 = ax1.twinx()  # Create another axis that shares the same x-axis

    ax1.set_xticks(df_bills.date)
    ax1.set_xticklabels(
        [d.strftime('%m/%Y') for d in df_bills.date],
        rotation=45,
        fontsize=12
    )

    ax1.plot(df_bills.date, (df_bills.technology_solid_alum_consump / df_bills.technology_water_amount), color='blue',
             linewidth=3, marker="o", label=get_display(arabic_reshaper.reshape('الشبة الصلبة الفعلية')))
    ax2.plot(df_bills.date, df_bills.solid_alum_range_from, 'green', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('الحد الأدنى الموصى به')))
    ax2.plot(df_bills.date, df_bills.solid_alum_range_to, 'red', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('الحد الأقصى الموصى به')))
    ax1.grid(color='grey', linestyle='--')
    ax1.set_xlabel(get_display(arabic_reshaper.reshape('شهر/سنة')), fontsize=14)
    ax1.set_ylabel(get_display(arabic_reshaper.reshape('معامل استهلاك الشبة الصلبة الفعلي')), color='blue', fontsize=14)
    ax2.set_ylabel(get_display(arabic_reshaper.reshape('معامل استهلاك الشبة الصلبة القياسي')), color='green',
                   fontsize=14)
    ax2.set_yticks(ax1.get_yticks())
    ax2.fill_between(df_bills.date,
                     df_bills.solid_alum_range_from,
                     df_bills.solid_alum_range_to,
                     color='green', alpha=0.1, label=get_display(arabic_reshaper.reshape('النطاق الموصى به')))
    for x, y in zip(df_bills.date, df_bills.technology_solid_alum_consump / df_bills.technology_water_amount):
        ax1.text(x, y, f"{y:.4f}", fontsize=9, color='blue', ha='center', va='bottom')
        # ax1.set_xlim([df_bills.date.min(), df_bills.date.max()])
        # ax1.set_ylim([
        #     (df_bills.technology_solid_alum_consump / df_bills.technology_water_amount).min(),
        #     (df_bills.technology_solid_alum_consump / df_bills.technology_water_amount).max()
        # ])
        # Combine y-limits
        y_min = min((df_bills.technology_solid_alum_consump / df_bills.technology_water_amount).min(),
                    df_bills.solid_alum_range_from.min())
        y_max = max((df_bills.technology_solid_alum_consump / df_bills.technology_water_amount).max(),
                    df_bills.solid_alum_range_to.max())
        y_pad = (y_max - y_min) * 0.1
        y_min -= y_pad
        y_max += y_pad
        ax1.set_ylim(y_min, y_max)
        ax2.set_ylim(y_min, y_max)

        # Improve ticks
        ax1.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='green')

        # Add combined legend
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(
            lines + lines2, labels + labels2,
            loc='center left',
            bbox_to_anchor=(1.05, 1),
            fontsize=12,
            borderaxespad=0.
        )
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=120)
    img.seek(0)
    solid_alum_plot = base64.b64encode(img.read()).decode('utf-8')
    plt.close()
    ###########################################################################################################
    # liquid alum plot
    plt.figure(figsize=(12, 6), dpi=120)
    plt.title(get_display(arabic_reshaper.reshape('منحنى تغير نسبة استهلاك الشبة السائلة عبر الزمن')), fontsize=18)
    plt.xticks(fontsize=14, rotation=45)
    plt.yticks(fontsize=14)
    ax1 = plt.gca()  # get current axes
    ax2 = ax1.twinx()  # Create another axis that shares the same x-axis

    ax1.set_xticks(df_bills.date)
    ax1.set_xticklabels(
        [d.strftime('%m/%Y') for d in df_bills.date],
        rotation=45,
        fontsize=12
    )

    ax1.plot(df_bills.date, (df_bills.technology_liquid_alum_consump / df_bills.technology_water_amount), color='blue',
             linewidth=3, marker="o", label=get_display(arabic_reshaper.reshape('الشبة السائلة الفعلية')))
    ax2.plot(df_bills.date, df_bills.liquid_alum_range_from, 'green', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('الحد الأدنى الموصى به')))
    ax2.plot(df_bills.date, df_bills.liquid_alum_range_to, 'red', linewidth=3, linestyle='dashed',
             label=get_display(arabic_reshaper.reshape('الحد الأقصى الموصى به')))
    ax1.grid(color='grey', linestyle='--')
    ax1.set_xlabel(get_display(arabic_reshaper.reshape('شهر/سنة')), fontsize=14)
    ax1.set_ylabel(get_display(arabic_reshaper.reshape('معامل استهلاك الشبة السائلة الفعلي')), color='blue',
                   fontsize=14)
    ax2.set_ylabel(get_display(arabic_reshaper.reshape('معامل استهلاك الشبة السائلة القياسي')), color='green',
                   fontsize=14)
    ax2.set_yticks(ax1.get_yticks())
    ax2.fill_between(df_bills.date,
                     df_bills.liquid_alum_range_from,
                     df_bills.liquid_alum_range_to,
                     color='green', alpha=0.1, label=get_display(arabic_reshaper.reshape('النطاق الموصى به')))
    for x, y in zip(df_bills.date, df_bills.technology_liquid_alum_consump / df_bills.technology_water_amount):
        ax1.text(x, y, f"{y:.4f}", fontsize=9, color='blue', ha='center', va='bottom')
        # ax1.set_xlim([df_bills.date.min(), df_bills.date.max()])
        # ax1.set_ylim([
        #     (df_bills.technology_liquid_alum_consump / df_bills.technology_water_amount).min(),
        #     (df_bills.technology_liquid_alum_consump / df_bills.technology_water_amount).max()
        # ])
        # Combine y-limits
        y_min = min((df_bills.technology_liquid_alum_consump / df_bills.technology_water_amount).min(),
                    df_bills.liquid_alum_range_from.min())
        y_max = max((df_bills.technology_liquid_alum_consump / df_bills.technology_water_amount).max(),
                    df_bills.liquid_alum_range_to.max())
        y_pad = (y_max - y_min) * 0.1
        y_min -= y_pad
        y_max += y_pad
        ax1.set_ylim(y_min, y_max)
        ax2.set_ylim(y_min, y_max)

        # Improve ticks
        ax1.tick_params(axis='y', labelcolor='blue')
        ax2.tick_params(axis='y', labelcolor='green')

        # Add combined legend
        lines, labels = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(
            lines + lines2, labels + labels2,
            loc='center left',
            bbox_to_anchor=(1.05, 1),
            fontsize=12,
            borderaxespad=0.
        )
    img = io.BytesIO()
    plt.savefig(img, format='png', bbox_inches='tight', dpi=120)
    img.seek(0)
    liquid_alum_plot = base64.b64encode(img.read()).decode('utf-8')
    return jsonify(
        {
            "power_plot": power_plot,
            "chlorine_plot": chlorine_plot,
            "solid_alum_plot": solid_alum_plot,
            "liquid_alum_plot": liquid_alum_plot
        }
    )


@app.route("/annual-bills")
def show_annual_bills():
    bills = db.session.query(AnuualBill).all()
    bills_list = [bill.to_dict() for bill in bills]
    return jsonify(bills_list)


@app.route("/new-annual-bill/<meter_id>", methods=["GET", "POST"])
def new_annual_bill(meter_id):
    if request.method == "POST":
        data = request.get_json()
        print(data)
        gauge = db.session.query(Gauge).filter(Gauge.meter_id == meter_id).first()
        bills = db.session.query(GuageBill).filter(
            GuageBill.account_number == gauge.account_number,
            or_(
                and_(GuageBill.bill_year == data['financial_year'], GuageBill.bill_month > 6),
                and_(GuageBill.bill_year == data['financial_year'] + 1, GuageBill.bill_month <= 6)
            )
        ).all()
        if not bills:
            return jsonify({"error": "لا يوجد فواتير مسجلة لهذا العداد"}), 410
        calculated_total_consump = 0
        for bill in bills:
            calculated_total_consump += Decimal(str(bill.consump_cost))
        calculated_annual_bill = (data['reference_power_factor'] - data[
            'anuual_power_factor']) / 2 * calculated_total_consump + data['anuual_Rounding']
        if int(calculated_total_consump) - int(data['anuual_consump_cost']) in range(-1, 2):
            if int(calculated_annual_bill) - int(data['anuual_bill_total']) in range(-1, 2):
                annual_bill = AnuualBill(
                    account_number=gauge.account_number,
                    financial_year=data['financial_year'],
                    reference_power_factor=data['reference_power_factor'],
                    anuual_power_factor=data['anuual_power_factor'],
                    anuual_consump_cost=data['anuual_consump_cost'],
                    anuual_Rounding=data['anuual_Rounding'],
                    anuual_bill_total=data['anuual_bill_total']
                )
                db.session.add(annual_bill)
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
                            "success": "تم إدخال الفاتورة السنوية بنجاح"
                        }
                    }
                    return jsonify(response), 200
            else:
                return jsonify({"error": f"{calculated_annual_bill}الإجمالي غير مطابق للبنود المدخلة "}), 406
        else:
            return jsonify({
                               "error": f"{calculated_total_consump}قيمة الاستهلاك الكلي لا يساوي مجموع الفواتير المسجلة لدينا "}), 405
    return jsonify({"response": "لا إله إلا الله وحده لا شريك له له الملك وله الحمد وهو على كل شيء قدير"})


@app.route("/prediction/<station_id>")
def predict(station_id):
    station_bills = db.session.query(TechnologyBill).filter(
        TechnologyBill.station_id == station_id,
        TechnologyBill.technology_water_amount != None
    ).all()
    if not station_bills:
        return jsonify({"error": "لا يوجد بيانات لهذه المحطة"}), 410
    bills_list = [bill.to_dict() for bill in station_bills]

    df_bills = pd.DataFrame(bills_list)
    df_year_bills = df_bills.groupby(['station_id', 'bill_year'], as_index=False).agg(
        {'technology_water_amount': pd.Series.mean}
    )
    print(df_year_bills)
    plt.figure(figsize=(8, 4), dpi=200)
    with sns.axes_style("darkgrid"):
        ax = sns.regplot(data=df_year_bills,
                         x='bill_year',
                         y='technology_water_amount',
                         scatter_kws={'alpha': 0.4,
                                      'color': '#2f4b7c'},
                         line_kws={'color': '#ff7c43'})
    ax.set(
        ylabel=f'{get_display(arabic_reshaper.reshape('المياه المنتجة'))}',
        xlabel=f'{get_display(arabic_reshaper.reshape('السنوات'))}',
    )
    # Save to BytesIO buffer
    img = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img, format='png', dpi=200, bbox_inches='tight')
    img.seek(0)  # Rewind the buffer

    # Encode image to Base64
    prediction_base64 = base64.b64encode(img.read()).decode('utf-8')

    regression = LinearRegression()

    # Explanatory Variable(s) or Feature(s)
    X = pd.DataFrame(df_year_bills, columns=['bill_year'])

    # Response Variable or Target
    y = pd.DataFrame(df_year_bills, columns=['technology_water_amount'])

    # Find the best-fit line
    regression.fit(X, y)

    # theta zero
    print(f"The intercept is: {regression.intercept_[0]}")
    # theta one
    print(f"The slope coeficient is: {regression.coef_[0]}")

    # R-squared
    points_represented = regression.score(X, y)

    max_water_amount = station_bills[0].station.station_water_capacity * 30
    expected_year = (max_water_amount - regression.intercept_[0]) / regression.coef_[0, 0]
    result = {
        "prediction_plot": prediction_base64,
        "water_capacity": max_water_amount,
        "represented_points": points_represented * 100,
        "expected_year": expected_year
    }
    return jsonify(result)


@app.route("/reports", methods=["GET", "POST"])
@login_required
def show_reports():
    if request.method == "POST":
        data = request.get_json()
        if current_user.group_id == 1 or current_user.group_id == 2:  # Administrators or Tech-office
            if data['report_name'] == "branch":
                # Use parentheses instead of backslashes
                query = db.session.query(
                    Branch.branch_name,
                    TechnologyBill.bill_year,
                    TechnologyBill.bill_month,
                    func.sum(TechnologyBill.technology_bill_total).label("total_bill"),
                    func.sum(TechnologyBill.technology_water_amount).label("total_water"),
                    func.sum(TechnologyBill.technology_power_consump).label("total_power"),
                    func.sum(TechnologyBill.technology_chlorine_consump).label("total_chlorine"),
                    func.sum(TechnologyBill.technology_liquid_alum_consump).label("total_liquid_alum"),
                    func.sum(TechnologyBill.technology_solid_alum_consump).label("total_solid_alum")
                )
                # Complex date range across years
                query = query.filter(
                    or_(
                        and_(TechnologyBill.bill_year == data['start_year'], TechnologyBill.bill_month >= data['start_month']),
                        and_(TechnologyBill.bill_year > data['start_year'], TechnologyBill.bill_year < data['end_year']),
                        and_(TechnologyBill.bill_year == data['end_year'], TechnologyBill.bill_month <= data['end_month'])
                    )
                )
                query = query.filter(TechnologyBill.technology_bill_percent.isnot(None))
                query = query.select_from(TechnologyBill)
                query = query.join(TechnologyBill.station)
                query = query.join(Station.branch)
                query = query.group_by(Branch.branch_name, TechnologyBill.bill_year, TechnologyBill.bill_month)
                bills = query.all()

                bills_list = [
                    {
                        "branch_name": bill.branch_name,
                        "year": bill.bill_year,
                        "month": bill.bill_month,
                        "total_bill": float(bill.total_bill) if bill.total_bill else 0,
                        "total_water": float(bill.total_water) if bill.total_water else 0,
                        "total_power": float(bill.total_power) if bill.total_power else 0,
                        "total_chlorine": float(bill.total_chlorine) if bill.total_chlorine else 0,
                        "total_liquid_alum": float(bill.total_liquid_alum) if bill.total_liquid_alum else 0,
                        "total_solid_alum": float(bill.total_solid_alum) if bill.total_solid_alum else 0,

                    } for bill in bills
                ]
                return jsonify(bills_list)
            elif data['report_name'] == "technology":
                query = db.session.query(
                    TechnologyBill.technology_id,
                    TechnologyBill.bill_year,
                    TechnologyBill.bill_month,
                    func.sum(TechnologyBill.technology_bill_total).label("total_bill"),
                    func.sum(TechnologyBill.technology_water_amount).label("total_water"),
                    func.sum(TechnologyBill.technology_power_consump).label("total_power"),
                    func.sum(TechnologyBill.technology_chlorine_consump).label("total_chlorine"),
                    func.sum(TechnologyBill.technology_liquid_alum_consump).label("total_liquid_alum"),
                    func.sum(TechnologyBill.technology_solid_alum_consump).label("total_solid_alum")
                )
                # Complex date range across years
                query = query.filter(
                    or_(
                        and_(TechnologyBill.bill_year == data['start_year'],
                             TechnologyBill.bill_month >= data['start_month']),
                        and_(TechnologyBill.bill_year > data['start_year'],
                             TechnologyBill.bill_year < data['end_year']),
                        and_(TechnologyBill.bill_year == data['end_year'],
                             TechnologyBill.bill_month <= data['end_month'])
                    )
                )
                query = query.filter(TechnologyBill.technology_bill_percent.isnot(None))
                query = query.select_from(TechnologyBill)
                query = query.group_by(TechnologyBill.technology_id, TechnologyBill.bill_year, TechnologyBill.bill_month)
                bills = query.all()
                bills_list = [
                    {
                        "technology_name": bill.technology.technology_name,
                        "year": bill.bill_year,
                        "month": bill.bill_month,
                        "total_bill": float(bill.total_bill) if bill.total_bill else 0,
                        "total_water": float(bill.total_water) if bill.total_water else 0,
                        "total_power": float(bill.total_power) if bill.total_power else 0,
                        "total_chlorine": float(bill.total_chlorine) if bill.total_chlorine else 0,
                        "total_liquid_alum": float(bill.total_liquid_alum) if bill.total_liquid_alum else 0,
                        "total_solid_alum": float(bill.total_solid_alum) if bill.total_solid_alum else 0,
                    } for bill in bills
                ]
                return jsonify(bills_list)

        elif current_user.group_id == 1 or current_user.group_id == 3:  # Administrators or Power-saving
            pass
    return jsonify(current_user.group.to_dict())



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.get_json()
        print(data)
        user = db.session.query(User).filter(User.username == data['username']).first()
        if user:
            return jsonify({"error": "يوجد حساب بهذا الاسم، جرب تسجيل الدخول بدلا من إنشاء حساب جديد"}), 401
        hash_and_salted_password = generate_password_hash(
            data['password'],
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            emp_code=data['emp_code'],
            emp_name=data['emp_name'],
            username=data['username'].lower(),
            userpassword=hash_and_salted_password,
            is_active=False
        )
        db.session.add(new_user)
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

    return jsonify(groups_list)  #   {"response": "الله أكبر"}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json()
        user = db.session.query(User).filter(User.username == data['username']).first()

        if not user or not check_password_hash(user.userpassword, data['password']):
            return jsonify({"error": "اسم مستخدم أو كلمة مرور خاطئة"}), 401
        else:
            if user.is_active:
                login_user(user)
                return jsonify(current_user=current_user.to_dict()), 200
            else:
                return jsonify({
                    "error": "هذا الحساب غير مفعل، برجاء مراجعة الادارة العامة لتكنولوجيا المعلومات لتفعيل حسابك"}), 410
    return jsonify({"response": "لا إله إلا الله"})


@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if request.method == "POST":
        data = request.get_json()
        if check_password_hash(current_user.userpassword, data['old_password']):
            current_user.userpassword = generate_password_hash(data['new_password'], method='pbkdf2:sha256',
                                                               salt_length=8)
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
