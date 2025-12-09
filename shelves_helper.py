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

    def assignDeviceWithSlot(self, device, slot):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        slot = int(slot)
        if (slot - self.slot_start) >= len(self.slots):
            print(f"{device} {slot} Slot number is larger than current slots available!")
            return
        slot = slot - self.slot_start
        print(slot)
        print(len(self.slots))
        if not self.slots[slot] == None:
            newDevices = []
            if isinstance(self.slots[slot], list):
                for slottedDevice in self.slots[slot]:
                    newDevices.append(slottedDevice)
            else:
                newDevices.append(self.slots[slot])
            newDevices.append(device)
            self.slots[slot] = newDevices
        else:
            self.slots[slot] = device
        self.saveSlots()

    def assignDevice(self, device):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        if self.number_of_devices_per_slot > 1:
            for i in range(0, len(self.slots)):
                if self.slots[i] == None:
                    self.slots[i] = device
                    self.saveSlots()
                    print(f"Device '{device}' assigned to slot {i + self.slot_start}")
                    return i
                else:
                    if isinstance(self.slots[i], list) and (len(self.slots[i]) < self.number_of_devices_per_slot):
                        continue # slot is full
                    else:
                        newDevices = []
                        for slottedDevice in self.slots[i]:
                            newDevices.append(slottedDevice)
                        newDevices.append(device)
                        self.slots[i] = newDevices
                        self.saveSlots()
                        print(f"Device '{device}' assigned to slot {i + self.slot_start}")
                        return i    
        else:
            for i in range(0, len(self.slots)):
                if self.slots[i] == None:
                    self.slots[i] = device
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

    def displaySlots(self):
        if self.number_of_devices_per_slot <= 0: return -1
        self.loadSlots()
        first = False
        for i, device in enumerate(self.slots, 0):
            if not device == None:
                status = device
            elif isinstance(device, Sequence):
                for slottedDevice in device:
                    if first == False:
                        first = True
                        status = slottedDevice
                    else:
                        status = status + f", {slottedDevice}"
            else:
                status = "Empty"
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

#shelves["elite_book_shelf"].assignDevice("NB62KA721Q74")
