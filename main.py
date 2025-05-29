import os
from flask import Flask, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError, SQLAlchemyError, DataError
from flask_cors import CORS
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
CORS(app)
CORS(app, origins=["http://localhost:5000"])

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
        print(request.form.get('name'))
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
        new_stg = StationGaugeTechnology(
            station_id=request.form.get('station_id'),
            technology_id=request.form.get('technology_id'),
            account_number=request.form.get('account_number'),
            relation_status=True
        )

        db.session.add(new_stg)
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
                    "success": "تم ربط البيانات بنجاح"
                }
            }
            return jsonify(response), 200

    return jsonify(stations=stations_list, gauges=gauges_list, techs=techs_list)


@app.route("/cancel-relation/<relation_id>")
def cancel_relation(relation_id):
    current_relation = StationGaugeTechnology.query.get(relation_id)
    if not current_relation.bills:
        db.session.delete(current_relation)
    else:
        current_relation.relation_status = False

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
                "success": "تم إلغاء ربط البيانات بنجاح"
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
        if not gauge_sgts:
            return jsonify({"error": "هذا العداد غير مرتبط بمحطة، برجاء ربط العداد أولا"}), 400
        new_bill = GuageBill(
            account_number=request.form.get('account_number'),
            bill_month=request.form.get('bill_month'),
            bill_year=request.form.get('bill_year'),
            prev_reading=request.form.get('prev_reading'),
            current_reading=request.form.get('current_reading'),
            reading_factor=request.form.get('reading_factor'),
            power_consump=request.form.get('power_consump'),
            # consump_cost=request.form.get('consump_cost'),
            fixed_installment=request.form.get('fixed_installment'),
            settlements=request.form.get('settlements'),
            stamp=request.form.get('stamp'),
            prev_payments=request.form.get('prev_payments'),
            rounding=request.form.get('rounding'),
            bill_total=request.form.get('bill_total')
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
                        current_tech_bill.technology_power_consump += new_bill.power_consump * request.form.get('percent')[i] / 100
                        current_tech_bill.technology_bill_total += new_bill.bill_total * request.form.get('percent')[i] / 100
                    else:
                        tech_bill = TechnologyBill(
                            station_guage_technology_id=gauge_sgts[i].station_guage_technology_id,
                            technology_bill_percentage=request.form.get('percent')[i],
                            technology_power_consump=new_bill.power_consump * request.form.get('percent')[i] / 100,
                            technology_bill_total=new_bill.bill_total * request.form.get('percent')[i] / 100
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
        voltage.voltage_cost = request.form.get('voltage_cost')
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
