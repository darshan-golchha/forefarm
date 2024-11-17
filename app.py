from flask import Flask
from config import MONGO_URI
from farms import farms_bp  # Import the blueprint
from flask_pymongo import PyMongo
from dotenv import load_dotenv
from flask_cors import CORS
import os
from flask_talisman import Talisman


def create_app():

    app = Flask(__name__)
    app.config["MONGO_URI"] = MONGO_URI
    cors = CORS(app)
    app.config['CORS_HEADERS'] = 'Content-Type'

    mongo = PyMongo(app)

    app.register_blueprint(farms_bp, url_prefix='/farm')

    app.mongo = mongo

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
