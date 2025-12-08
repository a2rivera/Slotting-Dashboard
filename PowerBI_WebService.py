import sys
import os

from pathlib import Path


import win32api
import win32security
import ldap3
import json

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler

from app_helpers import extract_ucd_slot
from techstop_shelf_assignment import process_slot_tickets, get_tickets
from techstop_notify_automation import slot_new_device_task
with open("config.json", "r") as f:
    config = json.load(f)

ldap_server = config["ldap"]["server"]
ldap_user = config["ldap"]["username"]
ldap_pass = config["ldap"]["password"]
search_base = config["ldap"]["search_base"]

globalResponse = None

#app = Flask(__name__, static_url_path='/static', static_folder="E:\\website\\WWWRoot\\App\\static")
app = Flask(__name__)
app.secret_key = os.urandom(24)

socketio = SocketIO(app, cors_allowed_origins="*")

def setResponse():
    global globalResponse
    formatted_response = {
        "result": get_tickets()
    }

    for item in formatted_response["result"]:
        slot, ucd = extract_ucd_slot(item.get('short_description', ''))
        item["slot"] = slot
        item["ucd"] = ucd
    globalResponse = formatted_response
    
    process_slot_tickets()

@app.route("/")
def pickUpHome():
    return redirect(url_for("slotDashboard"))

@app.route("/get-data")
def getData():
    if globalResponse == None:
        setResponse()
    return jsonify(globalResponse)

@app.route("/slotting-dashboard")
def slotDashboard():
    handle_str = request.headers['x-iis-windowsauthtoken']
    handle = int(handle_str, 16)
    win32security.ImpersonateLoggedOnUser(handle)
    username = win32api.GetUserName()
    win32api.CloseHandle(handle)

    conn = ldap3.Connection(ldap_server, user=ldap_user, password=ldap_pass, auto_bind=True)
    
    search_filter = f'(sAMAccountName={username})'
    conn.search(search_base, search_filter, attributes=['mail', 'userPrincipalName'])

    if conn.entries:
        entry = conn.entries[0]
        email = entry.mail.value or entry.userPrincipalName.value
    else:
        email = None

    data = {
        "email":  email,
        "rows": globalResponse
    }

    return render_template("home.html", data=data)

@app.route("/<taskNumber>/<userEmail>")
def automatePickUp(taskNumber, userEmail):
    try:
        requestedFor, CI, slotNumber, UCD = slot_new_device_task(str(taskNumber), userEmail)
        print(requestedFor)
        print(CI)
        print(slotNumber)
        print(UCD)
        #return f"Customer: {requestedFor}<br>Device Name: {CI}<br>Slot: {slotNumber}<br>UCD: {UCD}"
        for item in globalResponse["result"]:
            if item["number"] == taskNumber:
                item["slot"] = slotNumber
                item["ucd"] = UCD

        return jsonify({
            "requestedFor": requestedFor,
            "CI": CI,
            "slotNumber": slotNumber,
            "UCD": UCD
        })
    except Exception as e:
        return jsonify({
            "requestedFor": e,
            "CI": None,
            "slotNumber": None,
            "UCD": None
        })
    
scheduler = BackgroundScheduler()
scheduler.add_job(setResponse, 'interval', minutes=5)
scheduler.start()
setResponse()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5001))
    app.run(host='localhost', port=port)

    #socketio.run(app, debug=True)
