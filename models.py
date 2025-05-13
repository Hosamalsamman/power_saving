from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Branch(db.Model):
    __tablename__ = 'branches'
    branch_id = db.Column(db.SmallInteger, primary_key=True)
    branch_name = db.Column(db.String(200), nullable=False, unique=True)

    stations = db.relationship('Station', back_populates='branch')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class WaterSource(db.Model):
    __tablename__ = 'water_source'
    water_source_id = db.Column(db.SmallInteger, primary_key=True)
    water_source_name = db.Column(db.String(400), nullable=False, unique=True)

    stations = db.relationship('Station', back_populates='water_source')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Station(db.Model):
    __tablename__ = 'stations'
    station_id = db.Column(db.SmallInteger, primary_key=True)
    station_name = db.Column(db.String(200), nullable=False, unique=True)
    branch_id = db.Column(db.SmallInteger, db.ForeignKey('branches.branch_id'), nullable=False)
    station_type = db.Column(db.String(10), nullable=False)
    station_water_capacity = db.Column(db.Integer, nullable=False)
    water_source_id = db.Column(db.SmallInteger, db.ForeignKey('water_source.water_source_id'), nullable=False)
    station_status = db.Column(db.Boolean, nullable=False)

    branch = db.relationship('Branch', back_populates='stations')
    water_source = db.relationship('WaterSource', back_populates='stations')
    station_guage_technologies = db.relationship('StationGuageTechnology', back_populates='station')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Voltage(db.Model):
    __tablename__ = 'voltage'
    voltage_id = db.Column(db.SmallInteger, primary_key=True)
    voltage_type = db.Column(db.String(50), nullable=False)
    voltage_cost = db.Column(db.Numeric(10, 4), nullable=False)

    guages = db.relationship('Guage', back_populates='voltage')
    guage_bills = db.relationship('GuageBill', back_populates='voltage')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Guage(db.Model):
    __tablename__ = 'guages'
    account_number = db.Column(db.String(50), primary_key=True)
    meter_id = db.Column(db.String(50), unique=True)
    meter_factor = db.Column(db.Integer, nullable=False)
    final_reading = db.Column(db.BigInteger, nullable=False)
    voltage_id = db.Column(db.SmallInteger, db.ForeignKey('voltage.voltage_id'), nullable=False)
    account_status = db.Column(db.Boolean, nullable=False)

    voltage = db.relationship('Voltage', back_populates='guages')
    guage_bills = db.relationship('GuageBill', back_populates='guage')
    station_guage_technologies = db.relationship('StationGuageTechnology', back_populates='guage')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Technology(db.Model):
    __tablename__ = 'technologies'
    technology_id = db.Column(db.SmallInteger, primary_key=True)
    technology_name = db.Column(db.String(200), nullable=False, unique=True)
    power_per_water = db.Column(db.Float, nullable=False)
    liquid_chlorine_per_water = db.Column(db.Float)
    solid_chlorine_per_water = db.Column(db.Float)
    alum_per_water = db.Column(db.Float)

    station_guage_technologies = db.relationship('StationGuageTechnology', back_populates='technology')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class StationGuageTechnology(db.Model):
    __tablename__ = 'station_guage_technology'
    station_guage_technology_id = db.Column(db.Integer, unique=True, nullable=False)
    station_id = db.Column(db.SmallInteger, db.ForeignKey('stations.station_id'), primary_key=True)
    technology_id = db.Column(db.SmallInteger, db.ForeignKey('technologies.technology_id'), primary_key=True)
    account_number = db.Column(db.String(50), db.ForeignKey('guages.account_number'), primary_key=True)

    station = db.relationship('Station', back_populates='station_guage_technologies')
    technology = db.relationship('Technology', back_populates='station_guage_technologies')
    guage = db.relationship('Guage', back_populates='station_guage_technologies')
    technology_bills = db.relationship('TechnologyBill', back_populates='station_guage_technology')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class GuageBill(db.Model):
    __tablename__ = 'guage_bill'
    guage_bill_id = db.Column(db.String(50), unique=True, nullable=False)
    account_number = db.Column(db.String(50), db.ForeignKey('guages.account_number'), primary_key=True)
    bill_month = db.Column(db.SmallInteger, primary_key=True)
    bill_year = db.Column(db.SmallInteger, primary_key=True)
    prev_reading = db.Column(db.BigInteger, nullable=False)
    current_reading = db.Column(db.BigInteger, nullable=False)
    reading_factor = db.Column(db.Integer, nullable=False)
    power_consump = db.Column(db.BigInteger, nullable=False)
    voltage_id = db.Column(db.SmallInteger, db.ForeignKey('voltage.voltage_id'), nullable=False)
    voltage_cost = db.Column(db.Numeric(10, 4), nullable=False)
    consump_cost = db.Column(db.Numeric(19, 4), nullable=False)
    fixed_installment = db.Column(db.Numeric(19, 4), nullable=False)
    settlements = db.Column(db.Numeric(19, 4), nullable=False)
    stamp = db.Column(db.Numeric(19, 4), nullable=False)
    prev_payments = db.Column(db.Numeric(19, 4), nullable=False)
    rounding = db.Column(db.Float, nullable=False)
    bill_total = db.Column(db.Numeric(19, 4), nullable=False)

    guage = db.relationship('Guage', back_populates='guage_bills')
    voltage = db.relationship('Voltage', back_populates='guage_bills')
    technology_bills = db.relationship('TechnologyBill', back_populates='guage_bill')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class TechnologyBill(db.Model):
    __tablename__ = 'technology_bill'
    guage_bill_id = db.Column(db.String(50), db.ForeignKey('guage_bill.guage_bill_id'), primary_key=True)
    station_guage_technology_id = db.Column(db.Integer, db.ForeignKey('station_guage_technology.station_guage_technology_id'), primary_key=True)
    technology_bill_percentage = db.Column(db.Float, nullable=False)
    technology_power_consump = db.Column(db.BigInteger, nullable=False)
    technology_liquid_alum_consump = db.Column(db.BigInteger)
    technology_solid_alum_consump = db.Column(db.BigInteger)
    technology_chlorine_consump = db.Column(db.BigInteger)
    technology_water_amount = db.Column(db.BigInteger)
    technology_bill_total = db.Column(db.Numeric(19, 4), nullable=False)

    guage_bill = db.relationship('GuageBill', back_populates='technology_bills')
    station_guage_technology = db.relationship('StationGuageTechnology', back_populates='technology_bills')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Group(db.Model):
    __tablename__ = 'groups'
    group_id = db.Column(db.SmallInteger, primary_key=True)
    group_name = db.Column(db.String(400), nullable=False, unique=True)
    group_notification = db.Column(db.String(1000))

    users = db.relationship('User', back_populates='group')
    group_permissions = db.relationship('GroupPermission', back_populates='group')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class Permission(db.Model):
    __tablename__ = 'premessions'
    permession_id = db.Column(db.SmallInteger, primary_key=True)
    permession_name = db.Column(db.String(400), nullable=False, unique=True)

    group_permissions = db.relationship('GroupPermission', back_populates='permession')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class GroupPermission(db.Model):
    __tablename__ = 'group_premessions'
    group_id = db.Column(db.SmallInteger, db.ForeignKey('groups.group_id'), primary_key=True)
    permession_id = db.Column(db.SmallInteger, db.ForeignKey('premessions.permession_id'), primary_key=True)

    group = db.relationship('Group', back_populates='group_permissions')
    permession = db.relationship('Permission', back_populates='group_permissions')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class User(db.Model):
    __tablename__ = 'users'
    emp_code = db.Column(db.String(8), primary_key=True)
    emp_name = db.Column(db.String(400), nullable=False, unique=True)
    username = db.Column(db.String(30), unique=True)
    userpassword = db.Column(db.String(30), nullable=False)
    group_id = db.Column(db.SmallInteger, db.ForeignKey('groups.group_id'), nullable=False)

    group = db.relationship('Group', back_populates='users')

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
