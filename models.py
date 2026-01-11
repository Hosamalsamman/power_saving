from decimal import Decimal

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Float, ForeignKey, NVARCHAR, Numeric, DECIMAL
from flask_login import UserMixin


class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class Branch(db.Model):
    __tablename__ = 'branches'
    branch_id = db.Column(Integer, primary_key=True)
    branch_name = db.Column(NVARCHAR(200), unique=True, nullable=False)

    stations = db.relationship('Station', back_populates='branch')
    places = db.relationship('Place', back_populates='branch')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Technology(db.Model):
    __tablename__ = 'technologies'
    technology_id = db.Column(Integer, primary_key=True, autoincrement=True)
    technology_name = db.Column(NVARCHAR(200), unique=True, nullable=False)
    power_per_water = db.Column(Float, nullable=False)
    technology_main_type = db.Column(NVARCHAR(20), nullable=False)

    station_techs = db.relationship('StationGaugeTechnology', back_populates='technology')
    technology_bills = db.relationship('TechnologyBill', back_populates='technology')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class WaterSource(db.Model):
    __tablename__ = 'water_source'
    water_source_id = db.Column(Integer, primary_key=True, autoincrement=True)
    water_source_name = db.Column(NVARCHAR(400), unique=True, nullable=False)

    stations = db.relationship('Station', back_populates='water_source')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Station(db.Model):
    __tablename__ = 'stations'
    station_id = db.Column(Integer, primary_key=True, autoincrement=True)
    station_name = db.Column(NVARCHAR(200), unique=True, nullable=False)
    branch_id = db.Column(Integer, db.ForeignKey('branches.branch_id'), nullable=False)
    station_type = db.Column(NVARCHAR(10), nullable=False)
    station_water_capacity = db.Column(Integer, nullable=False)
    water_source_id = db.Column(Integer, db.ForeignKey('water_source.water_source_id'), nullable=False)
    # TODO: should modify it to false after filling stations with it's area
    area_id = db.Column(Integer, db.ForeignKey('area_of_service.area_id'), nullable=True)

    branch = db.relationship('Branch', back_populates='stations')
    area = db.relationship('AreaOfService', back_populates='stations')
    water_source = db.relationship('WaterSource', back_populates='stations')
    station_techs = db.relationship('StationGaugeTechnology', back_populates='station')
    technology_bills = db.relationship('TechnologyBill', back_populates='station')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['branch_name'] = self.branch.branch_name if self.branch else None
        data['water_source_name'] = self.water_source.water_source_name if self.water_source else None

        return data


class Voltage(db.Model):
    __tablename__ = 'voltage'
    voltage_id = db.Column(Integer, primary_key=True, autoincrement=True)
    voltage_type = db.Column(NVARCHAR(50), nullable=False)
    voltage_cost = db.Column(Float, nullable=False)
    fixed_fee = db.Column(Float, nullable=False)

    guages = db.relationship('Gauge', back_populates='voltage')
    bills = db.relationship('GuageBill', back_populates='voltage')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Gauge(db.Model):
    __tablename__ = 'guages'
    account_number = db.Column(NVARCHAR(50), primary_key=True)
    meter_id = db.Column(NVARCHAR(50), unique=True, nullable=False)
    meter_factor = db.Column(Integer, nullable=False)
    final_reading = db.Column(Float, nullable=False)
    voltage_id = db.Column(Integer, db.ForeignKey('voltage.voltage_id'), nullable=False)

    voltage = db.relationship('Voltage', back_populates='guages')
    bills = db.relationship('GuageBill', back_populates='guage')
    station_techs = db.relationship('StationGaugeTechnology', back_populates='guage')
    anuual_bills = db.relationship('AnuualBill', back_populates='gauge')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['voltage_type'] = self.voltage.voltage_type if self.voltage else None
        data['voltage_cost'] = self.voltage.voltage_cost if self.voltage else None
        data['fixed_fee'] = self.voltage.fixed_fee if self.voltage else None
        # Since all related stations belong to the same branch
        branch_name = None
        station_set = set()
        for sgt in self.station_techs:
            if sgt.station and sgt.relation_status:
                station_set.add(sgt.station.station_name)

                # Get branch name once
                if not branch_name and sgt.station.branch:
                    branch_name = sgt.station.branch.branch_name

        data['station_names'] = ", ".join(station_set) if station_set else None
        data['station_names_list'] = list(station_set) if station_set else None
        data['branch_name'] = branch_name
        return data


