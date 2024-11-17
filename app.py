from flask import Flask
from config import MONGO_URI
from farms import farms_bp
from flask_pymongo import PyMongo
from flask_cors import CORS
from dotenv import load_dotenv
import os

def create_app():
    app = Flask(__name__)
    app.config["MONGO_URI"] = MONGO_URI
    
    # Enable CORS
    CORS(app, resources={r"/*": {"origins": "*"}})

    mongo = PyMongo(app)
    app.register_blueprint(farms_bp, url_prefix='/farm')
    app.mongo = mongo
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host="0.0.0.0", port=5500, debug=True)