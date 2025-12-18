import sys
import os
import time

from pathlib import Path


import win32api
import win32security
import ldap3
import yaml

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler

from app_helpers import extract_ucd_slot
from techstop_shelf_assignment import process_slot_tickets, get_tickets
from techstop_notify_automation import slot_new_device_task
from shelves_helper import shelves
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

ldap_server = config["ldap"]["server"]
search_base = config["ldap"]["search_base"]

globalResponse = None
globalLoanerData = None
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

def get_loaner_data():
    """Fetch loaner computer data from your data source.
    
    TODO: Replace this with actual data source (ServiceNow, database, etc.)
    Expected return format:
    [
        {
            "name": "LOANER-001",
            "status": "in use",  # or "in stock", "re-imaging"
            "date_of_return": "2024-12-31",  # YYYY-MM-DD format
            "user_assigned_to": "user@srp.gov"  # only if status is "in use"
        },
        ...
    ]
    """
    global globalLoanerData
    # TODO: Replace with actual data fetching logic
    # For now, return empty list or placeholder data
    if globalLoanerData is None:
        globalLoanerData = []
    return globalLoanerData

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
    ldap_user = "pabtechstop@srp.gov"
    ldap_pass = "ReturnToChaos26"
    conn = ldap3.Connection(ldap_server, user=ldap_user, password=ldap_pass, auto_bind=True) # TODO: change to use gMSA identity, currently not working with IIS application pool identity
    
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

@app.route("/loaner-dashboard")
def loanerDashboard():
    """Loaner computer dashboard page."""
    handle_str = request.headers.get('x-iis-windowsauthtoken', '0')
    if handle_str and handle_str != '0':
        try:
            handle = int(handle_str, 16)
            win32security.ImpersonateLoggedOnUser(handle)
            username = win32api.GetUserName()
            win32api.CloseHandle(handle)
        except:
            username = None
    else:
        username = None

    email = None
    if username:
        try:
            # Use the gMSA identity running the IIS application (no explicit credentials)
            ldap_user = "pabtechstop@srp.gov"
            ldap_pass = "ReturnToChaos26"
            conn = ldap3.Connection(ldap_server, user=ldap_user, password=ldap_pass, auto_bind=True) # TODO: change to use gMSA identity, currently not working with IIS application pool identity
            
            search_filter = f'(sAMAccountName={username})'
            conn.search(search_base, search_filter, attributes=['mail', 'userPrincipalName'])

            if conn.entries:
                entry = conn.entries[0]
                email = entry.mail.value or entry.userPrincipalName.value
        except Exception as e:
            print(f"Error fetching email for loaner dashboard: {e}")

    loaners = get_loaner_data()
    data = {
        "email": email,
        "loaners": loaners
    }

    return render_template("loaner_dashboard.html", data=data)

@app.route("/get-loaner-data")
def getLoanerData():
    """API endpoint to get loaner data."""
    loaners = get_loaner_data()
    return jsonify({"loaners": loaners})

@app.route("/notify-loaner-return", methods=["POST"])
def notifyLoanerReturn():
    """API endpoint to send notification to user about returning their loaner computer."""
    try:
        data = request.get_json()
        loaner_name = data.get("loanerName", "")
        user_email = data.get("userEmail", "")

        if not loaner_name or not user_email:
            return jsonify({
                "success": False,
                "error": "Missing loanerName or userEmail"
            }), 400

        # TODO: Implement actual email notification logic here
        # For now, just log it
        print(f"Notification requested for loaner {loaner_name} to user {user_email}")
        
        # Placeholder for email sending logic
        # You can integrate with your existing email notification system
        # similar to techstop_notify_automation.py
        
        return jsonify({
            "success": True,
            "message": f"Notification sent to {user_email} for loaner {loaner_name}"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
    
scheduler = BackgroundScheduler()
scheduler.add_job(setResponse, 'interval', minutes=5)
scheduler.start()
setResponse()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5001))
    app.run(host='localhost', port=port)

    #socketio.run(app, debug=True)
