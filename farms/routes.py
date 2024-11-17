from flask import request, jsonify, current_app, Response
from functools import wraps
from http import HTTPStatus
import json
from urllib.request import urlopen
from . import farms_bp
from .utils import is_valid_geojson, get_countyinfo, get_labels
from idrandgen import generate_random_id
from bson import json_util
from dotenv import load_dotenv, find_dotenv
from flask_cors import cross_origin
from jose import jwt
from os import environ as env
import certifi
import requests
import pandas as pd
import time

class AuthError(Exception):
    """
    An AuthError is raised whenever the authentication failed.
    """
    def __init__(self, error: dict[str, str], status_code: int):
        super().__init__()
        self.error = error
        self.status_code = status_code

ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)
AUTH0_DOMAIN = env.get("AUTH0_DOMAIN")
API_IDENTIFIER = env.get("AUTH0_AUDIENCE")
DATABRICKS_URL = env.get("DATABRICKS_URL")
DATABRICKS_TOKEN = env.get("DATABRICKS_TOKEN")
ALGORITHMS = ["RS256"]

EVENTS_TO_NUM = {
    "None": 1,
    "Astronomical Low Tide": 2,
    "Avalanche": 3,
    "Blizzard": 4,
    "Coastal Flood": 5,
    "Cold/Wind Chill": 6,
    "Debris Flow": 7,
    "Dense Fog": 8,
    "Dense Smoke": 9,
    "Drought": 10,
    "Dust Devil": 11,
    "Dust Storm": 12,
    "Excessive Heat": 13,
    "Extreme Cold/Wind Chill": 14,
    "Flash Flood": 15,
    "Flood": 16,
    "Freezing Fog": 17,
    "Frost/Freeze": 18,
    "Funnel Cloud": 19,
    "Hail": 20,
    "Heat": 21,
    "Heavy Rain": 22,
    "Heavy Snow": 23,
    "High Surf": 24,
    "High Wind": 25,
    "Hurricane (Typhoon)": 26,
    "Ice Storm": 27,
    "Lake-Effect Snow": 28,
    "Lakeshore Flood": 29,
    "Lightning": 30,
    "Marine Hail": 31,
    "Marine High Wind": 32,
    "Marine Strong Wind": 33,
    "Marine Thunderstorm Wind": 34,
    "Rip Current": 35,
    "Seiche": 36,
    "Sleet": 37,
    "Sneakerwave": 38,
    "Storm Surge/Tide": 39,
    "Strong Wind": 40,
    "Thunderstorm Wind": 41,
    "Tornado": 42,
    "Tropical Depression": 43,
    "Tropical Storm": 44,
    "Tsunami": 45,
    "Volcanic Ash": 46,
    "Waterspout": 47,
    "Wildfire": 48,
    "Winter Storm": 49,
    "Winter Weather": 50
}

NUM_TO_EVENT = {val: key for key, val in EVENTS_TO_NUM.items()}

def find_date_index(df, date):
    ## Convert date string to year and day
    date = pd.to_datetime(date)
    year = date.year
    day = date.day_of_year
    ## Find the row with this year and day
    result = df[(df["Year15"] == year) & (df["Day15"] == day - 1)].index
    if result.empty:
        return -1
    else:
        return result[0]

@farms_bp.errorhandler(AuthError)
def handle_auth_error(ex: AuthError) -> Response:
    """
    serializes the given AuthError as json and sets the response status code accordingly.
    :param ex: an auth error
    :return: json serialized ex response
    """
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    return response


def get_token_auth_header() -> str:
    """Obtains the access token from the Authorization Header
    """
    auth = request.headers.get("Authorization", None)
    if not auth:
        raise AuthError({"code": "authorization_header_missing",
                         "description":
                             "Authorization header is expected"}, 401)

    parts = auth.split()

    if parts[0].lower() != "bearer":
        raise AuthError({"code": "invalid_header",
                        "description":
                            "Authorization header must start with"
                            " Bearer"}, 401)
    if len(parts) == 1:
        raise AuthError({"code": "invalid_header",
                        "description": "Token not found"}, 401)
    if len(parts) > 2:
        raise AuthError({"code": "invalid_header",
                         "description":
                             "Authorization header must be"
                             " Bearer token"}, 401)

    token = parts[1]
    return token

def get_user_id():
    token = get_token_auth_header()
    unverified_claims = jwt.get_unverified_claims(token)
    return unverified_claims.get("sub")

def requires_scope(required_scope: str) -> bool:
    """Determines if the required scope is present in the access token
    Args:
        required_scope (str): The scope required to access the resource
    """
    token = get_token_auth_header()
    unverified_claims = jwt.get_unverified_claims(token)
    if unverified_claims.get("scope"):
        token_scopes = unverified_claims["scope"].split()
        for token_scope in token_scopes:
            if token_scope == required_scope:
                return True
    return False


