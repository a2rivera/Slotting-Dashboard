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

def get_phone_setup_instructions(is_phone_device: bool, pickup_location: str = "PAB"):
    if not is_phone_device:
        return ""

    appointment_instruction = ""
    if pickup_location == "PAB":
        appointment_instruction = """
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Schedule a <a href="https://srpnet.service-now.com/sp?id=walkup_online_checkin&amp;location_id=4ff57115db28701088dd266e139619d4">TechStop appointment</a> if possible.</span></li>
        """

    return """
        <p style='margin:0in;line-height:115%'><b><span style='font-size:10.0pt;
        line-height:115%;font-family:"Arial",sans-serif;color:black'>What to expect with your new phone:</span></b></p>
        <ul style='margin-top:0in;margin-bottom:0in'>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>SRP is introducing a new sign-in experience for corporate phones using Apple Managed IDs.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Be on the lookout for an email from &quot;no-reply@apple.com&quot; with your new Managed Apple ID.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>You will sign in to your Apple Account with your SRP email address.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Applications will be installed from Company Portal.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Personal Apple services like Find My, Apple Pay, and subscription services will be restricted.</span></li>
        </ul>
        <p style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
        line-height:115%;font-family:"Arial",sans-serif;color:black'><o:p>&nbsp;</o:p></span></p>
        <p style='margin:0in;line-height:115%'><b><span style='font-size:10.0pt;
        line-height:115%;font-family:"Arial",sans-serif;color:black'>Before your phone pickup:</span></b></p>
        <p style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
        line-height:115%;font-family:"Arial",sans-serif;color:black'>These steps are recommended to make your TechStop visit faster. If you are unable to complete them, TechStop will still assist you.</span></p>
        <ul style='margin-top:0in;margin-bottom:0in'>
        """ + appointment_instruction + """
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Plan to be at TechStop for up to one hour. To reduce your time at TechStop, complete the activities below before your visit.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Back up your current phone to iCloud before your visit. See <a href="https://srpnet.service-now.com/kb_view.do?sysparm_article=KB0024480">KB0024480</a>.</span>
          <ul style='margin-top:0in;margin-bottom:0in'>
           <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
           line-height:115%;font-family:"Arial",sans-serif;color:black'>If you need more backup space or the iCloud backup fails, use iTunes or Finder on a computer. See <a href="https://srpnet.service-now.com/kb_view.do?sysparm_article=KB0024533">KB0024533</a>.</span></li>
          </ul>
         </li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Make sure you know your Apple ID password. If needed, reset it before your visit using <a href="https://srpnet.service-now.com/kb_view.do?sysparm_article=KB0024415">KB0024415</a>.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>If you use a personal Apple ID with your SRPNET.COM email address, rename it using <a href="https://srpnet.service-now.com/kb_view.do?sysparm_article=KB0024530">KB0024530</a>.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Remove or move any SRP-related information from your personal Apple ID to OneDrive using <a href="https://srpnet.service-now.com/kb_view.do?sysparm_article=KB0023173">KB0023173</a>.</span></li>
        </ul>
        <p style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
        line-height:115%;font-family:"Arial",sans-serif;color:black'><o:p>&nbsp;</o:p></span></p>
        <p style='margin:0in;line-height:115%'><b><span style='font-size:10.0pt;
        line-height:115%;font-family:"Arial",sans-serif;color:black'>Apps:</span></b></p>
        <ul style='margin-top:0in;margin-bottom:0in'>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>Apps available for your phone will be listed in Company Portal.</span></li>
         <li style='margin:0in;line-height:115%'><span style='font-size:10.0pt;
         line-height:115%;font-family:"Arial",sans-serif;color:black'>If you do not see an app you need in Company Portal, submit an <a href="https://srpnet.service-now.com/sp?id=sc_cat_item&amp;table=sc_cat_item&amp;sys_id=c82ceeaa1b13e050b01654ee034bcbbd&amp;searchTerm=company%20portal%20app">app onboarding request</a>.</span></li>
        </ul>
    """

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
    phone_setup_instructions = get_phone_setup_instructions(is_phone_device, pickup_location)

    html_content = html_template.replace("{{ machine }}", Machine) \
                            .replace("{{ formatted_today_date }}", formattedTodayDate) \
                            .replace("{{ formatted_two_weeks_date }}", formattedTwoWeeksDate) \
                            .replace("{{ ritm }}", RITM) \
                            .replace("{{ phone_setup_instructions }}", phone_setup_instructions) \
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

    # iPads should be notify-only (no slot assignment), even for PAB.
    sd_lower = str(task_found.get("short_description") or "").lower()
    mn_lower = str(machine_name or "").lower()
    if "ipad" in sd_lower or "ipad" in mn_lower:
        today = datetime.now()
        twoWeeks = today + timedelta(weeks=2)
        formattedTwoWeeksDate = twoWeeks.strftime("%m/%d")
        email(machine_name, task_found["parent"], task_found["requested_for"], userEmail, pickup_location=pickup_location)
        short_description = f"UCD: {formattedTwoWeeksDate} {task_found['short_description']}"
        update_snow_ticket(task_found["sys_id"], short_description)
        return task_found["requested_for"], task_found["cmdb_ci"], -1, formattedTwoWeeksDate
    
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
