import re
import asyncio
from app_helpers import extract_ucd_slot
from shelves_helper import get_shelf
from api_client import run_calls_sync, call_api
import yaml
from app_helpers import find_key_words

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

async def assign_task_slot(task: dict):
    short_description = re.sub(r'[^\w\s]+', '', str(task["short_description"]).lower())
    display_name = task["cmdb_ci"]
    
    if ("slot" not in short_description):
        return False
    if str(task["state"]) == "Cancelled" or str(task["state"]) == "Closed" or str(task["state"]) == "Resolved": # These should not appear in the query but this is a safe guard
        return False
    
    key_words_found, key_words_found_str = find_key_words(task)
    if not key_words_found:
        return False
    
    slot_number, ucd = extract_ucd_slot(short_description)
    computer_found = []
    
    if slot_number is not None:
        shelf, slot_number_ = get_shelf(device=None, slot_number=int(slot_number))
        if shelf == None or slot_number == None:
            return False
        print(f"{task["number"]} {slot_number}")
        print(f"{task["number"]} {shelf.file_name}")
        shelf.assignDeviceWithSlot(display_name, slot_number)
        
        return True
    else:
        if display_name == "" and (not key_words_found):
            return False
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
                "url": ("http://configurationitem/table/computer?SystemID=SOAP-UI&ReferenceID=*&MaxRows=100&KeyName=u_display_name&KeyValue=" + display_name),
                "headers": {
                    "accept": "application/json",
                },
                "method": "GET"
            }
            response = await call_api(spec["url"], headers=spec["headers"], method=spec["method"])
            computer_found = response["result"]
            
        if len(computer_found) == 0:
            return False
        
        shelf, slot_number_ = get_shelf(computer_found)
        if shelf == None or slot_number == None:
            return False
        shelf.assignDeviceWithSlot(display_name, slot_number)

        return True

def get_tickets():
    unslotted_query_params = "sysparm_query=active=true&sys_class_name=Incident&short_descriptionLIKE"

    first = False
    for key_words in config["key_words"]:
        if not first:
            first = True
            unslotted_query_params += key_words
        else:
            unslotted_query_params += f"^ORshort_descriptionLIKE{key_words}"

    call_specs = [
        { # Rest Call to get TASKs in PAB TechStop Support slotted
            "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=PAB TechStop Support",
            "headers": {
                "accept": "application/json",
                "QueryParams": "sysparm_query=active=true&sys_class_name=Catalog Task&short_descriptionLIKEslot"
            },
            "method": "GET"
        },
        { # Rest Call to get TASKs in TechStop Hardware Support slotted
            "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=TechStop Hardware Support",
            "headers": {
                "accept": "application/json",
                "QueryParams": "sysparm_query=active=true&sys_class_name=Catalog Task&short_descriptionLIKEslot"
            },
            "method": "GET"
        },
        { # Rest call to get INCIDENTs in PAB TechStop Support
            "url": "http://configurationitem/table/incident?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=PAB TechStop Support",
            "headers": {
                    "accept": "application/json",
                    "QueryParams": "sysparm_query=active=true&sys_class_name=Incident&short_descriptionLIKEslot"
            },
            "method": "GET"
        },
        { # Rest call to get INCIDENTs in TechStop Hardware Support
            "url": "http://configurationitem/table/incident?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=TechStop Hardware Support",
            "headers": {
                    "accept": "application/json",
                    "QueryParams": "sysparm_query=active=true&sys_class_name=Incident&short_descriptionLIKEslot"
            },
            "method": "GET"
        },
    ]

    results = run_calls_sync(call_specs=call_specs)
    tickets: list[dict[str, any]] = []

    for result in results:
        tickets.extend(result.get("result", []))
        
    return tickets

async def process_tickets(tickets):
    tasks = []
    for ticket in tickets:
        if "TASK" in str(ticket["number"]):
            tasks.append(assign_task_slot(ticket))
        elif "INC" in str(ticket["number"]):
            tasks.append(assign_task_slot(ticket))  # incidents reuse same logic
    results = await asyncio.gather(*tasks)
    return results

def process_slot_tickets():
    return asyncio.run(process_tickets(get_tickets()))


process_slot_tickets()