def requires_auth(func):
    """Determines if the access token is valid
    """
    
    @wraps(func)
    def decorated(*args, **kwargs):
        token = get_token_auth_header()
        jsonurl = urlopen("https://" + AUTH0_DOMAIN + "/.well-known/jwks.json", cafile=certifi.where())
        jwks = json.loads(jsonurl.read())
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.JWTError as jwt_error:
            raise AuthError({"code": "invalid_header",
                            "description":
                                "Invalid header. "
                                "Use an RS256 signed JWT Access Token"}, 401) from jwt_error
        if unverified_header["alg"] == "HS256":
            raise AuthError({"code": "invalid_header",
                             "description":
                                 "Invalid header. "
                                 "Use an RS256 signed JWT Access Token"}, 401)
        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
        if rsa_key:
            try:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=ALGORITHMS,
                    audience=API_IDENTIFIER,
                    issuer="https://" + AUTH0_DOMAIN + "/"
                )
            except jwt.ExpiredSignatureError as expired_sign_error:
                raise AuthError({"code": "token_expired",
                                "description": "token is expired"}, 401) from expired_sign_error
            except jwt.JWTClaimsError as jwt_claims_error:
                raise AuthError({"code": "invalid_claims",
                                "description":
                                    "incorrect claims,"
                                    " please check the audience and issuer"}, 401) from jwt_claims_error
            except Exception as exc:
                raise AuthError({"code": "invalid_header",
                                "description":
                                    "Unable to parse authentication"
                                    " token."}, 401) from exc

            return func(*args, **kwargs)
        raise AuthError({"code": "invalid_header",
                         "description": "Unable to find appropriate key"}, 401)

    return decorated

def handle_options_request():
    response = current_app.make_default_options_response()
    return response

# Update the add_farm route to handle OPTIONS
@farms_bp.route('/add-farm', methods=['POST', 'OPTIONS'])
@cross_origin()
def add_farm():
    if request.method == 'OPTIONS':
        return handle_options_request(['POST'])
        
    # Your existing authentication check
    @requires_auth
    def handle_post():
        geojson = request.get_json()
        if not geojson:
            return jsonify({
                "error": "invalid_request",
                "description": "Invalid request body"
            }), HTTPStatus.BAD_REQUEST
            
        # Rest of your existing add_farm code
        geojson['properties']['fieldId'] = generate_random_id()
        geojson['properties']['user_id'] = get_user_id()
        geojson['properties']['county_info'] = get_countyinfo(geojson)

        if not is_valid_geojson(geojson):
            return jsonify({
                "error": "invalid_format",
                "description": "Invalid GeoJSON format"
            }), HTTPStatus.BAD_REQUEST

        current_app.mongo.db.farms.insert_one(geojson)
        return jsonify({"message": "Farm added successfully"}), HTTPStatus.OK
    
    return handle_post()

# Update the update_farm route
@farms_bp.route('/update-farm', methods=['PUT', 'OPTIONS'])
@cross_origin()
def update_farm():
    if request.method == 'OPTIONS':
        return handle_options_request(['PUT'])
        
    @requires_auth
    def handle_put():
        geojson = request.get_json()
        if not geojson:
            return jsonify({
                "error": "invalid_request",
                "description": "Invalid request body"
            }), HTTPStatus.BAD_REQUEST

        if not is_valid_geojson(geojson):
            return jsonify({
                "error": "invalid_format",
                "description": "Invalid GeoJSON format"
            }), HTTPStatus.BAD_REQUEST

        current_app.mongo.db.farms.update_one(
            {"properties.fieldId": request.get_json()['properties']['fieldId']}, 
            {"$set": geojson}
        )
        return jsonify({"message": "Farm updated successfully"}), HTTPStatus.OK
    
    return handle_put()

# Update the delete_farm route
@farms_bp.route('/delete-farm/<fieldId>', methods=['DELETE', 'OPTIONS'])
@cross_origin()
def delete_farm(fieldId):
    if request.method == 'OPTIONS':
        return handle_options_request(['DELETE'])
        
    @requires_auth
    def handle_delete():
        current_app.mongo.db.farms.delete_one({"properties.fieldId": fieldId})
        return jsonify({"message": "Farm deleted successfully"}), HTTPStatus.OK
    
    return handle_delete()

# Update the get_user_farms route
@farms_bp.route('/user-farms', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_user_farms():
    if request.method == 'OPTIONS':
        return handle_options_request(['GET'])
        
    @requires_auth
    def handle_get():
        farms = list(current_app.mongo.db.farms.find({"properties.user_id": get_user_id()}))
            
        return json.loads(json_util.dumps(farms)), HTTPStatus.OK
    
    return handle_get()

# Update the get_alerts route
@farms_bp.route('/get-alerts', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_alerts():
    if request.method == 'OPTIONS':
        return handle_options_request(['GET'])
        
    @requires_auth
    def handle_get():
        farms = list(current_app.mongo.db.farms.find({"properties.user_id": get_user_id()}))
        
        res = []
        for farm in farms:
            county_info = farm['properties']['county_info']
            labels = get_labels(county_info)
            res.append({
                "fieldId": farm['properties']['fieldId'],
                "labels": labels
            })
        return jsonify(res), HTTPStatus.OK
    
    return handle_get()

@farms_bp.route('/add-employee', methods=['POST', 'OPTIONS'])
@cross_origin()
def add_employee_to_farm():
    if request.method == 'OPTIONS':
        return handle_options_request(['POST'])
    
    @requires_auth
    def handle_get():
        fieldId = request.args.get('fieldId')
        employee = request.args.get('employee')
        current_app.mongo.db.farms.update_one(
            {"properties.fieldId": fieldId},
            {"$push": {"properties.employees": employee}}
        )
        return jsonify({"message": "Employee added successfully"}), HTTPStatus.OK
    
    return handle_get()

@farms_bp.route('/get-employees', methods=['GET', 'OPTIONS'])
@cross_origin()
def get_employees():
    if request.method == 'OPTIONS':
        return handle_options_request(['GET'])
    
    @requires_auth
    def handle_get():
        fieldId = request.args.get('fieldId')
        farm = current_app.mongo.db.farms.find_one({"properties.fieldId": fieldId})
        return jsonify(farm['properties']['employees']), HTTPStatus.OK
    
    return handle_get()