from flask import Blueprint


farms_bp = Blueprint('farms', __name__)

# Import routes to register with the blueprint
from . import routes