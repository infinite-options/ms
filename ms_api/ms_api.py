from flask import Flask, request, render_template, url_for, redirect
from flask_restful import Resource, Api
from flask_mail import Mail, Message  # used for email
# used for serializer email and error handling
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from flask_cors import CORS
import jwt

from werkzeug.exceptions import BadRequest, NotFound

from dateutil.relativedelta import *
from decimal import Decimal
from datetime import datetime, date, timedelta
from hashlib import sha512
from math import ceil
import string
import random
#regex
import re
from env_keys import BING_API_KEY, RDS_PW

import decimal
import sys
import json
import pytz
import pymysql
import requests
import stripe
import binascii
stripe_public_key = 'pk_test_6RSoSd9tJgB2fN2hGkEDHCXp00MQdrK3Tw'
stripe_secret_key = 'sk_test_fe99fW2owhFEGTACgW3qaykd006gHUwj1j'
stripe.api_key = stripe_secret_key
# RDS for AWS SQL 5.7
# RDS_HOST = 'pm-mysqldb.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
# RDS for AWS SQL 8.0
RDS_HOST = 'io-mysqldb8.cxjnrciilyjq.us-west-1.rds.amazonaws.com'
RDS_PORT = 3306
RDS_USER = 'admin'
RDS_DB = 'sf'

app = Flask(__name__)
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})
# Set this to false when deploying to live application
app.config['DEBUG'] = True
# Adding for email testing
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'ptydtesting@gmail.com'
app.config['MAIL_PASSWORD'] = 'ptydtesting06282020'
app.config['MAIL_DEFAULT_SENDER'] = 'ptydtesting@gmail.com'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
# app.config['MAIL_DEBUG'] = True
# app.config['MAIL_SUPPRESS_SEND'] = False
# app.config['TESTING'] = False

mail = Mail(app)
s = URLSafeTimedSerializer('thisisaverysecretkey')
# API
api = Api(app)

# convert to UTC time zone when testing in local time zone
utc = pytz.utc
def getToday(): return datetime.strftime(datetime.now(utc), "%Y-%m-%d")
def getNow(): return datetime.strftime(datetime.now(utc),"%Y-%m-%d %H:%M:%S")

# Connect to MySQL database (API v2)
def connect():
    global RDS_PW
    global RDS_HOST
    global RDS_PORT
    global RDS_USER
    global RDS_DB

    print("Trying to connect to RDS (API v2)...")
    try:
        conn = pymysql.connect(RDS_HOST,
                               user=RDS_USER,
                               port=RDS_PORT,
                               passwd=RDS_PW,
                               db=RDS_DB,
                               charset='utf8mb4',
                               cursorclass=pymysql.cursors.DictCursor)
        print("Successfully connected to RDS. (API v2)")
        return conn
    except:
        print("Could not connect to RDS. (API v2)")
        raise Exception("RDS Connection failed. (API v2)")


# Disconnect from MySQL database (API v2)
def disconnect(conn):
    try:
        conn.close()
        print("Successfully disconnected from MySQL database. (API v2)")
    except:
        print("Could not properly disconnect from MySQL database. (API v2)")
        raise Exception("Failure disconnecting from MySQL database. (API v2)")




# Serialize JSON
def serializeResponse(response):
    # def is_json(myjson):
    #     try:
    #         if type(myjson) is not str:
    #             return False
    #         json.loads(myjson)
    #     except ValueError as e:
    #         return False
    #     return True
    try:
        for row in response:
            for key in row:
                if type(row[key]) is Decimal:
                    row[key] = float(row[key])
                elif (type(row[key]) is date or type(row[key]) is datetime) and row[key] is not None:
                # Change this back when finished testing to get only date
                    # row[key] = row[key].strftime("%Y-%m-%d")
                    row[key] = row[key].strftime("%Y-%m-%d %H-%M-%S")
                # elif is_json(row[key]):
                #     row[key] = json.loads(row[key])
                elif isinstance(row[key], bytes):
                    row[key] = row[key].decode()
        return response
    except:
        raise Exception("Bad query JSON")


# Execute an SQL command (API v2)
# Set cmd parameter to 'get' or 'post'
# Set conn parameter to connection object
# OPTIONAL: Set skipSerialization to True to skip default JSON response serialization
def execute(sql, cmd, conn, skipSerialization=False):
    response = {}
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cmd == 'get':
                result = cur.fetchall()
                response['message'] = 'Successfully executed SQL query.'
                # Return status code of 280 for successful GET request
                response['code'] = 280
                if not skipSerialization:
                    result = serializeResponse(result)
                response['result'] = result
            elif cmd == 'post':
                conn.commit()
                response['message'] = 'Successfully committed SQL command.'
                # Return status code of 281 for successful POST request
                response['code'] = 281
            else:
                response['message'] = 'Request failed. Unknown or ambiguous instruction given for MySQL command.'
                # Return status code of 480 for unknown HTTP method
                response['code'] = 480
    except:
        response['message'] = 'Request failed, could not execute MySQL command.'
        # Return status code of 490 for unsuccessful HTTP request
        response['code'] = 490
    finally:
        # response['sql'] = sql
        return response

def get_new_paymentID(conn):
    newPaymentQuery = execute("CALL new_payment_uid", 'get', conn)
    if newPaymentQuery['code'] == 280:
        return newPaymentQuery['result'][0]['new_id']
    return "Could not generate new payment ID", 500

def get_new_purchaseID(conn):
    newPurchaseQuery = execute("CALL new_purchase_uid", 'get', conn)
    if newPurchaseQuery['code'] == 280:
        return newPurchaseQuery['result'][0]['new_id']
    return "Could not generate new purchase ID", 500
def get_new_id(query, name, conn):
    response = {}
    new_id = execute(query, 'get', conn)
    if new_id['code'] != 280:
        response['message'] = 'Could not generate ' + name + "."
        return response, 500
    response['message'] = "OK"
    response['result'] = new_id['result'][0]['new_id']
    return response, 200

def simple_get_execute(query, name_to_show, conn):
    response = {}
    res = execute(query, 'get', conn)
    if res['code'] != 280:
        search = re.search(r'#(.*?):', query)
        query_number = "    " + search.group(1) + "     " if search is not None else "UNKNOWN QUERY NUMBER"
        string = " Cannot run the query for " + name_to_show + "."
        print("\n")
        print("*" * (len(string) + 10))
        print(string.center(len(string) + 10, "*"))
        print(query_number.center(len(string) + 10, "*"))
        print("*" * (len(string) + 10), "\n")
        response['message'] = 'Internal Server Error.'
        return response, 500
    elif not res['result']:
        response['message'] = 'Can not found the requested info.'
        return response, 204
    else:
        response['message'] = "Get " + name_to_show + " successful."
        response['result'] = res['result']

        return response, 200

def simple_post_execute(queries, names, conn):
    response = {}
    if len(queries) != len(names):
        return "Error. Queries and Names should have the same length."
    for i in range(len(queries)):
        res = execute(queries[i], 'post', conn)
        if res['code'] != 281:
            string = " Cannot Insert into the " + names[i] + " table. "
            print("*" * (len(string) + 10))
            print(string.center(len(string) + 10, "*"))
            print("*" * (len(string) + 10))
            response['message'] = "Internal Server Error."
            return response, 500
    response['message'] = "Successful."
    return response, 201



# class SignUp(Resource):
#     def post(self):
#         try:
#             conn = connect()
#             data = request.get_json(force=True)

#             email = data['email']
#             firstName = data['first_name']
#             lastName = data['last_name']
#             phone = data['phone_number']
#             address = data['address']
#             unit = data['unit'] if data.get('unit') is not None else 'NULL'
#             city = data['city']
#             state = data['state']
#             zip_code = data['zip_code']
#             latitude = data['latitude']
#             longitude = data['longitude']

#             referral = data['referral_source']
#             role = data['role']
#             cust_id = data['cust_id'] if data.get('cust_id') is not None else 'NULL'

#             if data.get('social') is None or data.get('social') == "FALSE" or data.get('social') == False:
#                 social_signup = False
#             else:
#                 social_signup = True
            

#             get_user_id_query = "CALL new_customer_uid();"
#             NewUserIDresponse = execute(get_user_id_query, 'get', conn)

#             if NewUserIDresponse['code'] == 490:
#                 string = " Cannot get new User id. "
#                 print("*" * (len(string) + 10))
#                 print(string.center(len(string) + 10, "*"))
#                 print("*" * (len(string) + 10))
#                 response['message'] = "Internal Server Error."
#                 return response, 500
#             NewUserID = NewUserIDresponse['result'][0]['new_id']

#             if social_signup == False:
#                 salt = getNow()
#                 hashed = sha512((data['password'] + salt).encode()).hexdigest()
#                 password = "'" + sha512((data['password'] + salt).encode()).hexdigest() + "'"
#                 algorithm = "'SHA512'"
#                 salt = "'" + salt + "'"
#                 access_token = 'NULL'
#                 refresh_token = 'NULL'
#                 user_social_signup = 'NULL'
#             else:
#                 access_token = "'" + data['access_token'] + "'"
#                 refresh_token = "'" + data['refresh_token'] + "'"
#                 salt = 'NULL'
#                 password = 'NULL'
#                 algorithm = 'NULL'
#                 user_social_signup = data['social']
#             # write everything to database

#             if cust_id != 'NULL' and cust_id:

#                 NewUserID = cust_id

#                 query = '''
#                             SELECT user_access_token, user_refresh_token
#                             FROM sf.customers
#                             WHERE customer_uid = \'''' + cust_id + '''\';
#                        '''
#                 it = execute(query, 'get', conn)
#                 print('it-------', it)

#                 access_token = it['result'][0]['user_access_token']
#                 refresh_token = it['result'][0]['user_refresh_token']


#                 customer_insert_query =  ['''
#                                     UPDATE sf.customers 
#                                     SET 
#                                     customer_created_at = \'''' + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + '''\',
#                                     customer_first_name = \'''' + firstName + '''\',
#                                     customer_last_name = \'''' + lastName + '''\',
#                                     customer_phone_num = \'''' + phone + '''\',
#                                     customer_address = \'''' + address + '''\',
#                                     customer_unit = \'''' + unit + '''\',
#                                     customer_city = \'''' + city + '''\',
#                                     customer_state = \'''' + state + '''\',
#                                     customer_zip = \'''' + zip_code + '''\',
#                                     customer_lat = \'''' + latitude + '''\',
#                                     customer_long = \'''' + longitude + '''\',
#                                     password_salt = \'''' + salt + '''\',
#                                     password_hashed = \'''' + password + '''\',
#                                     password_algorithm = \'''' + algorithm + '''\',
#                                     referral_source = \'''' + referral + '''\',
#                                     role = \'''' + role + '''\',
#                                     user_social_media = \'''' + user_social_signup + '''\'
#                                     WHERE customer_uid = \'''' + cust_id + '''\';
#                                     ''']


#             else:

#                 # check if there is a same customer_id existing
#                 query = """
#                         SELECT customer_email FROM sf.customers
#                         WHERE customer_email = \'""" + email + "\';"
#                 print('email---------')
#                 items = execute(query, 'get', conn)
#                 if items['result']:

#                     items['result'] = ""
#                     items['code'] = 409
#                     items['message'] = "Email address has already been taken."

#                     return items

#                 if items['code'] == 480:

#                     items['result'] = ""
#                     items['code'] = 480
#                     items['message'] = "Internal Server Error."
#                     return items


#                 # write everything to database
#                 customer_insert_query = ["""
#                                         INSERT INTO sf.customers 
#                                         (
#                                             customer_uid,
#                                             customer_created_at,
#                                             customer_first_name,
#                                             customer_last_name,
#                                             customer_phone_num,
#                                             customer_email,
#                                             customer_address,
#                                             customer_unit,
#                                             customer_city,
#                                             customer_state,
#                                             customer_zip,
#                                             customer_lat,
#                                             customer_long,
#                                             password_salt,
#                                             password_hashed,
#                                             password_algorithm,
#                                             referral_source,
#                                             role,
#                                             user_social_media,
#                                             user_access_token,
#                                             user_refresh_token
#                                         )
#                                         VALUES
#                                         (
                                        