class AnuualBill(db.Model):
    __tablename__ = 'anuual_bills'

    anuual_bill_id = db.Column(db.Integer, nullable=False, unique=True, autoincrement=True)
    account_number = db.Column(NVARCHAR(50), db.ForeignKey('guages.account_number'), nullable=False, primary_key=True)
    financial_year = db.Column(db.Integer, nullable=False, primary_key=True)
    reference_power_factor = db.Column(Float, nullable=False)
    anuual_power_factor = db.Column(Float, nullable=False)
    anuual_consump_cost = db.Column(Numeric(19, 4), nullable=False)
    anuual_Rounding = db.Column(Float, nullable=False)
    anuual_bill_total = db.Column(Numeric(19, 4), nullable=False)

    gauge = db.relationship('Gauge', back_populates='anuual_bills')

    # # remove this when working on sqlserver , autoincrement=True will do the job for sqlserver OR , db.Sequence('station_gauge_seq') in postgres
    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)
    #     if not self.anuual_bill_id:
    #         # Get next available ID
    #         max_id = db.session.query(db.func.max(AnuualBill.anuual_bill_id)).scalar()
    #         self.anuual_bill_id = (max_id or 0) + 1

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        return data


class StationGaugeTechnology(db.Model):
    __tablename__ = 'station_guage_technology'
    station_guage_technology_id = db.Column(db.Integer, unique=True, nullable=False, autoincrement=True, server_default=db.FetchedValue())
    station_id = db.Column(Integer, db.ForeignKey('stations.station_id'), primary_key=True)
    technology_id = db.Column(Integer, db.ForeignKey('technologies.technology_id'), primary_key=True)
    account_number = db.Column(NVARCHAR(50), db.ForeignKey('guages.account_number'), primary_key=True)
    relation_status = db.Column(Boolean, nullable=False)

    station = db.relationship('Station', back_populates='station_techs')
    technology = db.relationship('Technology', back_populates='station_techs')
    guage = db.relationship('Gauge', back_populates='station_techs')

    # # remove this when working on sqlserver , autoincrement=True will do the job for sqlserver OR , db.Sequence('station_gauge_seq') in postgres
    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)
    #     if not self.station_guage_technology_id:
    #         # Get next available ID
    #         max_id = db.session.query(db.func.max(StationGaugeTechnology.station_guage_technology_id)).scalar()
    #         self.station_guage_technology_id = (max_id or 0) + 1


    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['station_name'] = self.station.station_name if self.station else None
        data['technology_name'] = self.technology.technology_name if self.technology else None
        data['account_number'] = self.guage.account_number if self.guage else None
        data['branch_id'] = self.station.branch.branch_id if self.station else None
        data['branch_name'] = self.station.branch.branch_name if self.station else None
        return data


class GuageBill(db.Model):
    __tablename__ = 'guage_bill'
    guage_bill_id = db.Column(Integer, unique=True, nullable=False, autoincrement=True, server_default=db.FetchedValue())
    account_number = db.Column(NVARCHAR(50), db.ForeignKey('guages.account_number'), primary_key=True)
    bill_month = db.Column(Integer, primary_key=True)
    bill_year = db.Column(Integer, primary_key=True)
    prev_reading = db.Column(Float, nullable=False)
    current_reading = db.Column(Float, nullable=False)
    reading_factor = db.Column(Integer, nullable=False)
    power_consump = db.Column(Float, nullable=False)
    voltage_id = db.Column(Integer, db.ForeignKey('voltage.voltage_id'), nullable=False)
    voltage_cost = db.Column(NVARCHAR(50), nullable=False)
    consump_cost = db.Column(Numeric(19, 4), nullable=False)
    fixed_installment = db.Column(Numeric(19, 4), nullable=False)
    settlements = db.Column(Numeric(19, 4), nullable=False)
    settlement_qty = db.Column(Float, nullable=False)
    stamp = db.Column(Numeric(19, 4), nullable=False)
    prev_payments = db.Column(Numeric(19, 4), nullable=False)
    rounding = db.Column(Float, nullable=False)
    bill_total = db.Column(Numeric(19, 4), nullable=False)
    is_paid = db.Column(Boolean, nullable=False)
    notes = db.Column(NVARCHAR(4000), nullable=True)
    delay_month = db.Column(Integer, nullable=True)
    delay_year = db.Column(Integer, nullable=True)

    guage = db.relationship('Gauge', back_populates='bills')
    voltage = db.relationship('Voltage', back_populates='bills')

    # def to_dict(self):
    #     data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
    #     data['voltage_type'] = self.voltage.voltage_type if self.voltage else None
    #     return data

    def to_dict(self):
        result = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, Decimal):
                val = float(val)
            result[col.name] = val

        result['voltage_type'] = self.voltage.voltage_type if self.voltage else None
        branch_name = None
        station_set = set()
        for sgt in self.guage.station_techs:
            if sgt.relation_status:
                station_set.add(sgt.station.station_name)

            # Get branch name once
            if not branch_name:
                branch_name = sgt.station.branch.branch_name

        result['station_names'] = ", ".join(station_set) if station_set else None
        result['station_names_list'] = list(station_set) if station_set else None
        result['branch_name'] = branch_name
        return result


    # # remove this when working on sqlserver , autoincrement=True will do the job for sqlserver OR , db.Sequence('station_gauge_seq') in postgres
    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)
    #     if not self.guage_bill_id:
    #         # Get next available ID
    #         max_id = db.session.query(db.func.max(GuageBill.guage_bill_id)).scalar()
    #         self.guage_bill_id = (max_id or 0) + 1


