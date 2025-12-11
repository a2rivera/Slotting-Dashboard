from __future__ import annotations

import json
from collections.abc import Sequence
import time
from filelock import FileLock, Timeout
import os
import yaml

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

shelves: dict[str, Shelf] = {}

class Shelf:
    def __init__(self, slotsNumber, file_name, slot_start, device_name, number_of_devices_per_slot):
        self.number_of_slots = slotsNumber
        self.file_name = file_name
        self.slots = [None] * (self.number_of_slots)
        self.slot_start = slot_start
        self.device_name = device_name
        self.number_of_devices_per_slot = number_of_devices_per_slot

    def loadSlots(self):
        while True:
            try:
                with FileLock(f"ShelfJSON/{self.file_name}" + ".lock"): # Locks the JSON file 
                    if os.path.exists(f"ShelfJSON/{self.file_name}"):
                        with open(f"ShelfJSON/{self.file_name}", 'r') as file:
                            slots = json.load(file)
                            if len(slots) != self.number_of_slots:
                                raise ValueError("Slot count mismatch")
                            self.slots = slots
                            return slots
                break
            except Timeout:
                print("File is locked cannot load! Retrying in 5 seconds...")
                time.sleep(5)  # Wait before retrying
            except (FileNotFoundError, ValueError, json.JSONDecodeError):
                return [None] * self.number_of_slots

    def saveSlots(self):
        while True:
            try:
                with FileLock(f"ShelfJSON/{self.file_name}" + ".lock"): # Locks the JSON file 
                    temp_file_path = f"ShelfJSON/{self.file_name}" + '.tmp'
                    with open(temp_file_path, 'w') as file:
                        json.dump(self.slots, file)
                    os.replace(temp_file_path, f"ShelfJSON/{self.file_name}")
                break
            except Timeout:
                print("File is locked cannot save! Retrying in 5 seconds...")
                time.sleep(5)  # Wait before retrying

    def assignDeviceWithSlot(self, device, slot, ticket_number):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        slot = int(slot)
        
        # Check if slot is within valid range (must be >= slot_start and < slot_start + number_of_slots)
        if slot < self.slot_start:
            print(f"{device} {slot} Slot number is less than shelf start slot {self.slot_start}!")
            return None
        
        slot_index = slot - self.slot_start
        if slot_index >= len(self.slots):
            print(f"{device} {slot} Slot number is larger than current slots available!")
            return None
        
        # Validate slot_index is non-negative (should be caught above, but double-check)
        if slot_index < 0:
            print(f"{device} {slot} Invalid slot index calculated: {slot_index}")
            return None
        
        # Store device with ticket number (new format only)
        device_entry = {"device": device, "ticket": ticket_number}
        
        # Check if adding device would exceed max devices per slot (warning only, since this is an override)
        if not self.slots[slot_index] == None:
            current_count = len(self.slots[slot_index]) if isinstance(self.slots[slot_index], list) else 1
            
            # Extract device names for comparison
            existing_devices = []
            if isinstance(self.slots[slot_index], list):
                for d in self.slots[slot_index]:
                    existing_devices.append(d.get("device", "") if isinstance(d, dict) else "")
            else:
                existing_devices.append(self.slots[slot_index].get("device", "") if isinstance(self.slots[slot_index], dict) else "")
            
            if str(device).lower() in [str(d).lower() for d in existing_devices if d]:
                print(f"Device '{device}' already present in slot {slot}; skipping.")
                return slot_index

            if current_count >= self.number_of_devices_per_slot and self.number_of_devices_per_slot > 0:
                print(f"Warning: Slot {slot} already has {current_count} device(s), max is {self.number_of_devices_per_slot}. Adding anyway (override mode).")
            
            newDevices = []
            if isinstance(self.slots[slot_index], list):
                for slottedDevice in self.slots[slot_index]:
                    newDevices.append(slottedDevice)
            else:
                newDevices.append(self.slots[slot_index])
            newDevices.append(device_entry)
            self.slots[slot_index] = newDevices
        else:
            self.slots[slot_index] = device_entry
        
        self.saveSlots()
        print(f"Device '{device}' assigned to slot {slot} (override)")
        return slot_index

    def assignDevice(self, device, ticket_number):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        
        # Store device with ticket number (new format only)
        device_entry = {"device": device, "ticket": ticket_number}
        
        if self.number_of_devices_per_slot > 1:
            for i in range(0, len(self.slots)):
                if self.slots[i] == None:
                    self.slots[i] = device_entry
                    self.saveSlots()
                    print(f"Device '{device}' assigned to slot {i + self.slot_start}")
                    return i
                else:
                    # Slot is not empty - check if it can accommodate more devices
                    if isinstance(self.slots[i], list):
                        # Slot is a list - check if it has room
                        if len(self.slots[i]) < self.number_of_devices_per_slot:
                            # Has room - add device to list
                            self.slots[i].append(device_entry)
                            self.saveSlots()
                            print(f"Device '{device}' assigned to slot {i + self.slot_start}")
                            return i
                        else:
                            # Slot is full - continue to next slot
                            continue
                    else:
                        # Slot has a single device - convert to list and add device
                        newDevices = [self.slots[i], device_entry]
                        self.slots[i] = newDevices
                        self.saveSlots()
                        print(f"Device '{device}' assigned to slot {i + self.slot_start}")
                        return i    
        else:
            for i in range(0, len(self.slots)):
                if self.slots[i] == None:
                    self.slots[i] = device_entry
                    self.saveSlots()
                    print(f"Device '{device}' assigned to slot {i + self.slot_start}")
                    return i
                
        print(f"No empty slots available\n{self.file_name}")
        return None

    def removeDevice(self, slot):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        if 0 <= slot < len(self.slots) and not self.slots[slot] == None:
            device = self.slots[slot]                
            self.slots[slot] = None
            self.saveSlots()
            print(f"Device '{device}' removed from slot {slot}")
            return device
        print("Invalid slot or slot already empty")
        return None
    
    def removeDevicesFromClosedTickets(self, active_ticket_numbers: set):
        """
        Remove devices from shelves that are associated with closed tickets.
        Devices whose tickets are not in the active_ticket_numbers set will be removed.
        """
        self.loadSlots()
        removed_count = 0
        modified = False
        
        for slot_index, slot_content in enumerate(self.slots):
            if slot_content is None:
                continue
            
            # Handle single device
            if not isinstance(slot_content, list):
                if isinstance(slot_content, dict):
                    ticket = slot_content.get("ticket")
                    if ticket and ticket not in active_ticket_numbers:
                        device_name = slot_content.get("device", "")
                        self.slots[slot_index] = None
                        modified = True
                        removed_count += 1
                        print(f"Removed device '{device_name}' from slot {slot_index + self.slot_start} (ticket {ticket} is closed)")
                continue
            
            # Handle list of devices
            preserved_devices = []
            for device_entry in slot_content:
                if isinstance(device_entry, dict):
                    ticket = device_entry.get("ticket")
                    if ticket and ticket not in active_ticket_numbers:
                        device_name = device_entry.get("device", "")
                        removed_count += 1
                        print(f"Removed device '{device_name}' from slot {slot_index + self.slot_start} (ticket {ticket} is closed)")
                        continue
                preserved_devices.append(device_entry)
            
            # Update slot if devices were removed
            if len(preserved_devices) != len(slot_content):
                if len(preserved_devices) == 0:
                    self.slots[slot_index] = None
                elif len(preserved_devices) == 1:
                    self.slots[slot_index] = preserved_devices[0]
                else:
                    self.slots[slot_index] = preserved_devices
                modified = True
        
        if modified:
            self.saveSlots()
        
        if removed_count > 0:
            print(f"Removed {removed_count} device(s) from closed tickets on {self.file_name}")
        
        return removed_count

    def displaySlots(self):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        for i, device in enumerate(self.slots, 0):
            if device == None:
                status = "Empty"
            elif isinstance(device, Sequence) and not isinstance(device, str):
                first = True
                status = ""
                for slottedDevice in device:
                    device_name = slottedDevice.get("device", "") if isinstance(slottedDevice, dict) else ""
                    if first:
                        first = False
                        status = device_name
                    else:
                        status = status + f", {device_name}"
            else:
                status = device.get("device", "") if isinstance(device, dict) else ""
            print(f"Slot {i + self.slot_start}: {status}")