#                                             \'""" + NewUserID + """\',
#                                             \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
#                                             \'""" + firstName + """\',
#                                             \'""" + lastName + """\',
#                                             \'""" + phone + """\',
#                                             \'""" + email + """\',
#                                             \'""" + address + """\',
#                                             \'""" + unit + """\',
#                                             \'""" + city + """\',
#                                             \'""" + state + """\',
#                                             \'""" + zip_code + """\',
#                                             \'""" + latitude + """\',
#                                             \'""" + longitude + """\',
#                                             \'""" + salt + """\',
#                                             \'""" + password + """\',
#                                             \'""" + algorithm + """\',
#                                             \'""" + referral + """\',
#                                             \'""" + role + """\',
#                                             \'""" + user_social_signup + """\',
#                                             \'""" + access_token + """\',
#                                             \'""" + refresh_token + """\');"""]

#             items = execute(customer_insert_query[0], 'post', conn)
#             print(customer_insert_query[0])
#             if items['code'] != 281:
#                 items['result'] = ""
#                 items['code'] = 480
#                 items['message'] = "Error while inserting values in database"

#                 return items


#             items['result'] = {
#                 'first_name': firstName,
#                 'last_name': lastName,
#                 'customer_uid': NewUserID,
#                 'access_token': access_token,
#                 'refresh_token': refresh_token
#             }
#             items['message'] = 'Signup successful'
#             items['code'] = 200


#             # Sending verification email
#             if social_signup == False:
#                 token = s.dumps(email)
#                 msg = Message("Email Verification", sender='ptydtesting@gmail.com', recipients=[email])
#                 # link = url_for('confirm', token=token, hashed=password, _external=True)

#                 link = url_for('confirm', token=token, hashed=hashed, _external=True)
#                 msg.body = "Click on the link {} to verify your email address.".format(link)
#                 mail.send(msg)
#             return items
#         except:
#             print("Error happened while Sign Up")
#             if "NewUserID" in locals():
#                 execute("""DELETE FROM customers WHERE customer_uid = '""" + NewUserID + """';""", 'post', conn)
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)

# # confirmation page
# @app.route('/api/v2/confirm', methods=['GET'])
# def confirm():
#     try:
#         token = request.args['token']
#         hashed = request.args['hashed']
#         print("hased: ", hashed)
#         email = s.loads(token)  # max_age = 86400 = 1 day

#         # marking email confirmed in database, then...
#         conn = connect()
#         query = """UPDATE customers SET email_verified = 1 WHERE customer_email = \'""" + email + """\';"""
#         update = execute(query, 'post', conn)
#         if update.get('code') == 281:
#             # redirect to login page
#             return redirect('https://mealtoyourdoor.netlify.app/?email={}&hashed={}'.format(email, hashed))
#         else:
#             print("Error happened while confirming an email address.")
#             error = "Confirm error."
#             err_code = 401  # Verification code is incorrect
#             return error, err_code
#     except (SignatureExpired, BadTimeSignature) as err:
#         status = 403  # forbidden
#         return str(err), status
#     finally:
#         disconnect(conn)





class SignUp(Resource):
    def post(self):
        response = {}
        items = []
        try:
            conn = connect()
            data = request.get_json(force=True)
            print(data)
            email = data['email']
            firstName = data['first_name']
            lastName = data['last_name']
            phone = data['phone_number']
            address = data['address']
            unit = data['unit'] if data.get('unit') is not None else 'NULL'
            city = data['city']
            state = data['state']
            zip_code = data['zip_code']
            latitude = data['latitude']
            longitude = data['longitude']
            referral = data['referral_source']
            role = data['role']
            time = data['social_timestamp']
            cust_id = data['cust_id'] if data.get('cust_id') is not None else 'NULL'

            if data.get('social') is None or data.get('social') == "FALSE" or data.get('social') == False:
                social_signup = False
            else:
                social_signup = True


            get_user_id_query = "CALL new_customer_uid();"
            NewUserIDresponse = execute(get_user_id_query, 'get', conn)

            if NewUserIDresponse['code'] == 490:
                string = " Cannot get new User id. "
                print("*" * (len(string) + 10))
                print(string.center(len(string) + 10, "*"))
                print("*" * (len(string) + 10))
                response['message'] = "Internal Server Error."
                return response, 500
            NewUserID = NewUserIDresponse['result'][0]['new_id']

            if social_signup == False:
                salt = (datetime.now()).strftime("%Y-%m-%d %H:%M:%S")

                password = sha512((data['password'] + salt).encode()).hexdigest()
                print('password------', password)
                algorithm = "SHA512"
                access_token = 'NULL'
                refresh_token = 'NULL'
                user_social_signup = 'NULL'
            else:

                access_token = data['access_token']
                refresh_token = data['refresh_token']
                salt = 'NULL'
                password = 'NULL'
                algorithm = 'NULL'
                user_social_signup = data['social']

            if cust_id != 'NULL' and cust_id:
                
                NewUserID = cust_id

                query = '''
                            SELECT user_access_token, user_refresh_token
                            FROM sf.customers
                            WHERE customer_uid = \'''' + cust_id + '''\';
                       '''
                it = execute(query, 'get', conn)
                print('it-------', it)

                access_token = it['result'][0]['user_access_token']
                refresh_token = it['result'][0]['user_refresh_token']


                customer_insert_query =  ['''
                                    UPDATE sf.customers 
                                    SET 
                                    customer_created_at = \'''' + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + '''\',
                                    customer_first_name = \'''' + firstName + '''\',
                                    customer_last_name = \'''' + lastName + '''\',
                                    customer_phone_num = \'''' + phone + '''\',
                                    customer_address = \'''' + address + '''\',
                                    customer_unit = \'''' + unit + '''\',
                                    customer_city = \'''' + city + '''\',
                                    customer_state = \'''' + state + '''\',
                                    customer_zip = \'''' + zip_code + '''\',
                                    customer_lat = \'''' + latitude + '''\',
                                    customer_long = \'''' + longitude + '''\',
                                    password_salt = \'''' + salt + '''\',
                                    password_hashed = \'''' + password + '''\',
                                    password_algorithm = \'''' + algorithm + '''\',
                                    referral_source = \'''' + referral + '''\',
                                    role = \'''' + role + '''\',
                                    user_social_media = \'''' + user_social_signup + '''\'
                                    social_timestamp = \'''' + time + '''\'
                                    WHERE customer_uid = \'''' + cust_id + '''\';
                                    ''']


            else:
                #print("1")
                # check if there is a same customer_id existing
                query = """
                        SELECT customer_email FROM sf.customers
                        WHERE customer_email = \'""" + email + "\';"
                print('email---------')
                items = execute(query, 'get', conn)
                if items['result']:

                    items['result'] = ""
                    items['code'] = 409
                    items['message'] = "Email address has already been taken."

                    return items

                if items['code'] == 480:

                    items['result'] = ""
                    items['code'] = 480
                    items['message'] = "Internal Server Error."
                    return items

                #print("2")
                # write everything to database
                # this method of insert, only works for mysql. and limits insert to one row at a time
                customer_insert_query = ["""
                                        INSERT INTO sf.customers 
                                        set
                                            customer_uid= \'""" + NewUserID + """\',
                                            customer_created_at = \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
                                            customer_first_name = \'""" + firstName + """\',
                                            customer_last_name =\'""" + lastName + """\',
                                            customer_phone_num =\'""" + phone + """\',
                                            customer_email = \'""" + email + """\',
                                            customer_address = \'""" + address + """\',
                                            customer_unit = \'""" + unit + """\',
                                            customer_city = \'""" + city + """\',
                                            customer_state = \'""" + state + """\',
                                            customer_zip =\'""" + zip_code + """\',
                                            customer_lat =\'""" + latitude + """\',
                                            customer_long =\'""" + longitude + """\',
                                            password_salt =\'""" + salt + """\',
                                            password_hashed =\'""" + password + """\',
                                            password_algorithm =\'""" + algorithm + """\',
                                            referral_source= \'""" + referral + """\',
                                            role =\'""" + role + """\',
                                            user_social_media =\'""" + user_social_signup + """\',
                                            user_access_token =\'""" + access_token + """\',
                                            user_refresh_token =\'""" + refresh_token + """\'
                                        ;"""]
            #print("3")
            items = execute(customer_insert_query[0], 'post', conn)
            #print(items)
            if items['code'] != 281:
                items['result'] = ""
                items['code'] = 480
                items['message'] = "Error while inserting values in database"

                return items

            #print("4")
            items['result'] = {
                'first_name': firstName,
                'last_name': lastName,
                'customer_uid': NewUserID,
                'access_token': access_token,
                'refresh_token': refresh_token
            }
            items['message'] = 'Signup successful'
            items['code'] = 200

            print('sss-----', social_signup)

            if social_signup == False:
                token = s.dumps(email)
                msg = Message("Email Verification", sender='ptydtesting@gmail.com', recipients=[email])

                print('MESSAGE----', msg)
                print('message complete')
                link = url_for('confirm', token=token, hashed=password, _external=True)
                print('link---', link)
                msg.body = "Click on the link {} to verify your email address.".format(link)
                print('msg-bd----', msg.body)
                mail.send(msg)

            return items
        except:
            print("Error happened while Sign Up")
            if "NewUserID" in locals():
                execute("""DELETE FROM customers WHERE customer_uid = '""" + NewUserID + """';""", 'post', conn)
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

# confirmation page
@app.route('/api/v2/confirm', methods=['GET'])
def confirm():
    try:
        token = request.args['token']
        hashed = request.args['hashed']
        print("hased: ", hashed)
        email = s.loads(token)  # max_age = 86400 = 1 day

        # marking email confirmed in database, then...
        conn = connect()
        query = """UPDATE customers SET email_verified = 1 WHERE customer_email = \'""" + email + """\';"""
        update = execute(query, 'post', conn)
        if update.get('code') == 281:
            # redirect to login page
            # only for testing on localhost
            #return redirect('http://localhost:3000/login?email={}&hashed={}'.format(email, hashed))
            return redirect('https://mealtoyourdoor.netlify.app/?email={}&hashed={}'.format(email, hashed))
        else:
            print("Error happened while confirming an email address.")
            error = "Confirm error."
            err_code = 401  # Verification code is incorrect
            return error, err_code
    except (SignatureExpired, BadTimeSignature) as err:
        status = 403  # forbidden
        return str(err), status
    finally:
        disconnect(conn)







'''
class Login (Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            email = data['email']
            password = data.get('password')
            refresh_token = data.get('token')
            query = """
                    # CUSTOMER QUERY 1: LOGIN
                    SELECT customer_uid,
                            customer_last_name,
                            customer_first_name,
                            customer_email, 	
                            password_hashed, 	
                            email_verified, 	
                            user_social_media,
                            user_access_token,
                            user_refresh_token  
                    FROM sf.customers c 
                    -- WHERE customer_email = "1m4kfun@gmail.com";
                    WHERE customer_email = \'""" + email + """\';
                    """
            res = simple_get_execute(query, __class__.__name__, conn)
            if res[1] == 500:
                response['message'] = "Internal Server Error."
                return response, 500
            elif res[1] == 204:
                response['message'] = 'Email Not Found'
                return response, 404
            else:
                user_social_media = res[0]['result'][0]['user_social_media']
                if password is not None and user_social_media is not None:
                    response['message'] = "Need to login by Social Media"
                    return response, 401
                elif (password is None and refresh_token is None) or (password is None and user_social_media is None):
                    return BadRequest("Bad request.")
                # compare passwords if user_social_media is false
                elif user_social_media is None and password is not None:
                    if res[0]['result'][0]['password_hashed'] != password:
                        response['message'] = "Wrong password."
                        return response, 401
                    if (int(res[0]['result'][0]['email_verified']) == 0) or (res[0]['result'][0]['email_verified'] == "FALSE"):
                        response['message'] = "Account need to be verified by email."
                        return response, 401
                # compare the refresh token because it never expire.
                elif (user_social_media != 'NULL' and user_social_media is not None):
                    if (res[0]['result'][0]['user_refresh_token'] != refresh_token):
                        response['message'] = "Cannot Authenticated. Token is invalid."
                        return response, 401
                else:
                    string = " Cannot compare the password or refresh token while log in. "
                    print("*" * (len(string) + 10))
                    print(string.center(len(string) + 10, "*"))
                    print("*" * (len(string) + 10))
                    response['message'] = 'Internal Server Error.'
                    return response, 500

                del res[0]['result'][0]['password_hashed']
                del res[0]['result'][0]['email_verified']

                response['message'] = "Authenticated success."
                response['result'] = res[0]['result'][0]
                return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
'''   



