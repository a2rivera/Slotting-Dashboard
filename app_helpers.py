import re
import yaml
import asyncio
from shelves_helper import get_shelf, shelves
from api_client import call_api

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

def extract_ucd_slot(short_description: str = None):
    if not short_description:
        return None, None
    slot_match = re.search(r"Slot[:\s]*([0-9]+)", short_description, re.IGNORECASE)
    ucd_match = re.search(r"UCD[:\s]*([0-9/]+)", short_description, re.IGNORECASE)
    slot = slot_match.group(1) if slot_match else None
    ucd = ucd_match.group(1) if ucd_match else None
    return slot, ucd

def find_key_words(task : dict):
    key_words_found = False
    key_words_found_str = ""
    for key_words in config["key_words"]:
        if key_words in str(task["short_description"]).lower():
            key_words_found = True
            key_words_found_str = key_words
    return key_words_found, key_words_found_str

async def assign_device_to_shelf(task: dict, override_mode: bool = None):
    """
    Unified function to assign a device to a shelf slot.
    
    This function handles two modes:
    1. Auto-assign mode: Lets the shelf automatically choose an available slot
    2. Override mode: Assigns device to a specific slot number (from task description)
    
    Args:
        task: Dictionary containing task information with keys:
            - short_description: Task short description
            - cmdb_ci: Configuration item display name
            - number: Task number
            - state: Task state (for override mode validation)
        override_mode: Optional boolean to force mode. If None, mode is auto-detected:
            - Override: if "slot" is in short_description and slot number can be extracted
            - Auto-assign: otherwise
    
    Returns:
        Tuple: (shelf_or_false, slot_number_or_error_message, is_overfill_or_false)
        - Success (auto-assign): (shelf, slot_number, is_overfill)
        - Success (override): (shelf, slot_number, False) 
        - Error: (False, error_message, False)
    """
    short_description = re.sub(r"[^\w\s]+", "", str(task["short_description"]).lower())
    display_name = task["cmdb_ci"]
    
    # Auto-detect mode if not specified
    if override_mode is None:
        slot_number_from_desc, ucd = extract_ucd_slot(task["short_description"])
        override_mode = ("slot" in short_description) and (slot_number_from_desc is not None)
    
    # Override mode: assign to specific slot
    if override_mode:
        # Validate task state for override mode
        if str(task.get("state", "")) in ["Cancelled", "Closed", "Resolved"]:
            return False, None, False
        
        # Extract slot number from description
        slot_number_from_desc, ucd = extract_ucd_slot(task["short_description"])
        if slot_number_from_desc is None:
            return False, None, False
        
        # Get shelf based on slot number
        shelf, slot_index = get_shelf(device=None, slot_number=int(slot_number_from_desc))
        if shelf is None or slot_index is None:
            return False, None, False
        
        # Use placeholder if display_name is empty
        if display_name == "":
            display_name = f"placeholder_device_{task['number']}"
        
        # Assign device to specific slot
        shelf.assignDeviceWithSlot(display_name, int(slot_number_from_desc), ticket_number=str(task.get('number', ''))) # We don't use the slot_index here because it is zero indexed and assignDeviceWithSlot expects the slot number not the index/converts to zero based index
        return shelf, int(slot_number_from_desc), False # Returns the shelf, the slot number (from description to add to short description), and False because it is not an overfill
    
    # Auto-assign mode: let shelf choose the slot
    # Check if already slotted (should not happen in auto-assign mode)
    if "slot" in short_description:
        return False, "Cannot slot Device! Task is already slotted. Please double check and confirm if the device is slotted and if the Task is correct. (To 'unslot' the device remove 'Slot' from the Short Description and the system will re-slot it)", False
    
    # Find key words to determine device type
    key_words_found, key_words_found_str = find_key_words(task)
    computer_found = []
    
    if not key_words_found:
        return False, "Cannot slot Device! The task does not contain key words specified. If this is a task that should be slotted please edit the configuration file to include key words in the short description.", False
    
    # Handle display_name and computer_found
    if display_name == "" and (not key_words_found):
        return False, "Cannot slot Device! There is no Configuration item listed! Please correct the task and add the CI in the field.", False
    elif display_name == "" and key_words_found:
        # If there is no CI, we use a placeholder device name
        display_name = f"placeholder_device_{task['number']}"
        computer_found = [
            {
                "asset": key_words_found_str, # The key words found in the short description, this is used to determine the type of device to slot
                "sys_class_name": "none"
            }
        ]
    elif display_name != "" and key_words_found:
        # If there is a CI, we use the CI to determine the type of device to slot
        spec = {
            "url": f"http://configurationitem/table/computer?SystemID=SOAP-UI&ReferenceID=*&MaxRows=100&KeyName=u_display_name&KeyValue={task['cmdb_ci']}",
            "headers": {
                "accept": "application/json"
            },
            "method": "GET"
        }
        response = await call_api(spec["url"], headers=spec["headers"], method=spec["method"])
        computer_found = response["result"]
    
    if len(computer_found) == 0: # If there is no computer found, we return an error
        return False, "Cannot slot Device! Cannot determine what type of device this is, needs to be defined in the the config file via key words", False
    
    # Get shelf and assign device (let shelf choose slot)
    shelf, _ = get_shelf(computer_found) # We don't use the slot_index here because it is zero indexed and assignDevice expects the slot number not the index/converts to zero based index
    if shelf is None: # If there is no shelf found, we return an error
        return False, "Could not find shelf for device", False
    
    slot_index = shelf.assignDevice(display_name, ticket_number=str(task.get('number', ''))) # We don't use the slot_index here because it is zero indexed and assignDevice expects the slot number not the index/converts to zero based index
    
    # Handle overflow case (no available slots)
    if slot_index is None: # If there is no slot found, that means the shelf is full and we need to assign the device to the overflow slot
        display_name = f"placeholder_overfill_{task['number']}"
        overfill_shelf, overfill_slot = resolve_overflow_shelf(computer_found)
        if overfill_shelf is None:
            return False, "Could not find overflow shelf for device", False
        slot_to_use = overfill_slot if overfill_slot is not None else overfill_shelf.slot_start
        overfill_shelf.assignDeviceWithSlot(display_name, slot_to_use, ticket_number=str(task.get('number', '')))  # Uses the configured overflow slot (or shelf start)
        return overfill_shelf, slot_to_use, True
    
    # Return shelf, actual slot number (index + start), and overflow flag
    return shelf, (slot_index + shelf.slot_start), False

def resolve_overflow_shelf(device: list[dict]):
    """
    Determine the overflow shelf and slot based on configured overflow_rules.
    Returns (shelf_object_or_none, slot_number_or_none)
    """
    rules = config.get("overflow_rules", [])
    if not device:
        return None, None
    asset = str(device[0].get("asset", "")).lower()
    sys_class = str(device[0].get("sys_class_name", "")).lower()
    for rule in rules:
        for kw in rule.get("keywords", []):
            kw_lower = str(kw).lower()
            if kw_lower in asset or kw_lower in sys_class:
                shelf_name = rule.get("shelf")
                shelf_obj = shelves.get(shelf_name)
                if shelf_obj is None:
                    continue
                return shelf_obj, rule.get("slot")
    return None, None