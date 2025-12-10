import asyncio
from app_helpers import assign_device_to_shelf
from api_client import run_calls_sync
import yaml

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

async def assign_task_slot(task: dict):
    """
    Wrapper function for override mode (backward compatibility).
    Uses assign_device_to_shelf with override_mode=True to assign to specific slot.
    Returns True on success, False on failure.
    """
    result = await assign_device_to_shelf(task, override_mode=True)
    shelf_or_success, slot_number_or_error, is_overfill = result
    
    # For override mode, we return True/False for backward compatibility
    if shelf_or_success is not False:
        # Print debug info (shelf_or_success is the shelf object in override mode)
        if shelf_or_success and slot_number_or_error:
            print(f"{task['number']} {slot_number_or_error}")
            print(f"{task['number']} {shelf_or_success.file_name}")
        return True
    return False

def get_tickets():
    call_specs = [
        { # Rest Call to get TASKs in PAB TechStop Support slotted
            "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=PAB TechStop Support",
            "headers": {
                "accept": "application/json",
                "QueryParams": "sysparm_query=short_descriptionLIKEslot&active=true&sys_class_name=Catalog Task"
            },
            "method": "GET"
        },
        { # Rest Call to get TASKs in TechStop Hardware Support slotted
            "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=TechStop Hardware Support",
            "headers": {
                "accept": "application/json",
                "QueryParams": "sysparm_query=short_descriptionLIKEslot&active=true&sys_class_name=Catalog Task"
            },
            "method": "GET"
        },
        { # Rest call to get INCIDENTs in PAB TechStop Support
            "url": "http://configurationitem/table/incident?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=PAB TechStop Support",
            "headers": {
                    "accept": "application/json",
                    "QueryParams": "sysparm_query=short_descriptionLIKEslot&active=true&sys_class_name=Incident"
            },
            "method": "GET"
        },
        { # Rest call to get INCIDENTs in TechStop Hardware Support
            "url": "http://configurationitem/table/incident?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=TechStop Hardware Support",
            "headers": {
                    "accept": "application/json",
                    "QueryParams": "sysparm_query=short_descriptionLIKEslot&active=true&sys_class_name=Incident"
            },
            "method": "GET"
        }
    ]
    
    for key_words in config["key_words"]:
        spec = {
            "url": "http://configurationitem/table/task?SystemID=SOAP-UI&ReferenceID=*&MaxRows=1000&KeyName=assignment_group&KeyValue=PAB TechStop Support",
            "headers": {
                "accept": "application/json",
                "QueryParams": f"sysparm_query=short_descriptionLIKE{key_words}&active=true&sys_class_name=Catalog Task"
            },
            "method": "GET"
        }
        call_specs.append(spec)

    results = run_calls_sync(call_specs=call_specs)

    #tickets: list[dict[str, any]] = []
    unique_tickets_by_sys_id: dict[str, any] = {}

    for result in results:
        for ticket in result["result"]:
            unique_tickets_by_sys_id[ticket["sys_id"]] = ticket
        #tickets.extend(result.get("result", []))

    #tickets = unique_tickets_by_sys_id(tickets)
    return list(unique_tickets_by_sys_id.values())

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