class Login(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            email = data['email']
            password = data.get('password')
            refresh_token = data.get('token')
            #signup_platform = data.get('signup_platform')
            query = """
                    # CUSTOMER QUERY 1: LOGIN
                    SELECT customer_uid,
                        customer_last_name,
                        customer_first_name,
                        customer_email,
                        password_hashed,
                        email_verified,
                        user_social_media,
                        user_access_token,
                        user_refresh_token
                    FROM sf.customers c
                    -- WHERE customer_email = "1m4kfun@gmail.com";
                    WHERE customer_email = \'""" + email + """\';
                    """
            items = execute(query, 'get', conn)
            print('Password', password)
            print(items)

            if items['code'] != 280:
                response['message'] = "Internal Server Error."
                response['code'] = 500
                return response
            elif not items['result']:
                items['message'] = 'Email Not Found. Please signup'
                items['result'] = ''
                items['code'] = 404
                return items
            else:
                print(items['result'])
                print('sc: ', items['result'][0]['user_social_media'])


                # checks if login was by social media
                if password and items['result'][0]['user_social_media'] != 'NULL' and items['result'][0]['user_social_media'] != None:
                    response['message'] = "Need to login by Social Media"
                    response['code'] = 401
                    return response

               # nothing to check
                elif (password is None and refresh_token is None) or (password is None and items['result'][0]['user_social_media'] == 'NULL'):
                    response['message'] = "Enter password else login from social media"
                    response['code'] = 405
                    return response

                # compare passwords if user_social_media is false
                elif (items['result'][0]['user_social_media'] == 'NULL' or items['result'][0]['user_social_media'] == None) and password is not None:

                    if items['result'][0]['password_hashed'] != password:
                        items['message'] = "Wrong password"
                        items['result'] = ''
                        items['code'] = 406
                        return items

                    if ((items['result'][0]['email_verified']) == '0') or (items['result'][0]['email_verified'] == "FALSE"):
                        response['message'] = "Account need to be verified by email."
                        response['code'] = 407
                        return response

                # compare the refresh token because it never expire.
                elif (items['result'][0]['user_social_media']) != 'NULL':
                    '''
                    keep
                    if signup_platform != items['result'][0]['user_social_media']:
                        items['message'] = "Wrong social media used for signup. Use \'" + items['result'][0]['user_social_media'] + "\'."
                        items['result'] = ''
                        items['code'] = 401
                        return items
                    '''
                    if (items['result'][0]['user_refresh_token'] != refresh_token):
                        print(items['result'][0]['user_refresh_token'])

                        items['message'] = "Cannot Authenticated. Token is invalid"
                        items['result'] = ''
                        items['code'] = 408
                        return items

                else:
                    string = " Cannot compare the password or refresh token while log in. "
                    print("*" * (len(string) + 10))
                    print(string.center(len(string) + 10, "*"))
                    print("*" * (len(string) + 10))
                    response['message'] = string
                    response['code'] = 500
                    return response
                del items['result'][0]['password_hashed']
                del items['result'][0]['email_verified']

                query = "SELECT * from sf.customers WHERE customer_email = \'" + email + "\';"
                items = execute(query, 'get', conn)
                items['message'] = "Authenticated successfully."
                items['code'] = 200
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)







'''
class AppleLogin (Resource):
    def post(self):
        try:
            token = request.form.get('id_token')
            if token:
                data = jwt.decode(token, verify=False)
                email = data.get('email')
                sub = data.get('sub')
                if email is not None:
                    return redirect("http://127.0.0.1:3000/?email={}&token={}".format(email, sub))
                else:
                    response = {
                        "message": "Not Found user's email in Apple's Token."
                    }
                    return response, 400
            else:
                response = {
                    "message": "Not found token "
                               ""
                               "in Apple's Response"
                }
                return response, 400
        except:
            raise BadRequest("Request failed, please try again later.")
'''



class AppleLogin (Resource):

    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            token = request.form.get('id_token')
            print(token)
            if token:
                print('INN')
                data = jwt.decode(token, verify=False)
                print('data-----', data)
                email = data.get('email')

                print(data, email)
                if email is not None:
                    sub = data['sub']
                    query = """
                    SELECT customer_uid,
                        customer_last_name,
                        customer_first_name,
                        customer_email,
                        password_hashed,
                        email_verified,
                        user_social_media,
                        user_access_token,
                        user_refresh_token
                    FROM sf.customers c
                    WHERE customer_email = \'""" + email + """\';
                    """
                    items = execute(query, 'get', conn)
                    print(items)

                    if items['code'] != 280:
                        items['message'] = "Internal error"
                        return items


                    # new customer
                    if not items['result']:
                        items['message'] = "Email doesn't exists Please go to the signup page"
                        get_user_id_query = "CALL new_customer_uid();"
                        NewUserIDresponse = execute(get_user_id_query, 'get', conn)

                        if NewUserIDresponse['code'] == 490:
                            string = " Cannot get new User id. "
                            print("*" * (len(string) + 10))
                            print(string.center(len(string) + 10, "*"))
                            print("*" * (len(string) + 10))
                            response['message'] = "Internal Server Error."
                            response['code'] = 500
                            return response

                        NewUserID = NewUserIDresponse['result'][0]['new_id']
                        user_social_signup = 'APPLE'
                        print('NewUserID', NewUserID)
                        #only works for mysql, and only allows for inserting one row at a time
                        customer_insert_query = """
                                    INSERT INTO sf.customers 
                                    set
                                        customer_uid = \'""" + NewUserID + """\',
                                        customer_created_at = \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
                                        customer_email = \'""" + email + """\',
                                        user_social_media = \'""" + user_social_signup + """\',
                                        user_refresh_token = \'""" + sub + """\'
                                    ;"""


                                    #original code for reference
                                    #   INSERT INTO sf.customers 
                                    # (
                                    #     customer_uid,
                                    #     customer_created_at,
                                    #     customer_email,
                                    #     user_social_media,
                                    #     user_refresh_token
                                    # )
                                    # VALUES
                                    # (
                                    
                                    #     \'""" + NewUserID + """\',
                                    #     \'""" + (datetime.now()).strftime("%Y-%m-%d %H:%M:%S") + """\',
                                    #     \'""" + email + """\',
                                    #     \'""" + user_social_signup + """\',
                                    #     \'""" + sub + """\'
                                    # );"""


                        item = execute(customer_insert_query, 'post', conn)

                        print('INSERT')

                        #if sql works, and new user then social sign up
                        if item['code'] != 281:
                            item['message'] = 'Check insert sql query'
                            return item
                        #applelogin changes
                        return redirect("https://mealtoyourdoor.netlify.app/social-sign-up")
                        #return redirect("http://localhost:3000/social-sign-up?id=" + NewUserID)

                    # Existing customer

                    #if we get back a refresh token
                    if items['result'][0]['user_refresh_token']:
                        print(items['result'][0]['user_social_media'], items['result'][0]['user_refresh_token'])

                        #if result is not apple
                        if items['result'][0]['user_social_media'] != "APPLE":
                            items['message'] = "Wrong social media used for signup. Use \'" + items['result'][0]['user_social_media'] + "\'."
                            items['code'] = 400
                            return redirect("https://mealtoyourdoor.netlify.app/")
                            #return redirect("http://localhost:3000")
                            #return items

                        #if referesh token does not match
                        elif items['result'][0]['user_refresh_token'] != sub:
                            items['message'] = "Token mismatch"
                            items['code'] = 400
                            return redirect("https://mealtoyourdoor.netlify.app/")
                            #return redirect("http://localhost:3000")
                            #return items

                        #if social media = apple, and token matches, send to meals selected
                        else:
                            #applelogin changes
                            # return redirect("http://localhost:3000/farms?id=" + items['result'][0]['customer_uid'])
                            return redirect("https://mealtoyourdoor.netlify.app/meals_selected?customer_uid=" + items['result'][0]['customer_uid'])
                            #return redirect("http://localhost:3000/select-meal?id=" + items['result'][0]['customer_uid'])

                else:
                    items['message'] = "Email not returned by Apple LOGIN"
                    items['code'] = 400
                    return items


            else:
                response = {
                    "message": "Token not found in Apple's Response",
                    "code": 400
                }
                return response
        except:
            raise BadRequest("Request failed, please try again later.")





class Change_Password(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            customer_uid = data['customer_uid']
            old_pass = data['old_password']
            new_pass = data['new_password']
            query = """
                        SELECT customer_email, password_hashed, password_salt, password_algorithm
                        FROM customers WHERE customer_uid = '""" + customer_uid + """';
                    """
            query_res = simple_get_execute(query, "CHANGE PASSWORD QUERY", conn)
            if query_res[1] != 200:
                return query_res
            # because the front end will send back plain password, We need to salt first
            # checking for identity
            old_salt = query_res[0]['result'][0]['password_salt']
            old_password_hashed = sha512((old_pass + old_salt).encode()).hexdigest()
            if old_password_hashed != query_res[0]['result'][0]['password_hashed']:
                response['message'] = "Wrong Password"
                return response, 401
            # create a new salt and hashing the new password
            new_salt = getNow()
            algorithm = query_res[0]['result'][0]['password_algorithm']
            if algorithm == "SHA512" or algorithm is None or algorithm == "":
                new_password_hashed = sha512((new_pass + new_salt).encode()).hexdigest()
            else: # if we have saved the hashing algorithm in our database,
                response['message'] = "Cannot change Password. Need the algorithm to hashed the new password."
                return response, 500
            update_query = """
                            UPDATE customers SET password_salt = '""" + new_salt + """', 
                                password_hashed = '""" + new_password_hashed + """'
                                WHERE customer_uid = '""" + customer_uid + """';
                            """
            update_query_res = simple_post_execute([update_query], ["UPDATE PASSWORD"], conn )
            if update_query_res[1] != 201:
                return update_query_res
            response['message'] = "Password updated."
            return response, 201
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Reset_Password(Resource):
    def get_random_string(self, stringLength=8):
        lettersAndDigits = string.ascii_letters + string.digits
        return "".join([random.choice(lettersAndDigits) for i in range(stringLength)])

    def get(self):
        response = {}
        try:
            conn = connect()
            # search for email;
            email = request.args['email']

            query = """SELECT * FROM customers
                    WHERE customer_email ='""" + email + "';"
            customer_lookup = simple_get_execute(query, "RESET PASSWORD QUERY", conn)
            if customer_lookup[1] != 200:
                return customer_lookup

            customer_uid = customer_lookup[0]['result'][0]['customer_uid']
            pass_temp = self.get_random_string()
            salt = getNow()
            pass_temp_hashed = sha512((pass_temp + salt).encode()).hexdigest()
            query = """
                    UPDATE customers SET password_hashed = '""" + pass_temp_hashed + """'
                     , password_salt = '""" + salt + """' 
                     WHERE customer_uid = '""" + customer_uid + """';
                    """
            # update database with temp password
            query_result = simple_post_execute([query], ["UPDATE RESET PASSWORD"], conn)
            if query_result[1]!= 201:
                return query_result
            # send an email to client
            msg = Message(
                "Email Verification", sender='ptydtesting@gmail.com', recipients=[email])
            msg.body = "Your temporary password is {}. Please use it to reset your password".format(pass_temp)
            mail.send(msg)
            response['message'] = "A temporary password has been sent"
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selected(Resource):
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            query = """
                    # CUSTOMER QUERY 3: ALL MEAL SELECTIONS BY CUSTOMER  (INCLUDES HISTORY)
                    SELECT * FROM sf.latest_combined_meal lcm
                    LEFT JOIN sf.lplp
                        ON lcm.sel_purchase_id = lplp.purchase_id
                    WHERE pur_customer_uid = '""" + customer_uid + """';
                    """



            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selected_Specific(Resource):
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            purchase_id = request.args['purchase_id']
            menu_date = request.args['menu_date']
            query = """
                    # CUSTOMER QUERY 3: ALL MEAL SELECTIONS BY CUSTOMER  (INCLUDES HISTORY)
                    SELECT * FROM sf.latest_combined_meal lcm
                    LEFT JOIN sf.lplp
                        ON lcm.sel_purchase_id = lplp.purchase_id
                    WHERE pur_customer_uid = '""" + customer_uid + """'
                    and purchase_id = '""" + purchase_id + """'
                    and sel_menu_date = '""" + menu_date + """';
                    """



            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)



