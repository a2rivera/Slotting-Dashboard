import sys
import os
import time

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
from shelves_helper import shelves
with open("config.json", "r") as f:
    config = json.load(f)

ldap_server = config["ldap"]["server"]
ldap_user = config["ldap"]["username"]
ldap_pass = config["ldap"]["password"]
search_base = config["ldap"]["search_base"]

globalResponse = None
last_refresh_ts = 0.0
MIN_REFRESH_SECONDS = 30  # throttle manual refreshes to at most once every 30 seconds

#app = Flask(__name__, static_url_path='/static', static_folder="E:\\website\\WWWRoot\\App\\static")
app = Flask(__name__)
app.secret_key = os.urandom(24)

socketio = SocketIO(app, cors_allowed_origins="*")

def setResponse():
    global globalResponse
    tickets = get_tickets()
    formatted_response = {
        "result": tickets
    }

    for item in formatted_response["result"]:
        slot, ucd = extract_ucd_slot(item.get('short_description', ''))
        item["slot"] = slot
        item["ucd"] = ucd
    globalResponse = formatted_response
    
    # Build set of active ticket numbers
    active_ticket_numbers = {str(ticket["number"]) for ticket in tickets}
    
    # Remove devices from closed tickets on all shelves
    print("Cleaning up devices from closed tickets...")
    total_removed = 0
    for shelf in shelves.values():
        removed = shelf.removeDevicesFromClosedTickets(active_ticket_numbers)
        total_removed += removed
    if total_removed > 0:
        print(f"Total devices removed from closed tickets: {total_removed}")
    
    process_slot_tickets()

@app.route("/")
def pickUpHome():
    return redirect(url_for("slotDashboard"))

@app.route("/get-data")
def getData():
    if globalResponse == None:
        setResponse()
    return jsonify(globalResponse)


@app.route("/refresh-data")
def refreshData():
    """Force a fresh pull from ServiceNow by calling setResponse, then return latest data.

    This endpoint is throttled so it can't be spammed and hammer ServiceNow.
    """
    global last_refresh_ts

    now = time.time()
    # If we've refreshed too recently, just return the existing cached data
    if last_refresh_ts and (now - last_refresh_ts) < MIN_REFRESH_SECONDS:
        remaining = int(MIN_REFRESH_SECONDS - (now - last_refresh_ts))
        payload = globalResponse or {"result": []}
        return jsonify(
            {
                "result": payload.get("result", []),
                "throttled": True,
                "next_allowed_in": max(remaining, 0),
            }
        )

    setResponse()
    last_refresh_ts = now
    payload = globalResponse or {"result": []}
    return jsonify(
        {
            "result": payload.get("result", []),
            "throttled": False,
            "next_allowed_in": MIN_REFRESH_SECONDS,
        }
    )

@app.route("/slotting-dashboard")
def slotDashboard():
    handle_str = request.headers['x-iis-windowsauthtoken']
    handle = int(handle_str, 16)
    win32security.ImpersonateLoggedOnUser(handle)
    username = win32api.GetUserName()
    win32api.CloseHandle(handle)

    # Use the gMSA identity running the IIS application (no explicit credentials)
    conn = ldap3.Connection(ldap_server, auto_bind=True)
    
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
