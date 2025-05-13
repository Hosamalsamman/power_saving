import os
from flask import Flask, jsonify, render_template, request
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
    pass


if __name__ == '__main__':
    app.run(debug=True)