class Get_Upcoming_Menu(Resource):
    def get(self):
        try:
            conn = connect()
            # menu_date = request.args['menu_date']
            query = """
                    # CUSTOMER QUERY 4: UPCOMING MENUS
                    SELECT * FROM sf.menu
                    LEFT JOIN sf.meals m
                        ON menu.menu_meal_id = m.meal_uid
                    WHERE menu_date > CURDATE();
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Get_Latest_Purchases_Payments(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            query = """
                    # CUSTOMER QUERY 2: CUSTOMER LATEST PURCHASE AND LATEST PAYMENT HISTORY
                    # NEED CUSTOMER ADDRESS IN CASE CUSTOMER HAS NOT ORDERED BEFORE
                    SELECT * FROM sf.lplp
                    LEFT JOIN sf.customers c
                        ON lplp.pur_customer_uid = c.customer_uid
                    WHERE pur_customer_uid = '""" + customer_uid + """';
                    """
            response = simple_get_execute(query, __class__.__name__, conn)
            if response[1] != 200:
                return response
            except_list = ['password_hashed', 'password_salt', 'password_algorithm']
            for i in range(len(response[0]['result'])):
                for key in except_list:
                     if response[0]['result'][i].get(key) is not None:
                        del response[0]['result'][i][key]
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
class Next_Billing_Date(Resource):
    def get(self):
        try:
            conn = connect()
            customer_uid = request.args['customer_uid']
            query = """
                        # CUSTOMER QUERY 5: NEXT SUBSCRIPTION BILLING DATE (WITH TRUE_SKIPS)
                        SELECT *,
                            IF (nbd.true_skips > 0,
                            ADDDATE(nbd.start_delivery_date, (nbd.num_issues + nbd.true_skips) * 7 / nbd.deliveries_per_week - 3),
                            ADDDATE(nbd.start_delivery_date, (nbd.num_issues +        0      ) * 7 / nbd.deliveries_per_week - 3) ) AS next_billing_date
                        FROM (
                            SELECT lplpibr.*,
                                si.*,
                                ts.true_skips
                            FROM sf.lplp_items_by_row AS lplpibr
                            LEFT JOIN sf.subscription_items si
                                ON lplpibr.lplpibr_jt_item_uid = si.item_uid
                            LEFT JOIN sf.true_skips AS ts
                                ON lplpibr.lplpibr_purchase_id = ts.d_purchase_id) AS nbd
                        WHERE lplpibr_customer_uid = '""" + customer_uid + """';
                        """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Next_Addon_Charge(Resource):
    def get(self):
        try:
            conn = connect()
            purchase_uid = request.args['purchase_uid']
            query = """
                        # CUSTOMER QUERY 6: NEXT ADDONS BILLING DATE AND AMOUNT
                        SELECT *,
                            MIN(sel_menu_date)
                        FROM (
                                SELECT *,
                                        SUM(addon_charge)
                                FROM (
                                    SELECT *,
                                        jt_qty * jt_price AS addon_charge
                                    FROM sf.selected_addons_by_row
                                    WHERE sel_menu_date >= ADDDATE(CURDATE(), -28) ) 
                                    AS meal_aoc
                                GROUP BY selection_uid
                                ORDER BY sel_purchase_id, sel_menu_date ASC) 
                            AS sum_aoc
                        WHERE sel_purchase_id = '""" + purchase_uid + """'
                        GROUP BY sel_purchase_id;
                        """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

# class AccountSalt(Resource):
#     def get(self):
#         try:
#             conn = connect()
#             email = request.args['email']
#             query = """
#                     SELECT password_algorithm, 
#                             password_salt 
#                     FROM customers cus
#                     WHERE customer_email = \'""" + email + """\';
#                     """
#             return simple_get_execute(query, __class__.__name__, conn)
#         except:
#             raise BadRequest('Request failed, please try again later.')
#         finally:
#             disconnect(conn)


