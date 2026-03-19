import re
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage

from app_helpers import assign_device_to_shelf
from api_client import call_api
import yaml
import asyncio

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

LOCATION_BY_ASSIGNMENT_GROUP = {
    "PAB TechStop Support": "PAB",
    "SSW Mobile TechStop": "SSW",
    "EVS Mobile TechStop": "EVS",
    "WVS Mobile TechStop": "WVS",
    "TSC Mobile TechStop": "TSC",
    "XCT Mobile TechStop": "XCT",
}
TRUE_SLOTTING_LOCATIONS = {"PAB"}

def slot_new_device(task: dict):
    """
    Wrapper function for auto-assign mode (backward compatibility).
    Uses assign_device_to_shelf with override_mode=False to let shelf choose slot.
    """
    return asyncio.run(assign_device_to_shelf(task, override_mode=False))

def normalize_optional_email(value: str = None):
    """Normalize optional email strings from URL/JS placeholders."""
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.lower() in {"none", "null", "undefined"}:
        return None
    if "@" not in normalized:
        return None
    return normalized

def normalize_assignment_group(value):
    if isinstance(value, dict):
        return str(value.get("display_value") or value.get("value") or "").strip()
    return str(value or "").strip()

def get_pickup_location(assignment_group):
    group_name = normalize_assignment_group(assignment_group)
    return LOCATION_BY_ASSIGNMENT_GROUP.get(group_name, "PAB")

def is_true_slotting_group(assignment_group):
    return get_pickup_location(assignment_group) in TRUE_SLOTTING_LOCATIONS

def email(
    Machine: str = "Undefined",
    RITM: str = "RITM0000000",
    Name: str = None,
    userEmail: str = None,
    pickup_location: str = "PAB",
):

    spec = {
        "url": "http://configurationitem/table/user?SystemID=SOAP-UI&ReferenceID=*&MaxRows=100",
        "headers": {
            "accept": "application/json",
            "QueryParams": f"sysparm_query=name={Name}"
        },
        "method": "GET"
    }

    response = asyncio.run(call_api(spec["url"], headers=spec["headers"], method=spec["method"]))
    userFound = response["result"]
    sendTo = ""

    if len(userFound) > 1:
        sendTo = []
        for user in userFound:
            sendTo.append(user["email"])
    else:
        sendTo = userFound[0]["email"]

    today = datetime.now()
    twoWeeks = today + timedelta(weeks=2)
    formattedTodayDate = today.strftime("%A, %B, %d, %Y")
    formattedTwoWeeksDate = twoWeeks.strftime("%A, %B, %d, %Y")
    email = EmailMessage()
    email["Subject"] = f"Your New {Machine} is Ready for Pickup: {RITM}"
    email["From"] = "PABTechStop@srpnet.com"
    email["To"] = sendTo
    normalized_bcc = normalize_optional_email(userEmail)
    if normalized_bcc:
        email["Bcc"] = normalized_bcc

    
    with open("email_template.html", "r") as file:
        html_template = file.read()

    
    machine_lower = str(Machine).lower()
    is_phone_device = ("phone" in machine_lower) or ("iphone" in machine_lower)
    phone_setup_note = (
        "Please note: iPhone setup can take up to one hour or more. "
        "If you are transferring data to a new phone, the process may take longer."
        if is_phone_device
        else ""
    )

    html_content = html_template.replace("{{ machine }}", Machine) \
                            .replace("{{ formatted_today_date }}", formattedTodayDate) \
                            .replace("{{ formatted_two_weeks_date }}", formattedTwoWeeksDate) \
                            .replace("{{ ritm }}", RITM) \
                            .replace("{{ phone_setup_note }}", phone_setup_note) \
                            .replace("{{ pickup_location }}", pickup_location)

    
    email.set_content(html_content, subtype="html")
    
    server = smtplib.SMTP("mail.srp.gov", 25)
    server.send_message(email)
    server.quit()

def update_snow_ticket(sysID: str = None, shortDescription: str = None):
    spec = {
        "url": "http://ConfigurationItem/table/task?SystemID=SystemID&ReferenceID=ReferenceID",
        "params": {
            "TaskID": sysID,
            "ShortDescription": shortDescription,
            "State": "On Hold",
            "WorkNotes": "Notified Customer via Email that the device is ready and available for pick up."
        },
        "headers": {
            "accept": "application/json",
        },
        "method": "PUT"
    }
    asyncio.run(call_api(spec["url"], params=spec["params"], headers=spec["headers"], method=spec["method"]))

def slot_new_device_task(task: str = None, userEmail : str = None):
    if task is None:
        return
    userEmail = normalize_optional_email(userEmail)
    
    spec = {
        "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000",
        "headers": {
            "accept": "application/json",
            "QueryParams": f"sysparm_query=active=true&sys_class_name=Catalog Task&number={task}"
        },
        "method": "GET"
    }
    
    response = asyncio.run(call_api(spec["url"], headers=spec["headers"], method=spec["method"]))
    task_found = response["result"][0]
    assignment_group = task_found.get("assignment_group")
    pickup_location = get_pickup_location(assignment_group)
    machine_name = task_found.get("cmdb_ci") or "Device"
    if isinstance(machine_name, dict):
        machine_name = machine_name.get("display_value") or machine_name.get("value") or "Device"
    
    today = datetime.now()
    twoWeeks = today + timedelta(weeks=2)
    formattedTwoWeeksDate = twoWeeks.strftime("%m/%d")

    if not is_true_slotting_group(assignment_group):
        email(machine_name, task_found["parent"], task_found["requested_for"], userEmail, pickup_location=pickup_location)
        short_description = f"UCD: {formattedTwoWeeksDate} {task_found['short_description']}"
        update_snow_ticket(task_found["sys_id"], short_description)
        return task_found["requested_for"], task_found["cmdb_ci"], -1, formattedTwoWeeksDate

    shelf, slot_number, overflow = slot_new_device(task_found)

    if shelf is not False:
        machine_name = shelf.device_name
        email(machine_name, task_found["parent"], task_found["requested_for"], userEmail, pickup_location=pickup_location)
        if slot_number != -1: # Slot -1 does not exist so if that is returned, then we know not to slot the device
            short_description = f"Slot: {slot_number}, UCD: {formattedTwoWeeksDate} {task_found['short_description']}"
        else:
            short_description = f"UCD: {formattedTwoWeeksDate} {task_found['short_description']}"
        update_snow_ticket(task_found["sys_id"], short_description) #slot device in SNOW

        if overflow:
            return task_found["requested_for"], task_found["cmdb_ci"], str(slot_number) + f", Overflow! Using Slot {slot_number} as overflow slot, please clear any other slots or close unclosed tickets", formattedTwoWeeksDate
        return task_found["requested_for"], task_found["cmdb_ci"], slot_number, formattedTwoWeeksDate
    else:
        return task_found["requested_for"], task_found["cmdb_ci"], slot_number, None # slotNumber is used as the error message!

#slot_new_device_task("TASK1150614", "anthony.rivera@srpnet.com")
