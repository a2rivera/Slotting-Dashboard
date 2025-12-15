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

def slot_new_device(task: dict):
    """
    Wrapper function for auto-assign mode (backward compatibility).
    Uses assign_device_to_shelf with override_mode=False to let shelf choose slot.
    """
    return asyncio.run(assign_device_to_shelf(task, override_mode=False))

def email(Machine : str = "Undefined", RITM : str = "RITM0000000", Name : str = None, userEmail : str = None):

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
    email["Bcc"] = userEmail

    
    with open("email_template.html", "r") as file:
        html_template = file.read()

    
    html_content = html_template.replace("{{ machine }}", Machine) \
                            .replace("{{ formatted_today_date }}", formattedTodayDate) \
                            .replace("{{ formatted_two_weeks_date }}", formattedTwoWeeksDate) \
                            .replace("{{ ritm }}", RITM)

    
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
    if userEmail is None:
        return
    
    spec = {
        "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=PAB TechStop Support",
        "headers": {
            "accept": "application/json",
            "QueryParams": f"sysparm_query=active=true&sys_class_name=Catalog Task&number={task}"
        },
        "method": "GET"
    }
    
    response = asyncio.run(call_api(spec["url"], headers=spec["headers"], method=spec["method"]))
    task_found = response["result"][0]
    
    shelf, slot_number, overflow = slot_new_device(task_found)

    if shelf is not False:
        Machine = shelf.device_name
        email(Machine, task_found["parent"], task_found["requested_for"], userEmail)
        today = datetime.now()
        twoWeeks = today + timedelta(weeks=2)
        formattedTwoWeeksDate = twoWeeks.strftime("%m/%d")
        if slot_number != -1: # Slot -1 does not exist so if that is returned, then we know not to slot the device
            short_description = f"Slot: {slot_number}, UCD: {formattedTwoWeeksDate} {task_found["short_description"]}"
        else:
            short_description = f"UCD: {formattedTwoWeeksDate} {task_found["short_description"]}"
        update_snow_ticket(task_found["sys_id"], short_description) #slot device in SNOW
    
        if overflow:
            return task_found["requested_for"], task_found["cmdb_ci"], str(slot_number) + f", Overflow! Using Slot {slot_number} as overflow slot, please clear any other slots or close unclosed tickets", formattedTwoWeeksDate
        return task_found["requested_for"], task_found["cmdb_ci"], slot_number, formattedTwoWeeksDate
    else:
        return task_found["requested_for"], task_found["cmdb_ci"], slot_number, None # slotNumber is used as the error message!

#slot_new_device_task("TASK1150614", "anthony.rivera@srpnet.com")