class AccountSalt(Resource):
    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            email = data['email']
            query = """
                    SELECT password_algorithm, 
                            password_salt 
                    FROM customers cus
                    WHERE customer_email = \'""" + email + """\';
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)






class Checkout(Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            customer_uid = data['customer_uid']
            business_uid = data['business_uid']
            delivery_first_name = data['delivery_first_name']
            delivery_last_name = data['delivery_last_name']
            delivery_email = data['delivery_email']
            delivery_phone = data['delivery_phone']
            delivery_address = data['delivery_address']
            #delivery_unit = data['delivery_unit']
            delivery_unit = data['unit'] if data.get('unit') is not None else 'NULL'
            delivery_city = data['delivery_city']
            delivery_state = data['delivery_state']
            delivery_zip = data['delivery_zip']
            delivery_instructions = "'" + data['delivery_instructions'] + "'" if data.get('delivery_instructions') else 'NULL'
            delivery_longitude = data['delivery_longitude']
            delivery_latitude = data['delivery_latitude']

            items = "'[" + ", ".join([str(item).replace("'", "\"") if item else "NULL" for item in data['items']]) + "]'"
            order_instructions = "'" + data['order_instructions'] + "'" if data.get('order_instructions') is not None else 'NULL'
            purchase_notes = "'" + data['purchase_notes'] + "'" if data.get('purchase_notes') is not None else 'NULL'
            amount_due = data['amount_due']
            amount_discount = data['amount_discount']
            amount_paid = data['amount_paid']
            cc_num = data['cc_num']
            cc_exp_date = data['cc_exp_year'] + data['cc_exp_month'] + "01"
            cc_cvv = data['cc_cvv']
            cc_zip = data['cc_zip']
            amount_must_paid = float(amount_due) - float(amount_paid) - float(amount_discount)
            # We should sanitize the variable before writting into database.
            # must pass these check first
            if items == "'[]'":
                raise BadRequest()
            
            purchaseId = get_new_purchaseID(conn)
            if purchaseId[1] == 500:
                print(purchaseId[0])
                response['message'] = "Internal Server Error."
                return response, 500
            paymentId = get_new_paymentID(conn)
            if paymentId[1] == 500:
                print(paymentId[0])
                response['message'] = "Internal Server Error."
                return response, 500
            # User authenticated
            # check the customer_uid and see what kind of registration.
            # if it was registered by email then check the password.
            customer_query = """SELECT * FROM customers WHERE customer_uid = '""" + data['customer_uid'] + """';"""
            customer_res = execute(customer_query, 'get', conn)

            if customer_res['code'] != 280 or not customer_res['result']:
                response['message'] = "Could not authenticate user"
                return response, 401
            # if customer_res['result'][0]['password_hashed'] is not None: original
            #print(customer_res['result'][0]['password_hashed'])
            #print(data['salt'])
            print("1")
            if customer_res['result'][0]['password_hashed'] != 'NULL' and customer_res['result'][0]['password_hashed'] is not None:
                if customer_res['result'][0]['password_hashed'] != data['salt']:
                    response['message'] = "Could not authenticate user. Wrong Password"
                    return response, 401
            # Validate credit card
            # if str(data['cc_num'][0:12]) == "XXXXXXXXXXXX":
            #     latest_purchase = get_latest_purchases(business_id, customer_uid)
            #     if latest_purchase['result'] is None:
            #         response['message'] = "Credit card number is invalid."
            #         return response, 400
            #     if str(latest_purchase['result']['cc_num'][:-4]) != str(data['cc_num'][:-4]):
            #         response['message'] = "Credit card number is invalid."
            #         return response, 400
            #     cc_num = latest_purchase['result']['cc_num']

            # create a stripe charge and make sure that charge is successful before writing it into database
            # we should use Idempotent key to prevent sending multiple payment requests due to connection fail.
            # Also, It is not safe for using Strip Charge API. We should use Stripe Payment Intent API and its SDKs instead.
            try:
                # create a token for stripe
                card_dict = {"number": data['cc_num'], "exp_month": int(data['cc_exp_month']), "exp_year": int(data['cc_exp_year']),"cvc": data['cc_cvv']}
                stripe_charge = {}
                try:
                    card_token = stripe.Token.create(card=card_dict)

                    if int(amount_must_paid) > 0:
                        stripe_charge = stripe.Charge.create(
                            amount=int(round(amount_must_paid*100, 0)),
                            currency="usd",
                            source=card_token,
                            description="Charge customer for new Subscription")
                    # update amount_paid. At this point, the payment has been processed so amount_paid == amount_due
                    amount_paid = amount_due
                except stripe.error.CardError as e:
                    # Since it's a decline, stripe.error.CardError will be caught
                    response['message'] = e.error.message
                    return response, 400

                # update coupon table
                coupon_id = data.get('coupon_id')
                if str(coupon_id) != "" and coupon_id is not None:
                    # update coupon table
                    coupon_id = "'" + coupon_id + "'"
                    coupon_query = """UPDATE coupons SET num_used = num_used + 1
                                WHERE coupon_id =  """ + str(coupon_id) + ";"
                    res = execute(coupon_query, 'post', conn)
                else:
                    coupon_id = 'NULL'
                charge_id = 'NULL' if stripe_charge.get('id') is None else "'" + stripe_charge.get('id') + "'"
                #calculate the start_delivery_date

                dayOfWeek = datetime.now().weekday()

                # Get the soonest Thursday, same day if today is Thursday
                thurs = datetime.now() + timedelta(days=(3 - dayOfWeek) % 7)

                # If today is Thursday after 4PM'
                if thurs.date() == datetime.now().date() and datetime.now().hour >= 16:
                    thurs += timedelta(days=7)

                #the next saturday
                start_delivery_date = (thurs + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
                # write into Payments table
                queries = [
                            '''
                            INSERT INTO sf.payments
                            SET payment_uid = \'''' + paymentId + '''\',
                                payment_time_stamp = \'''' + getNow() + '''\',
                                start_delivery_date = \'''' + start_delivery_date + '''\',
                                payment_id = \'''' + paymentId + '''\',
                                pay_purchase_id = \'''' + purchaseId + '''\',
                                pay_purchase_uid = \'''' + purchaseId + '''\',
                                amount_due = \'''' + amount_due + '''\',
                                amount_discount = \'''' + amount_discount + '''\',
                                amount_paid = \'''' + amount_paid + '''\',
                                pay_coupon_id = ''' + coupon_id + ''',
                                charge_id = ''' + charge_id + ''',
                                payment_type = 'STRIPE',
                                info_is_Addon = 'FALSE',
                                cc_num = \'''' + cc_num  + '''\', 
                                cc_exp_date = \'''' + cc_exp_date + '''\', 
                                cc_cvv = \'''' + cc_cvv + '''\', 
                                cc_zip = \'''' + cc_zip + '''\';
                            ''',
                            '''
                            INSERT INTO  sf.purchases
                            SET purchase_uid = \'''' + purchaseId + '''\',
                                purchase_date = \'''' + getToday() + '''\',
                                purchase_id = \'''' + purchaseId + '''\',
                                purchase_status = 'ACTIVE',
                                pur_customer_uid = \'''' + customer_uid + '''\',
                                pur_business_uid = \'''' + business_uid + '''\',
                                delivery_first_name = \'''' + delivery_first_name + '''\',
                                delivery_last_name = \'''' + delivery_last_name + '''\',
                                delivery_email = \'''' + delivery_email + '''\',
                                delivery_phone_num = \'''' + delivery_phone + '''\',
                                delivery_address = \'''' + delivery_address + '''\',
                                delivery_unit = \'''' + delivery_unit + '''\',
                                delivery_city = \'''' + delivery_city + '''\',
                                delivery_state = \'''' + delivery_state + '''\',
                                delivery_zip = \'''' + delivery_zip + '''\',
                                delivery_instructions = ''' + delivery_instructions + ''',
                                delivery_longitude = \'''' + delivery_longitude + '''\',
                                delivery_latitude = \'''' + delivery_latitude + '''\',
                                items = ''' + items + ''',
                                order_instructions = ''' + order_instructions + ''',
                                purchase_notes = ''' + purchase_notes + ''';'''
                            ]
                response = simple_post_execute(queries, ["PAYMENTS", "PURCHASES"], conn)
                if response[1] == 201:
                    response[0]['payment_id'] = paymentId
                    response[0]['purchase_id'] = purchaseId
                else:
                    if "paymentId" in locals() and "purchaseId" in locals():
                        execute("""DELETE FROM payments WHERE payment_uid = '""" + paymentId + """';""", 'post', conn)
                        execute("""DELETE FROM purchases WHERE purchase_uid = '""" + purchaseId + """';""", 'post', conn)
                return response
                # return "OK", 201
            except:

                response = {'message': "Payment process error."}
                return response, 500
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Meals_Selection (Resource):
    def post(self):
        response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            purchase_id = data['purchase_id']
            items_selected = "'[" + ", ".join([str(item).replace("'", "\"") for item in data['items']]) + "]'"
            delivery_day = data['delivery_day']
            sel_menu_date = data['menu_date']

            if data['is_addon']:
                res = execute("CALL new_addons_selected_uid();", 'get', conn)
            else:
                res = execute("CALL new_meals_selected_uid();", 'get', conn)
            if res['code'] != 280:
                print("*******************************************")
                print("* Cannot run the query to get a new \"selection_uid\" *")
                print("*******************************************")
                response['message'] = 'Internal Server Error.'
                return response, 500
            selection_uid = res['result'][0]['new_id']
            queries = [[
                        """
                        INSERT INTO addons_selected
                        SET selection_uid = '""" + selection_uid + """',
                            sel_purchase_id = '""" + purchase_id + """',
                            selection_time = '""" + getNow() + """',
                            sel_menu_date = '""" + sel_menu_date + """',
                            meal_selection = """ + items_selected + """,
                            delivery_day = '""" + delivery_day + """';
                        """
                        ],
                       [
                       """
                       INSERT INTO meals_selected
                       SET selection_uid = '""" + selection_uid + """',
                        sel_purchase_id = '""" + purchase_id + """',
                        selection_time = '""" + getNow() + """',
                        sel_menu_date = '""" + sel_menu_date + """',
                        meal_selection = """ + items_selected + """,
                        delivery_day = '""" + delivery_day + """';
                        """
                       ]]

            if data['is_addon'] == True:
                # write to addons selected table
                # need a stored function to get the new selection
                response = simple_post_execute(queries[0], ["ADDONS_SELECTED"], conn)
            else:
                response = simple_post_execute(queries[1], ["MEALS_SELECTED"], conn)
            if response[1] == 201:
                response[0]['selection_uid']= selection_uid
            return response
        except:
            if "selection_uid" in locals():
                execute("DELETE FROM addons_selected WHERE selection_uid = '" + selection_uid + "';", 'post', conn)
                execute("DELETE FROM meals_selected WHERE selection_uid = '" + selection_uid + "';", 'post', conn)
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

class Change_Purchase (Resource):
    def refund_calculator(self, info_res,  conn):
        # Getting the original start and end date for requesting purchase
        start_delivery_date = datetime.strptime(info_res['start_delivery_date'], "%Y-%m-%d %H-%M-%S")
        # check for SKIP. Let consider the simple case. The customer can change their purchases if and only if their purchase
        # still active.
        week_remaining = int(info_res['payment_frequency'])

        end_delivery_date = start_delivery_date + timedelta(days=(week_remaining) * 7)
        skip_query = """
                    SELECT COUNT(delivery_day) AS skip_count FROM 
                        (SELECT sel_purchase_id, sel_menu_date, max(selection_time) AS max_selection_time FROM meals_selected
                            WHERE sel_purchase_id = '""" + info_res['purchase_id'] + """'
                            GROUP BY sel_menu_date) AS GB 
                            INNER JOIN meals_selected S
                            ON S.sel_purchase_id = GB.sel_purchase_id
                                AND S.sel_menu_date = GB.sel_menu_date
                                AND S.selection_time = GB.max_selection_time
                    WHERE S.sel_menu_date >= '""" + start_delivery_date.strftime("%Y-%m-%d %H-%M-%S") + """'
                        AND S.sel_menu_date <= '""" + datetime.now().strftime("%Y-%m-%d %H-%M-%S") + """'
                        AND delivery_day = 'SKIP'
                    ORDER BY S.sel_menu_date;
                    """
        skip_res = simple_get_execute(skip_query, "SKIP QUERY", conn)
        if skip_res[1] != 200:
            return skip_res
        skip = int(skip_res[0].get('skip_count')) if skip_res[0].get('skip_count') else 0
        if datetime.now().date() > start_delivery_date.date():
            delivered = (datetime.now().date() - start_delivery_date.date()).days//7 + 1 - skip
            week_remaining -= delivered
        elif (datetime.now().date() > end_delivery_date):
            print("There is something wrong with the query to get info for the requested purchase.")
            response = {'message': "Internal Server Error."}
            return response, 500
        customer_paid = float(info_res['amount_paid'])
        # get the price of the new item.
        items_query = """
                        SELECT * FROM subscription_items
                        WHERE item_name = '""" + info_res['item_name'] + """'
                        """
        items_res = simple_get_execute(items_query, "GET Subscription_items QUERY", conn)
        if items_res[1] != 200:
            return items_res
        price = {}
        for item in items_res[0]['result']:
            price[item['num_issues']] = item['item_price']
        refund = 0
        if info_res['num_issues'] == 4: # 4 week prepaid
            print("matching 4 week pre-pay")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid - float(price[2]) - float(price[1])
            elif week_remaining == 2:
                refund = customer_paid - float(price[2])
            elif week_remaining == 3:
                refund = customer_paid - float(price[2])
            elif week_remaining == 4:
                refund = customer_paid
        elif info_res['num_issues'] == 2:
            print("matching 2 week Pre-pay")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid - float(price['1'])
            elif week_remaining == 2:
                refund = customer_paid
        elif info_res['num_issues'] == 1:
            print("matching weekly")
            if week_remaining == 0:
                refund = 0
            elif week_remaining == 1:
                refund = customer_paid
        return {"week_remaining": week_remaining, "refund_amount": refund}

    def stripe_refund (self, refund_info, conn):
        refund_amount = refund_info['refund_amount']
        # retrieve charge info from stripe
        if refund_info['stripe_charge_id']:
            stripe_retrieve_info = stripe.Charge.retrieve(refund_info['stripe_charge_id'])
            print(stripe_retrieve_info)
            return "OK"
        else:
            return None

    def post(self):
        try:
            conn = connect()
            # For this update_purchase endpoint, we should consider to ask customer provide their identity to make sure the right
            # person is doing what he/she want.
            # Also, using POST to protect sensitive information.
            data = request.get_json(force=True)
            customer_email = data['customer_email']
            password = data.get('password')
            refresh_token = data.get('refresh_token')
            cc_num = data['cc_num']
            cc_exp_date = data['cc_exp_date']
            cc_cvv = data['cc_cvv']
            purchase_id = data['purchase_id']
            new_item_id = data['new_item_id']
            #print("1")
            #Check user's identity
            cus_query = """
                        SELECT password_hashed,
                                user_refresh_token
                        FROM customers
                        WHERE customer_email = '""" + customer_email + """';
                        """
            cus_res = simple_get_execute(cus_query, "Update_Purchase - Check Login", conn)

            if cus_res[1] != 200:
                return cus_res
            if (not password and not refresh_token):
                raise BadRequest("Request failed, please try again later.")
            elif password:
                if password != cus_res[0]['result'][0]['password_hashed']:
                    response['message'] = 'Wrong password'
                    return response, 401
            elif refresh_token:
                if refresh_token != cus_res[0]['result']['user_refresh_token']:
                    response['message'] = 'Token Invalid'
                    return response, 401
            # query info for requesting purchase
            # Get info of requesting purchase_id
            info_query = """
                                    SELECT pur.*, pay.*, sub.*
                                    FROM purchases pur, payments pay, subscription_items sub
                                    WHERE pur.purchase_id = pay.pay_purchase_id
                                        AND sub.item_uid = (SELECT json_extract(items, '$[0].item_uid') item_uid 
                                                                FROM purchases WHERE purchase_id = '""" + purchase_id + """')
                                        AND pur.purchase_id = '""" + purchase_id + """'
                                        AND pur.purchase_status='ACTIVE';  
                                    """
            info_res = simple_get_execute(info_query, 'GET INFO FOR CHANGING PURCHASE', conn)
            if info_res[1] != 200:
                return info_res
            # Calculate refund
            refund_info = self.refund_calculator(info_res[0]['result'][0], conn)

            refund_amount = refund_info['refund_amount']

            # price for the new purchase
            item_query = """
                        SELECT * FROM subscription_items 
                        WHERE item_uid = '""" + new_item_id + """';
                        """
            item_res = simple_get_execute(item_query, "QUERY PRICE FOR NEW PURCHASE.", conn)
            if item_res[1] != 200:
                return item_res
            amount_will_charge = float(item_res[0]['result'][0]['item_price']) - refund_amount
            # Process stripe
            print("amount_will_charge: ", amount_will_charge)
            if amount_will_charge > 0:
                #charge with stripe
                pass

            elif amount_will_charge < 0:
                # establishing more info for refund_info before we feed it in stripe_refund
                refund_info['refund_amount'] = 0 - amount_will_charge

                refund_info['stripe_charge_id'] = info_res[0]['result'][0]['charge_id']
                self.stripe_refund(refund_info, conn)
                # refund
            # write the new purchase_id and payment_id into database

            # return new purchase_id
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)


# ---------- ADMIN ENDPOINTS ----------------#
# admin endpoints start from here            #
#--------------------------------------------#
class Plans(Resource):
    # HTTP method GET
    def get(self):
        try:
            conn = connect()
            business_uid = request.args['business_uid']
            query = """
                    # ADMIN QUERY 5: PLANS 
                    SELECT * FROM sf.subscription_items si 
                    -- WHERE itm_business_uid = "200-000007"; 
                    WHERE itm_business_uid = \'""" + business_uid + """\';
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
# Endpoint for Create/Edit menu
class Menu (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 1: 
                    #  MEALS & MENUS: 1. CREATE/EDIT MENUS: SEE MENU FOR A PARTICULAR DAY  (ADD/DELETE MENU ITEM)
                    SELECT * FROM sf.menu
                    LEFT JOIN sf.meals
                        ON menu_meal_id = meal_uid
                    WHERE menu_date > ADDDATE(CURDATE(),-21) AND menu_date < ADDDATE(CURDATE(),45);
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, Please try again later.")
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            menu_date = data['menu_date']
            menu_category = data['menu_category']
            menu_type = data['menu_type']
            meal_cat = data['meal_cat']
            menu_meal_id = data['menu_meal_id']
            default_meal = data['default_meal']
            delivery_days = "'[" + ", ".join([str(item) for item in data['delivery_days']]) + "]'"
            meal_price = data['meal_price']

            menu_uid = get_new_id("CALL new_menu_uid", "get_new_menu_ID", conn)
            if menu_uid[1] != 200:
                return menu_uid
            menu_uid = menu_uid[0]['result']

            query = """
                    INSERT INTO menu
                    SET menu_uid = '""" + menu_uid + """',
                        menu_date = '""" + menu_date + """',
                        menu_category = '""" + menu_category + """',
                        menu_type = '""" + menu_type + """',
                        meal_cat = '""" + meal_cat + """',
                        menu_meal_id = '""" + menu_meal_id + """',
                        default_meal = '""" + default_meal + """',
                        delivery_days = """ + delivery_days + """,
                        meal_price = '""" + meal_price + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = menu_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            menu_uid = request.args['menu_uid']

            query = """
                    DELETE FROM menu WHERE menu_uid = '""" + menu_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)






