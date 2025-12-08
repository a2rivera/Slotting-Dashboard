import re
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage

from shelves_helper import get_shelf
from api_client import call_api
from app_helpers import find_key_words
import yaml
import asyncio

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

def slot_new_device(task: dict):
    short_description = re.sub(r"[^\w\s]+", "", str(task["short_description"]).lower())
    display_name = task["cmdb_ci"]
    
    if "slot" in short_description:
        return False, "Cannot slot Device! Task is already slotted. Please double check and confirm if the device is slotted and if the Task is correct. (To 'unslot' the device remove 'Slot' from the Short Description and the system will re-slot it)", False
    
    key_words_found, key_words_found_str = find_key_words(task)
    computer_found = []
    
    if not key_words_found:
        return False, "Cannot slot Device! The task does not contain key words specified. If this is a task that should be slotted please edit the configuration file to include key words in the short description.", False
    
    if display_name == "" and (not key_words_found):
        return False, "Cannot slot Device! There is no Configuration item listed! Please correct the task and add the CI in the field.", False
    elif display_name == "" and key_words_found: # The new workflow WST made for some reason there is no cmdb_ci on it in the rest call
        display_name = f"placeholder_device_{task["number"]}" # we make a placeholder for computerfound because no cmdb found, to then be able to slot the device
        computer_found = [
            {
                "asset": key_words_found_str,
                "sys_class_name": "none"
            }
        ]
    elif display_name != "" and key_words_found:
        spec = {
            "url": f"http://configurationitem/table/computer?SystemID=SOAP-UI&ReferenceID=*&MaxRows=100&KeyName=u_display_name&KeyValue={task["cmdb_ci"]}",
            "headers": {
                "accept": "application/json"
            },
            "method": "GET"
        }
        response = asyncio.run(call_api(spec["url"], headers=spec["headers"], method=spec["method"]))
        computer_found = response["result"]
    
    if len(computer_found) == 0:
        return False, "Cannot slot Device! Cannot determine what type of device this is, needs to be defined in the the config file via key words", False
    
    shelf, slot_number = get_shelf(computer_found)
    if shelf == None:
        return False, "Could not find shelf for device", False
    slot_number = shelf.assignDevice(display_name)
    if slot_number == None:
        display_name = f"placeholder_overfill_{task["number"]}" # we make a placeholder for computerfound for desktop, this is used as overflow
        computer_found_temp = [ # use temp to send correct device and not overwrite
            {
                "asset": "mini desktop",
                "sys_class_name": "none"
            }
        ]
        overfill_shelf, slot_number = get_shelf(computer_found_temp) # So that shelf doesn"t become tuple
        slot_number = overfill_shelf.assignDeviceWithSlot(display_name, 0) # this is 0 because there is only 1 slot for desktops (slot #72)
        return overfill_shelf, overfill_shelf.slot_start, True # return overflow so the correct message is displayed when slotted
    return shelf, (slot_number + shelf.slot_start), False

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
            return task_found["requested_for"], task_found["cmdb_ci"], str(slot_number) + ", Overflow! Using Slot 72 as overflow slot, please clear any other slots or close unclosed tickets", formattedTwoWeeksDate
        return task_found["requested_for"], task_found["cmdb_ci"], slot_number, formattedTwoWeeksDate
    else:
        return task_found["requested_for"], task_found["cmdb_ci"], slot_number, None # slotNumber is used as the error message!

#slot_new_device_task("TASK1150614", "anthony.rivera@srpnet.com")