class TechnologyBill(db.Model):
    __tablename__ = 'technology_bill'
    tech_bill_id = db.Column(Integer, unique=True, nullable=False, autoincrement=True, server_default=db.FetchedValue())
    bill_month = db.Column(Integer, primary_key=True)
    bill_year = db.Column(Integer, primary_key=True)
    station_id = db.Column(Integer, db.ForeignKey('stations.station_id'), primary_key=True)
    technology_id = db.Column(Integer, db.ForeignKey('technologies.technology_id'), primary_key=True)
    technology_bill_percentage = db.Column(Float, nullable=True)
    technology_power_consump = db.Column(Float, nullable=False)
    technology_liquid_alum_consump = db.Column(Float)
    technology_solid_alum_consump = db.Column(Float)
    technology_chlorine_consump = db.Column(Float)
    technology_water_amount = db.Column(Float)
    technology_bill_total = db.Column(Numeric(19, 4), nullable=False)
    power_per_water = db.Column(Float)
    chlorine_range_from = db.Column(Float)
    chlorine_range_to = db.Column(Float)
    solid_alum_range_from = db.Column(Float)
    solid_alum_range_to = db.Column(Float)
    liquid_alum_range_from = db.Column(Float)
    liquid_alum_range_to = db.Column(Float)

    # Relationships
    station = db.relationship('Station', back_populates='technology_bills')
    technology = db.relationship('Technology', back_populates='technology_bills')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['station_name'] = self.station.station_name if self.station else None
        data['technology_name'] = self.technology.technology_name if self.technology else None
        data['branch_id'] = self.station.branch_id if self.station else None
        data['branch_name'] = self.station.branch.branch_name if self.station and self.station.branch else None
        return data

    # # remove this when working on sqlserver , autoincrement=True will do the job for sqlserver OR , db.Sequence('station_gauge_seq') in postgres
    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)
    #     if not self.tech_bill_id:
    #         # Get next available ID
    #         max_id = db.session.query(db.func.max(TechnologyBill.tech_bill_id)).scalar()
    #         self.tech_bill_id = (max_id or 0) + 1


class AlumChlorineReference(db.Model):
    __tablename__ = 'alum_chlorine_reference'
    chemical_id = db.Column(Integer, unique=True, nullable=False, autoincrement=True, server_default=db.FetchedValue())
    technology_id = db.Column(db.Integer, db.ForeignKey('technologies.technology_id'), primary_key=True)
    water_source_id = db.Column(db.Integer, db.ForeignKey('water_source.water_source_id'), primary_key=True)
    season = db.Column(NVARCHAR(20), primary_key=True)

    chlorine_range_from = db.Column(Float, nullable=False)
    chlorine_range_to = db.Column(Float, nullable=False)
    solid_alum_range_from = db.Column(Float)
    solid_alum_range_to = db.Column(Float)
    liquid_alum_range_from = db.Column(Float)
    liquid_alum_range_to = db.Column(Float)

    # Relationships
    technology = db.relationship('Technology', backref='alum_chlorine_references')
    water_source = db.relationship('WaterSource', backref='alum_chlorine_references')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['technology_name'] = self.technology.technology_name if self.technology else None
        data['water_source_name'] = self.water_source.water_source_name if self.water_source else None
        return data

    # # remove this when working on sqlserver , autoincrement=True will do the job for sqlserver OR , db.Sequence('station_gauge_seq') in postgres
    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)
    #     if not self.chemical_id:
    #         # Get next available ID
    #         max_id = db.session.query(db.func.max(AlumChlorineReference.chemical_id)).scalar()
    #         self.chemical_id = (max_id or 0) + 1


class AreaOfService(db.Model):
    __tablename__ = 'area_of_service'

    area_id = db.Column(Integer, primary_key=True)
    area_name = db.Column(NVARCHAR(200), unique=True, nullable=False)
    increasable = db.Column(Boolean, nullable=False)

    places = db.relationship('Place', back_populates='area')
    stations = db.relationship('Station', back_populates='area')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        return data