class Meals (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    # ADMIN QUERY 2: MEAL OPTIONS
                    SELECT * FROM sf.meals m;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            meal_category = data['meal_category']
            meal_name = data['meal_name']
            meal_desc = data['meal_desc']
            meal_hint = "'" + data['meal_hint'] + "'" if data['meal_hint'] else 'NULL'
            meal_photo_url = "'" + data['meal_photo_url'] + "'" if data['meal_photo_url'] else 'NULL'
            meal_calories = data['meal_calories']
            meal_protein = data['meal_protein']
            meal_carbs = data['meal_carbs']
            meal_fiber = data['meal_fiber']
            meal_sugar = data['meal_sugar']
            meal_fat = data['meal_fat']
            meal_sat = data['meal_sat']

            meal_uid = get_new_id("CALL new_meal_uid", "get_new_meal_ID", conn)
            if meal_uid[1] != 200:
                return meal_uid
            meal_uid = meal_uid[0]['result']

            query = """
                    INSERT INTO meals
                    SET meal_uid = '""" + meal_uid + """',
                        meal_category = '""" + meal_category + """',
                        meal_name = '""" + meal_name + """',
                        meal_desc = '""" + meal_desc + """',
                        meal_hint = """ + meal_hint + """,
                        meal_photo_url = """ + meal_photo_url + """,
                        meal_calories = '""" + meal_calories + """',
                        meal_protein = '""" + meal_protein + """',
                        meal_carbs = '""" + meal_carbs + """',
                        meal_fiber = '""" + meal_fiber + """',
                        meal_sugar = '""" + meal_sugar + """',
                        meal_fat = '""" + meal_fat + """',
                        meal_sat = '""" + meal_sat + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['meal_uid'] = meal_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            meal_uid = data['meal_uid']
            meal_category = data['meal_category']
            meal_name = data['meal_name']
            meal_desc = data['meal_desc']
            meal_hint = "'" + data['meal_hint'] + "'" if data['meal_hint'] else 'NULL'
            meal_photo_url = "'" + data['meal_photo_url'] + "'" if data['meal_photo_url'] else 'NULL'
            meal_calories = data['meal_calories']
            meal_protein = data['meal_protein']
            meal_carbs = data['meal_carbs']
            meal_fiber = data['meal_fiber']
            meal_sugar = data['meal_sugar']
            meal_fat = data['meal_fat']
            meal_sat = data['meal_sat']

            query = """
                    UPDATE meals
                    SET meal_category = '""" + meal_category + """',
                        meal_name = '""" + meal_name + """',
                        meal_desc = '""" + meal_desc + """',
                        meal_hint = """ + meal_hint + """,
                        meal_photo_url = """ + meal_photo_url + """,
                        meal_calories = '""" + meal_calories + """',
                        meal_protein = '""" + meal_protein + """',
                        meal_carbs = '""" + meal_carbs + """',
                        meal_fiber = '""" + meal_fiber + """',
                        meal_sugar = '""" + meal_sugar + """',
                        meal_fat = '""" + meal_fat + """',
                        meal_sat = '""" + meal_sat + """'
                    WHERE meal_uid = '""" + meal_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['message'] = "Update successful."
            response[0]['meal_uid'] = meal_uid
            return response
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Recipes (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 3: 
                    #  MEALS & MENUS  4. EDIT MEAL RECIPE: 
                    SELECT * FROM sf.meals
                    LEFT JOIN sf.recipes
                        ON meal_uid = recipe_meal_id
                    LEFT JOIN sf.ingredients
                        ON recipe_ingredient_id = ingredient_uid
                    LEFT JOIN sf.conversion_units
                        ON recipe_measure_id = measure_unit_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

class Ingredients (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 4: 
                    #  MEALS & MENUS  5. CREATE NEW INGREDIENT:
                    SELECT * FROM sf.ingredients
                    LEFT JOIN sf.inventory
                        ON ingredient_uid = inventory_ingredient_id
                    LEFT JOIN sf.conversion_units
                        ON inventory_measure_id = measure_unit_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            package_measure = data['package_measure']
            package_unit = data['package_unit']
            package_cost = data['package_cost']

            ingredient_uid_request = get_new_id("CALL new_ingredient_uid();", "Get_New_Ingredient_uid", conn)

            if ingredient_uid_request[1]!= 200:
                return ingredient_uid_request
            ingredient_uid = ingredient_uid_request[0]['result']
            query = """
                    INSERT INTO ingredients
                    SET ingredient_uid = '""" + ingredient_uid + """',
                        ingredient_desc = '""" + ingredient_desc + """',
                        package_size = '""" + package_size + """',
                        package_measure = '""" + package_measure + """',
                        package_unit = '""" + package_unit + """',
                        package_cost = '""" + package_cost + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['ingredient_uid'] = ingredient_uid
            return response
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            ingredient_uid = data['ingredient_uid']
            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            package_measure = data['package_measure']
            package_unit = data['package_unit']
            package_cost = data['package_cost']

            query = """
                    UPDATE ingredients
                    SET 
                        ingredient_desc = '""" + ingredient_desc + """',
                        package_size = '""" + package_size + """',
                        package_measure = '""" + package_measure + """',
                        package_unit = '""" + package_unit + """',
                        package_cost = '""" + package_cost + """'
                    WHERE ingredient_uid = '""" + ingredient_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            ingredient_uid = request.args['ingredient_uid']

            query = """
                    DELETE FROM ingredients WHERE ingredient_uid = '""" + ingredient_uid + """';
                    """
            print(query)
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Measure_Unit (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 5: 
                    #  MEALS & MENUS  6. CREATE NEW MEASURE UNIT: 
                    SELECT * FROM sf.conversion_units;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            type = data['type']
            recipe_unit = data['recipe_unit']
            conversion_ratio = data['conversion_ratio']
            common_unit = data['common_unit']

            measure_unit_uid_request = get_new_id("CALL new_measure_unit_uid();", "Get_New_Measure_Unit_uid", conn)

            if measure_unit_uid_request[1]!= 200:
                return measure_unit_uid_request
            measure_unit_uid = measure_unit_uid_request[0]['result']

            query = """
                    INSERT INTO conversion_units
                    SET measure_unit_uid = '""" + measure_unit_uid + """',
                        type = '""" + type + """',
                        recipe_unit = '""" + recipe_unit + """',
                        conversion_ratio = '""" + conversion_ratio + """',
                        common_unit = '""" + common_unit + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['measure_unit_uid'] = measure_unit_uid
            return response
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            measure_unit_uid = data['measure_unit_uid']
            type = data['type']
            recipe_unit = data['recipe_unit']
            conversion_ratio = data['conversion_ratio']
            common_unit = data['common_unit']

            query = """
                    UPDATE conversion_units
                    SET type = '""" + type + """',
                        recipe_unit = '""" + recipe_unit + """',
                        conversion_ratio = '""" + conversion_ratio + """',
                        common_unit = '""" + common_unit + """'
                    WHERE measure_unit_uid = '""" + measure_unit_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            ingredient_uid = request.args['ingredient_uid']

            query = """
                    DELETE FROM conversion_units WHERE measure_unit_uid = '""" + measure_unit_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Coupons(Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 7: 
                    # PLANS & COUPONS  2. SHOW ALL COUPONS
                    SELECT * FROM sf.coupons;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        try:
            conn = connect()
            data = request.get_json(force=True)
            coupon_id = data['coupon_id']
            valid = data['valid']
            discount_percent = data['discount_percent']
            discount_amount = data['discount_amount']
            discount_shipping = data['discount_shipping']
            expire_date = data['expire_date']
            limits = data['limits']
            notes = data['notes']
            num_used = data['num_used'] if data.get("num_used") else 0
            recurring = data['recurring']
            email_id = "'" + data['email_id'] + "'" if data['email_id'] else 'NULL'
            cup_business_uid = data['cup_business_uid']

            coupon_uid_request = get_new_id("CALL new_coupons_uid();", "Get_New_Coupons_uid", conn)
            if coupon_uid_request[1]!= 200:
                return coupon_uid_request

            coupon_uid = coupon_uid_request[0]['result']
            query = """
                    INSERT INTO coupons
                    SET coupon_uid = '""" + coupon_uid + """',
                        coupon_id = '""" + coupon_id + """',
                        valid = '""" + valid + """',
                        discount_percent = '""" + discount_percent + """',
                        discount_amount = '""" + discount_amount + """',
                        discount_shipping = '""" + discount_shipping + """',
                        expire_date = '""" + expire_date + """',
                        limits = '""" + limits + """',
                        notes = '""" + notes + """',
                        num_used = '""" + str(num_used) + """',
                        recurring = '""" + recurring + """',
                        email_id = """ + email_id + """,
                        cup_business_uid = '""" + cup_business_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            response[0]['coupon_uid'] = coupon_uid
            return response
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def put(self):
        try:
            conn = connect()
            data = request.get_json(force=True)

            coupon_uid = data['coupon_uid']
            coupon_id = data['coupon_id']
            valid = data['valid']
            discount_percent = data['discount_percent']
            discount_amount = data['discount_amount']
            discount_shipping = data['discount_shipping']
            expire_date = data['expire_date']
            limits = data['limits']
            notes = data['notes']
            num_used = data['num_used'] if data.get("num_used") else 0
            recurring = data['recurring']
            email_id = "'" + data['email_id'] + "'" if data['email_id'] else 'NULL'
            cup_business_uid = data['cup_business_uid']

            query = """
                    UPDATE coupons
                    SET coupon_id = '""" + coupon_id + """',
                        valid = '""" + valid + """',
                        discount_percent = '""" + discount_percent + """',
                        discount_amount = '""" + discount_amount + """',
                        discount_shipping = '""" + discount_shipping + """',
                        expire_date = '""" + expire_date + """',
                        limits = '""" + limits + """',
                        notes = '""" + notes + """',
                        num_used = '""" + str(num_used) + """',
                        recurring = '""" + recurring + """',
                        email_id = """ + email_id + """,
                        cup_business_uid = '""" + cup_business_uid + """'
                    WHERE coupon_uid = '""" + coupon_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 200
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)

    def delete(self):
        try:
            conn = connect()
            coupon_uid = request.args['coupon_uid']

            query = """
                    DELETE FROM coupons WHERE coupon_uid = '""" + coupon_uid + """';
                    """
            response = simple_post_execute([query], [__class__.__name__], conn)
            if response[1] != 201:
                return response
            return response[0], 202
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Ordered_By_Date(Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 9: 
                    #  ORDERS & INGREDIENTS  1. HOW MUCH HAS BEEN ORDERED BY DATE
                    #  LIKE VIEW E BUT WITH SPECIFIC COLUMNS CALLED OUT
                    SELECT d_menu_date,
                        jt_item_uid,
                        jt_name,
                        sum(jt_qty)
                    FROM(
                        SELECT *
                        FROM sf.final_meal_selection AS jot,
                        JSON_TABLE (jot.final_combined_selection, '$[*]' 
                            COLUMNS (
                                    jt_id FOR ORDINALITY,
                                    jt_item_uid VARCHAR(255) PATH '$.item_uid',
                                    jt_name VARCHAR(255) PATH '$.name',
                                    jt_qty INT PATH '$.qty',
                                    jt_price DOUBLE PATH '$.price')
                                ) AS jt)
                        AS total_ordered
                    GROUP BY d_menu_date, jt_name;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

class Ingredients_Need (Resource):
    def get(self):
        try:
            conn = connect()
            query = """
                    #  ADMIN QUERY 10: 
                    #  ORDERS & INGREDIENTS    2. WHAT INGREDIENTS NEED TO BE PURCHASED BY DATE
                    SELECT -- *,
                        d_menu_date,
                        ingredient_uid,
                        ingredient_desc,
                        sum(qty_needed), 
                        units
                    FROM(
                    SELECT *,
                        recipe_ingredient_qty / conversion_ratio AS qty_needed,
                        common_unit AS units
                    FROM (
                        SELECT d_menu_date,
                            jt_item_uid,
                            jt_name,
                            sum(jt_qty)
                        FROM(
                            SELECT *
                            FROM sf.final_meal_selection AS jot,
                            JSON_TABLE (jot.final_combined_selection, '$[*]' 
                                COLUMNS (
                                        jt_id FOR ORDINALITY,
                                        jt_item_uid VARCHAR(255) PATH '$.item_uid',
                                        jt_name VARCHAR(255) PATH '$.name',
                                        jt_qty INT PATH '$.qty',
                                        jt_price DOUBLE PATH '$.price')
                                    ) AS jt)
                                    AS total_ordered
                        GROUP BY d_menu_date, jt_name) 
                        AS ordered
                    LEFT JOIN sf.recipes
                        ON jt_item_uid = recipe_meal_id
                    LEFT JOIN sf.ingredients
                        ON recipe_ingredient_id = ingredient_uid
                    LEFT JOIN sf.conversion_units
                        ON recipe_measure_id = measure_unit_uid)
                        AS ing
                    GROUP BY d_menu_date, ingredient_uid;
                    """
            return simple_get_execute(query, __class__.__name__, conn)
        except:
            raise BadRequest("Request failed, please try again later.")
        finally:
            disconnect(conn)











class Edit_Menu(Resource):
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(""" select meal_name from meals;""", 'get', conn)
            items2 = execute(""" select * from menu;""", 'get', conn)

            response['message'] = 'Request successful.'
            response['result'] = items
            response['result2'] = items2

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)
            print("connected")
            menu_date = data['menu_date']
            menu = data['menu']
            print("data received")
            print(menu_date)
            print(menu)
            items['delete_menu'] = execute("""delete from menu
                                                        where menu_date = \'""" + str(menu_date) + """\';
                                                            """, 'post', conn)
            print("menu deleted")

            i = 0
            for eachitem in data['menu']:
                menu_category = menu[i]['menu_category']
                menu_type = menu[i]['menu_type']
                meal_cat = menu[i]['meal_cat']
                meal_name = menu[i]['meal_name']
                default_meal = menu[i]['default_meal']

                print(menu_category)
                print(menu_type)
                print(meal_cat)
                print(meal_name)
                print(default_meal)

                items['menu_insert'] = execute(""" insert into menu 
                                                    values 
                                                    (\'""" + str(menu_date) + """\',\'""" + str(menu_category) + """\',
                                                    \'""" + str(menu_type) + """\',\'""" + str(meal_cat) + """\',
                                                    (select meal_id from meals where meal_name = \'""" + str(meal_name) + """\'),
                                                    \'""" + str(default_meal) + """\');
                                                    """, 'post', conn)
                i += 1

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)












class Edit_Meal(Resource):
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()
            items = execute(""" select * from meals;""", 'get', conn)

            response['message'] = 'successful'
            response['result'] = items
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def patch(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            mealId = data['mealId']
            meal_category = data['meal_category']
            meal_name = data['meal_name']
            meal_desc = data['meal_desc']
            meal_hint = data['meal_hint']
            meal_photo_URL = data['meal_photo_URL']
            # extra_meal_price = data['extra_meal_price']
            meal_calories = data['meal_calories']
            meal_protein = data['meal_protein']
            meal_carbs = data['meal_carbs']
            meal_fiber = data['meal_fiber']
            meal_sugar = data['meal_sugar']
            meal_fat = data['meal_fat']
            meal_sat = data['meal_sat']
            print(data)
            print("Items read...")
            items['update_meal'] = execute("""update meals 
                                                set
                                                meal_category = \'""" + str(meal_category) + """\',
                                                meal_name = \'""" + str(meal_name) + """\',
                                                meal_desc = \'""" + str(meal_desc) + """\',
                                                meal_hint = \'""" + str(meal_hint) + """\',
                                                meal_photo_URL = \'""" + str(meal_photo_URL) + """\',
                                                # extra_meal_price = \'""" + str(extra_meal_price) + """\',
                                                meal_calories = \'""" + str(meal_calories) + """\',
                                                meal_protein = \'""" + str(meal_protein) + """\',
                                                meal_carbs = \'""" + str(meal_carbs) + """\',
                                                meal_fiber = \'""" + str(meal_fiber) + """\',
                                                meal_sugar = \'""" + str(meal_sugar) + """\',
                                                meal_fat = \'""" + str(meal_fat) + """\',
                                                meal_sat  = \'""" + str(meal_sat) + """\'
                                                where
                                                meal_id = \'""" + str(mealId) + """\';""", 'post', conn)                                            
            print("meal_updated...")
            
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn) 












class MealCreation(Resource):
    def listIngredients(self, result):
        response = {}
        print("1")
        for meal in result:
            key = meal['meal_id']
            if key not in response:
                response[key] = {}
                response[key]['meal_name'] = meal['meal_name']
                response[key]['ingredients'] = []
            ingredient = {}
            ingredient['name'] = meal['ingredient_desc']
            ingredient['qty'] = meal['recipe_ingredient_qty']
            ingredient['units'] = meal['recipe_unit']
            ingredient['ingredient_id'] = meal['ingredient_id']
            ingredient['measure_id'] = meal['recipe_measure_id']
            response[key]['ingredients'].append(ingredient)

        return response
        print("2")
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            query = """SELECT
                            m.meal_id,
                            m.meal_name,
                            ingredient_id,
                            ingredient_desc,
                            recipe_ingredient_qty,
                            recipe_unit,
                            recipe_measure_id
                            FROM
                            meals m
                            left JOIN
                            recipes r
                            ON
                            recipe_meal_id = meal_id
                            left JOIN
                            ingredients
                            ON
                            ingredient_id = recipe_ingredient_id
                            left join
                            conversion_units
                            ON                    
                            recipe_measure_id = measure_unit_uid
                            order by recipe_meal_id;"""

            sql = execute(query, 'get', conn)

            items = self.listIngredients(sql['result'])

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)

    def post(self):
        # response = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            # Post JSON needs to be in this format
                    #   data = {
                    #       'meal_id': '700-000001',
                    #       'ingredient_id': '110-000002',
                    #       'ingredient_qty': 3,
                    #       'measure_id': '130-000004'
                    #   }
            #print("1")

            # get_user_id_query = "CALL new_customer_uid();"
            # print(get_user_id_query)
            # NewUserIDresponse = execute(get_user_id_query, 'get', conn)
            # print(NewUserIDresponse)
            get_recipe_query = "CALL new_recipe_uid();"
            #print("2")
            #print(get_recipe_query)
            recipe_uid = execute(get_recipe_query, 'get', conn)
            #print(recipe_uid)
            NewRecipeID = recipe_uid['result'][0]['new_id']
            #print(NewRecipeID)

            #print("5")
            query = """
                INSERT INTO recipes 
                SET
                    recipe_uid = \'""" + NewRecipeID + """\',
                    recipe_meal_id = \'""" + data['meal_id'] + """\',
                    recipe_ingredient_id = \'""" + data['ingredient_id'] + """\',
                    recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
                    recipe_measure_id = \'""" + data['measure_id'] + """\'

                ON DUPLICATE KEY UPDATE
                    recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
                    recipe_measure_id = \'""" + data['measure_id'] + "\';"
            #print("6")
            #print(data)
            #original code
            # query = """
            #     INSERT INTO recipes (
            #         recipe_meal_id,
            #         recipe_ingredient_id,
            #         recipe_ingredient_qty,
            #         recipe_measure_id )
            #     VALUES (
            #         \'""" + data['meal_id'] + """\',
            #         \'""" + data['ingredient_id'] + """\',
            #         \'""" + data['ingredient_qty'] + """\',
            #         \'""" + data['measure_id'] + """\')
            #     ON DUPLICATE KEY UPDATE
            #         recipe_ingredient_qty = \'""" + data['ingredient_qty'] + """\',
            #         recipe_measure_id = \'""" + data['measure_id'] + "\';"
            #print("7")
            response = simple_post_execute([query], [__class__.__name__], conn)
            #print("8")
            #items = self.listIngredients(sql['result'])
            #print(items)
            response = 'Request successful.'
            #print("9")
            
            #response['result'] = items
            #print("10")
            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)










class Edit_Recipe(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            meal_id = data['meal_id']
            meal_name = data['meal_name']
            ingredients = data['ingredients']

            items['delete_ingredients'] = execute("""delete from recipes
                                                        where recipe_meal_id = \'""" + str(meal_id) + """\';
                                                            """, 'post', conn)

            i = 0
            for eachIngredient in data['ingredients']:
                name = ingredients[i]['name']
                qty = ingredients[i]['qty']
                units = ingredients[i]['units']
                ingredient_id = ingredients[i]['ingredient_id']
                measure_id = ingredients[i]['measure_id']
                print(name)
                print(qty)
                print(units)
                print(ingredient_id)
                print(measure_id)
                print(meal_id)
                print(meal_name)
                print("************************")

                items['new_ingredients_insert'] = execute(""" INSERT INTO recipes (
                                                            recipe_meal_id, recipe_ingredient_id, recipe_ingredient_qty, 
                                                            recipe_measure_id
                                                            ) 
                                                            VALUES (
                                                            \'""" + str(meal_id) + """\',\'""" + str(ingredient_id) + """\',\'""" + str(qty) + """\',\'""" + str(measure_id) + """\'
                                                            );
                                                            """, 'post', conn)
                i += 1

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)










class Add_New_Ingredient(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            data = request.get_json(force=True)

            ingredient_desc = data['ingredient_desc']
            package_size = data['package_size']
            ingredient_measure_id = data['ingredient_measure_id']
            ingredient_cost = data['ingredient_cost']

            ingredientIdQuery = execute(
                """CALL get_new_ingredient_id();""", 'get', conn)
            ingredientId = ingredientIdQuery['result'][0]['new_id']
            items['new_ingredient_insert'] = execute(""" INSERT INTO ingredients (
                                                                ingredient_id, ingredient_desc, package_size,ingredient_measure_id,ingredient_cost, ingredient_measure
                                                                ) 
                                                                SELECT \'""" + str(ingredientId) + """\', \'""" + str(ingredient_desc) + """\',
                                                                \'""" + str(package_size) + """\',\'""" + str(ingredient_measure_id) + """\',
                                                                \'""" + str(ingredient_cost) + """\', mu.recipe_unit 
                                                                FROM ptyd_conversion_units mu
                                                                WHERE measure_unit_id=\'""" + str(ingredient_measure_id) + """\';
                                                                """, 'post', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)
    def get(self):
        response = {}
        items = {}
        try:
            conn = connect()

            items = execute(""" SELECT
                                *
                                FROM
                                ptyd_ingredients;""", 'get', conn)

            response['message'] = 'Request successful.'
            response['result'] = items

            return response, 200
        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)











class Add_Meal_plan(Resource):
    def post(self):
        response = {}
        items = {}
        try:
            conn = connect()
            print("connection done...")
            data = request.get_json(force=True)
            print("data collected...")
            print(data)
            meal_planIdQuery = execute("""CALL get_new_meal_plan_id();""", 'get', conn)
            print("meal_Plan_id called..")
            mealPlanId = meal_planIdQuery['result'][0]['new_id']
            print("new_meal_plan_id created...")

            meal_plan_desc = data['meal_plan_desc']
            payment_frequency = data['payment_frequency']
            photo_URL = data['photo_URL']
            plan_headline = data['plan_headline']
            plan_footer = data['plan_footer']
            num_meals = data['num_meals']
            meal_weekly_price = data['meal_weekly_price']
            meal_plan_price = data['meal_plan_price']
            meal_shipping = data['meal_shipping']

            print("Items read...")
            items['new_meal_insert'] = execute("""INSERT INTO subscription_items  ( 	
                                                    item_uid,item_desc,payment_frequency,item_photo,info_headline,
                                                    info_footer,num_items,info_weekly_price,item_price,shipping 
                                                    ) 
                                                    VALUES ( 	
                                                    \'""" + str(mealPlanId) + """\',\'""" + str(meal_plan_desc) + """\',
                                                    \'""" + str(payment_frequency) + """\',\'""" + str(photo_URL) + """\',
                                                    \'""" + str(plan_headline) + """\',\'""" + str(plan_footer) + """\',
                                                    \'""" + str(num_meals) + """\',\'""" + str(meal_weekly_price) + """\',
                                                    \'""" + str(meal_plan_price) + """\',\'""" + str(meal_shipping) + """\'
                                                    );""", 'post', conn)

            print("meal_plan_inserted...")

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)