# Function that returns the shelf that a device should be assigned to
# It can use either the device or slot_number to find which shelf it pertains to
# The device doesn't necessarily have to be assigned or unassigned to the shelf to find its correct shelf assignment
def get_shelf(device: list = None, slot_number: int = None):
    shelf_assignment: str = None
    shelf: Shelf = None
    
    # Device based assignment
    if device is not None:
        for shelf_assignment_list in config["shelf_assignment"].values():
            for device_asset_name in shelf_assignment_list[0]:
                if str(device_asset_name).lower() in str(device[0]["asset"]).lower() or str(device_asset_name).lower() in str(device[0]["sys_class_name"]).lower():
                    shelf_assignment = shelf_assignment_list[1] # We don't use "key" here because we have different shelf names we're finding, for example the "mac" shelf, which isn't a shelf but we return it so that the user can then be emailed
                    # We don't break here because it may find another shelf that is more applicable to be assigned to (for example "zbook g11")
                    
    # Assign shelf by name if found
    if shelf_assignment is not None:
        shelf = shelves[shelf_assignment]

    # Slot number based assignment
    if slot_number is not None:
        for shelf_iter in shelves.values():
            start = shelf_iter.slot_start
            end = start + shelf_iter.number_of_slots - 1
            if slot_number >= start and slot_number <= end:
                shelf = shelf_iter
                slot_number -= start # Converts the slot number to zero based index
                break

    return shelf, slot_number

if not shelves: # Clause so that importing into other scripts doesn't re-initialize shelf objects
    for key, value in config["shelf_objects"].items():
        shelf_object = Shelf(value[0], key, value[1], value[2], value[3])  # Create a shelf with given slots, file_name, slotting start number, # of slots per device
        shelves[key] = shelf_object # Store shelf in dictionary

#shelves["phone_shelf"].displaySlots()
