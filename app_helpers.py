import re
import yaml

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