class Profile(Resource):
    # Fetches ALL DETAILS FOR A SPECIFIC USER

    def get(self, id):
    #def get(self):
        response = {}
        items = {}
        #customer_uid = request.args['customer_uid']
        print("user_id: ", id)
        try:
            conn = connect()
            query = """
                    SELECT *
                    FROM sf.customers c
                    WHERE customer_uid = \'""" + id + """\'
                    """
            items = execute(query, 'get', conn)
            if items['result']:

                items['message'] = 'Profile Loaded successful'
                items['result'] = items['result']
                items['code'] = 200
                return items
            else:
                items['message'] = "Customer UID doesn't exists"
                items['result'] = items['result']
                items['code'] = 404
                return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)





class UpdateProfile(Resource):
    def post(self):
            response = {}
            item = {}
            try:
                conn = connect()
                data = request.get_json(force=True)

                #query = "CALL sf.new_profile"
                #new_profile_query = execute(query, 'get', conn)
                #new_profile = newPaymentUID_query['result'][0]['new_id']

                uid= data['uid']
                f_name= data['first_name']
                l_name= data['last_name']
                phone= data['phone']
                email= data['email']
                address= data['address']
                unit= data['unit']
                city= data['city']
                state= data['state']
                zip_code= data['zip']
                notification= data['noti']
                print(data)

                customer_insert_query = [""" 
                                    UPDATE sf.customers
                                    SET
                                    customer_first_name = \'""" + f_name + """\',
                                    customer_last_name = \'""" + l_name + """\',
                                    customer_phone_num = \'""" + phone + """\',
                                    customer_email = \'""" + email + """\',
                                    customer_address = \'""" + address + """\',
                                    customer_unit = \'""" + unit + """\',
                                    customer_city = \'""" + city + """\',
                                    customer_state = \'""" + state + """\',
                                    customer_zip = \'""" + zip_code + """\',
                                    notification_approval = \'""" + notification + """\'
                                    WHERE customer_uid =\'""" + uid + """\';
                                    
                                """]


                print(customer_insert_query)
                item = execute(customer_insert_query[0], 'post', conn)
                if item['code'] == 281:
                    item['code'] = 200
                    item['message'] = 'Profile info updated'
                else:
                    item['message'] = 'check sql query'
                    item['code'] = 490

                return item

            except:
                print("Error happened while inserting in customer table")
                raise BadRequest('Request failed, please try again later.')
            finally:
                disconnect(conn)
                print('process completed')