class PlaceType(db.Model):
    __tablename__ = 'place_types'

    place_type_id = db.Column(Integer, primary_key=True)
    place_type_name = db.Column(NVARCHAR(100), unique=True, nullable=False)
    person_portion_from = db.Column(Integer, nullable=False)
    person_portion_to = db.Column(Integer, nullable=False)

    places = db.relationship('Place', back_populates='place_type')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Place(db.Model):
    __tablename__ = 'places'

    place_id = db.Column(Integer, primary_key=True)
    place_name = db.Column(NVARCHAR(200), unique=True, nullable=False)

    place_type_id = db.Column(Integer, db.ForeignKey('place_types.place_type_id'), nullable=False)

    branch_id = db.Column(Integer, db.ForeignKey('branches.branch_id'), nullable=False)

    area_id = db.Column(Integer, db.ForeignKey('area_of_service.area_id'), nullable=False)

    place_type = db.relationship('PlaceType', back_populates='places')
    branch = db.relationship('Branch', back_populates='places')
    area = db.relationship('AreaOfService', back_populates='places')

    populations = db.relationship('PlacePopulation', back_populates='place')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['area_name'] = self.area.area_name if self.area else None
        data['branch_name'] = self.branch.branch_name if self.branch else None
        data['place_type_name'] = self.place_type.place_type_name if self.place_type else None
        data['populations'] = [p.to_dict() for p in sorted(self.populations, key=lambda x: x.population_year)]
        return data


class PlacePopulation(db.Model):
    __tablename__ = 'place_population'

    place_id = db.Column(Integer, db.ForeignKey('places.place_id'), primary_key=True)

    population_year = db.Column(Integer, primary_key=True)

    population = db.Column(Integer, nullable=False)

    place = db.relationship('Place', back_populates='populations')

    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['place_name'] = self.place.place_name if self.place else None
        return data



class Group(db.Model):
    __tablename__ = 'groups'
    group_id = db.Column(Integer, primary_key=True, autoincrement=True)
    group_name = db.Column(NVARCHAR(400), unique=True, nullable=False)
    group_notification = db.Column(NVARCHAR(1000))

    users = db.relationship('User', back_populates='group')
    permissions = db.relationship('GroupPermission', back_populates='group')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Permission(db.Model):
    __tablename__ = 'premessions'
    permession_id = db.Column(Integer, primary_key=True, autoincrement=True)
    permession_name = db.Column(NVARCHAR(400), unique=True, nullable=False)

    group_permissions = db.relationship('GroupPermission', back_populates='permission')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class GroupPermission(db.Model):
    __tablename__ = 'group_premessions'
    group_id = db.Column(Integer, db.ForeignKey('groups.group_id'), primary_key=True)
    permession_id = db.Column(Integer, db.ForeignKey('premessions.permession_id'), primary_key=True)

    group = db.relationship('Group', back_populates='permissions')
    permission = db.relationship('Permission', back_populates='group_permissions')

    def to_dict(self):
        return {
            'group_id': self.group_id,
            'group_name': self.group.group_name if self.group else None,
            'permession_id': self.permession_id,
            'permession_name': self.permission.permession_name if self.permission else None
        }


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    emp_code = db.Column(NVARCHAR(8), primary_key=True)
    emp_name = db.Column(NVARCHAR(400), unique=True, nullable=False)
    username = db.Column(NVARCHAR(30), unique=True)
    userpassword = db.Column(NVARCHAR(300), nullable=False)
    group_id = db.Column(Integer, db.ForeignKey('groups.group_id'))
    is_active = db.Column(Boolean, nullable=False)

    group = db.relationship('Group', back_populates='users')
    audits = db.relationship("Auditing", back_populates="user")

    # Optional if you don’t want to rename your PK
    def get_id(self):
        return str(self.emp_code)  # must return a string


    def to_dict(self):
        data = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        data['group_name'] = self.group.group_name if self.group else None
        data.pop('userpassword', None)
        # data.pop('group_id', None)
        return data


class Auditing(db.Model):
    __tablename__ = "auditing"

    audit_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(30), db.ForeignKey("users.username"), nullable=False)
    audit_date = db.Column(db.DateTime, nullable=False)
    action = db.Column(db.String(10), nullable=False)             # INSERT / UPDATE / DELETE
    table_name = db.Column(db.String(100), nullable=False)
    old_data = db.Column(db.Text, nullable=True)                  # JSON string of old values
    new_data = db.Column(db.Text, nullable=True)                  # JSON string of new values

    # Relationships
    user = db.relationship("User", back_populates="audits")

    def to_dict(self):
        """Return a serializable dictionary of the audit record."""
        return {
            "audit_id": self.audit_id,
            "username": self.username,
            "audit_date": self.audit_date.isoformat() if self.audit_date else None,
            "action": self.action,
            "table_name": self.table_name,
            "old_data": self.old_data,
            "new_data": self.new_data,
        }