class access_refresh_update(Resource):

    def post(self):

        try:
            conn = connect()
            data = request.get_json(force=True)
            query = """
                    UPDATE sf.customers SET 
                    user_access_token = \'""" + data['access_token'] + """\', 
                    user_refresh_token = \'""" + data['refresh_token'] + """\', 
                    social_timestamp =  \'""" + data['social_timestamp'] + """\' 
                    WHERE (customer_uid = \'""" + data['uid'] + """\'); ;
                    """
            print(query)
            items = execute(query, 'post', conn)
            if items['code'] == 281:
                items['message'] = 'Access and refresh token updated successfully'
                print(items['code'])
                items['code'] = 200
            else:
                items['message'] = 'Check sql query'
                items['code'] = 400


            return items

        except:
            raise BadRequest('Request failed, please try again later.')
        finally:
            disconnect(conn)






# Define API routes
# Customer APIs


#--------------------- Signup/ Login page / Change Password ---------------------#
api.add_resource(SignUp, '/api/v2/signup')
#  * The "signup" endpoint accepts only POST request with appropriate named      #
#  parameters. Please check the documentation for the right format of those named#
#  parameters.                                                                   #
api.add_resource(Login, '/api/v2/login')
#  * The "Login" endpoint accepts only POST request with at least 2 parameters   #
# in its body. The first param is "email" and the second one is either "password"#
# or "refresh_token". We are gonna re-use the token we got from facebook or      #
# google for our site and we'll pick the refresh token because it will not       #
# expire.                                                                        #
api.add_resource(AppleLogin, '/api/v2/apple_login', '/')
api.add_resource(Change_Password, '/api/v2/change_password')

api.add_resource(Reset_Password, '/api/v2/reset_password')
#--------------------------------------------------------------------------------#

#---------------------------- Select Meal plan pages ----------------------------#
# We can use the Plans endpoint (in the Admin endpoints section below) to get    #
# needed info.
#--------------------------------------------------------------------------------#

#------------- Checkout, Meal Selection and Meals Schedule pages ----------------#
api.add_resource(Meals_Selected, '/api/v2/meals_selected')
#  * The "Meals_Selected" only accepts GET request with one required parameters  #
# "customer_id".It will return the information of all selected meals and addons  #
# which are associated with the specific purchase. Modified to show specific     #
# means for specific date                                                        #
api.add_resource(Get_Upcoming_Menu, '/api/v2/upcoming_menu' )
#  * The "Get_Upcoming_Menu" only accepts GET request without required param.    #
# It will return the information of all upcoming menu items.                     #
api.add_resource(Get_Latest_Purchases_Payments, '/api/v2/customer_lplp')
#  * The "Get_Latest_Purchases_Payments" only accepts GET request with 1 required#
#  parameters ("customer_uid"). It will return the information of all current    #
#  purchases of the customer associated with the given customer_uid.
api.add_resource(Next_Billing_Date, '/api/v2/next_billing_date')
#  * The "next_Billing_Date" only accepts GET request with parameter named       #
#  "customer_uid". It will return the next billing charge information.           #
api.add_resource(Next_Addon_Charge, '/api/v2/next_addon_charge')
#  * The "next_addon_charge" only accepts GET request with required parameter    #
# named "purchase_uid". It will return the next addon charge information.        #
api.add_resource(AccountSalt, '/api/v2/accountsalt')
#  * The "accountsalt" endpoint accepts only GET request with one required param. #
#  It will return the information of password hashed and password salt for an     #
# associated email account.
api.add_resource(Checkout, '/api/v2/checkout')
#  * The "checkout" accepts POST request with appropriate parameters. Please read#
# the documentation for these parameters and its formats.                        #
##################################################################################
api.add_resource(Meals_Selection, '/api/v2/meals_selection')
#  * The "Meals_Selection" accepts POST request with appropriate parameters      #
#  Please read the documentation for these parameters and its formats.           #
#--------------------------------------------------------------------------------#

api.add_resource(Change_Purchase, '/api/v2/change_purchase')
#


#********************************************************************************#
#*******************************  ADMIN APIs  ***********************************#
#---------------------------------   Subscriptions   ----------------------------#
api.add_resource(Plans, '/api/v2/plans')
#  * The "plans" endpoint accepts only get request with one required parameter.  #
#  It will return all the meal plans in the SUBSCRIPTION_ITEM table. The returned#
#  info contains all meal plans (which is grouped by item's name) and its        #
#  associated details.                                                           #
#--------------------------------------------------------------------------------#

#---------------------------- Create / Edit Menu pages ---------------------------#
api.add_resource(Menu, '/api/v2/menu')
#  * The "Menu" endpoint accepts GET, POST, and DELETE request. For GET request,  #
#  this endpoint does not need any parameters and returns all the menu's info.    #
#  For the POST request, we need the appropriate JSON format for request.         #
#  The DELETE request needs the "menu_uid" as the parameter in order to delete    #
# that associated record in the database.
api.add_resource(Meals, '/api/v2/meals')
#  * The "Meals" endpoint accepts GET, POST, and PUT request. For GET request,    #
#  this endpoint does not need any parameters and returns all the meals's info.   #
#  For the POST and PUT request, we need the appropriate JSON format for the      #
#  the request.                                                                   #
# NOTICE: Do we need the DELETE request for this endpoint?
#---------------------------------------------------------------------------------#

api.add_resource(Recipes, '/api/v2/recipes')
#  * The get_recipes endpoint accepts only get request and return all associate   #
#   info. This endpoint requires one parameter named "meal_uid".                  #
api.add_resource(Ingredients, '/api/v2/ingredients')
#  * The "Ingredients" endpoint accepts GET, POST, and PUT request. For GET       #
#  request, this endpoint does not need any parameters and returns all the meals's#
#  info. For the POST and PUT request, we need the appropriate JSON format for the#
#  the request.                                                                   #
# NOTICE: Do we need the DELETE request for this endpoint?                        #
api.add_resource(Measure_Unit, '/api/v2/measure_unit')
#  * The "Measure_Unit" endpoint accepts GET, POST, and PUT request. For GET
#  request, this endpoint does not need any parameters and returns all the        #
#  measure unit's info. For the POST and PUT request, we need the appropriate JSON#
#  format for the the request.                                                    #
# NOTICE: Do we need the DELETE request for this endpoint?                        #
#-------------------------------- Plan / Coupon pages ----------------------------#
#  * The user can access /api/v2/plans endpoint to get all Plans.                 #
#  * The "Coupons" endpoint accepts GET, POST, PUT and DELETE requestS. The GET   #
#  request does not require any parameter. POST, and PUT request require an       #
# appropriate JSON objects and the DELETE request requires "coupon_uid" as the    #
# required parameter.                                                             #
api.add_resource(Coupons, '/api/v2/coupons')
#---------------------------------------------------------------------------------#
#  * The Get_Orders_By_Purchase_id endpoint accepts only GET request without any  #
#  parameters.                                                                    #
api.add_resource(Ordered_By_Date, '/api/v2/ordered_by_date')
#  * The "Ingredients_Need accepts only get request and return all associate info.#
#  This endpoint does not require any parameter.                                  #
api.add_resource(Ingredients_Need, '/api/v2/ingredients_need')

#**********************************************************************************#

api.add_resource(Edit_Menu, '/api/v2/Edit_Menu')

api.add_resource(Edit_Meal, '/api/v2/Edit_Meal')

api.add_resource(MealCreation, '/api/v2/mealcreation')

api.add_resource(Edit_Recipe, '/api/v2/Edit_Recipe')

api.add_resource(Add_New_Ingredient, '/api/v2/Add_New_Ingredient')

api.add_resource(Profile, '/api/v2/Profile/<string:id>')

api.add_resource(Meals_Selected_Specific, '/api/v2/meals_selected_specific')

api.add_resource(UpdateProfile, '/api/v2/UpdateProfile')

api.add_resource(access_refresh_update, '/api/v2/access_refresh_update')

# Run on below IP address and port
# Make sure port number is unused (i.e. don't use numbers 0-1023)
# lambda function at: https://ht56vci4v9.execute-api.us-west-1.amazonaws.com/dev
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=2000)
    #app.run(host='0.0.0.0', port=2000)
