import pyautogui
import cv2
import numpy as np
import time
import os
import re
import shutil
from PIL import Image
import pytesseract
import datetime
from mousekey import MouseKey
from tabulate import tabulate
from collections import defaultdict

# --- MOUSEKEY SETUP ---
mkey = MouseKey()
mkey.enable_failsafekill('ctrl+e')  # Emergency kill: press ctrl+e

# --- CONFIGURATION ---
pytesseract.pytesseract.tesseract_cmd = r'D:\Tesseract\tesseract.exe'

BUY_RARITIES = ["Divine", "Mythical"]
TEMPLATE_FOLDER = "templates"

# Global bounds for seed detection
MIN_Y = 494
MAX_Y = 900

# Define the shop region - full region for scanning
FULL_SHOP_REGION = (600, 250, 750, 650)  # (x, y, w, h) of the shop window

# Point to click to scroll back to top
SCROLL_UP_POINT = (964, 330)
SCROLL_UP_CLICKS = 18

# Restock time box coordinates
RESTOCK_TIME_REGION = (855, 246, 97, 39)  # (x, y, width, height)

FIRST_SEED_SLOT = (1183, 519)  # Center of the first rarity box (absolute screen coordinates)
MAX_SEEDS = 30
NEXT_SEED_OFFSET_Y = 150  # Distance to move down for selecting the next seed

# Offsets relative to the center of the rarity box (measured in screen coordinates)
BUY_BUTTON_OFFSET = (-421, 112)
STOCK_BOX_OFFSET = (-312, -58)

# For OCR cropping (relative to rarity box center, adjust as needed)
SEED_ENTRY_OFFSET = (-576, -178)
SEED_ENTRY_SIZE = (682, 219)
NAME_OFFSET = (-364, -172, 457, 63)
STOCK_OFFSET = (-367, -75, 149, 36)

DEBUG_MODE = False

# --- TRACKING DATA ---
seeds_in_stock = []  # Will contain [timestamp, name, rarity, stock]
seeds_purchased = []  # Will contain [timestamp, name, rarity]

def clear_debug_folder():
    """Delete everything in the debug folder"""
    if os.path.exists("debug"):
        print("Clearing debug folder...")
        for file in os.listdir("debug"):
            file_path = os.path.join("debug", file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
    else:
        os.makedirs("debug")
        print("Created new debug folder.")

def reliable_click(x, y, delay=0.4):
    mkey.left_click_xy_natural(
        int(x), int(y),
        delay=delay,
        min_variation=-2,
        max_variation=2,
        use_every=3,
        sleeptime=(0.01, 0.015),
        print_coords=False,
        percent=90,
    )
    time.sleep(0.4)  # Wait after click for UI to update

def click_multiple(x, y, count, delay=0.2):
    """Click at the same position multiple times"""
    for i in range(count):
        reliable_click(x, y, delay=delay)
        time.sleep(0.1)  # Short delay between clicks

def click_seed(seed_center):
    reliable_click(seed_center[0], seed_center[1])

def click_buy_button(rarity_center):
    x, y = rarity_center
    bx, by = BUY_BUTTON_OFFSET
    reliable_click(x + bx, y + by)

def click_stock_box(rarity_center):
    x, y = rarity_center
    sx, sy = STOCK_BOX_OFFSET
    reliable_click(x + sx, y + sy)

def get_stock_box_center(rarity_center):
    x, y = rarity_center
    sx, sy = STOCK_BOX_OFFSET
    return (x + sx, y + sy)

def safe_crop(img, x, y, w, h):
    h_img, w_img = img.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = min(w, w_img - x)
    h = min(h, h_img - y)
    if w <= 0 or h <= 0:
        return None
    return img[y:y+h, x:x+w]

screenshot_counter = 0

def take_screenshot(region=None, label="screenshot"):
    global screenshot_counter
    img = pyautogui.screenshot(region=region)
    if not os.path.exists("debug"):
        os.makedirs("debug")
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"debug/{label}_{timestamp}_{screenshot_counter}.png"
    img.save(filename)
    screenshot_counter += 1
    return img

def save_debug_image(img, name):
    if not DEBUG_MODE:
        return
    if not os.path.exists("debug"):
        os.makedirs("debug")
    if isinstance(img, np.ndarray):
        cv2.imwrite(f"debug/{name}.png", img)
    else:
        img.save(f"debug/{name}.png")

def load_templates():
    templates = {}
    for rarity in BUY_RARITIES + ["Legendary", "Rare", "Uncommon", "Common"]:
        path = os.path.join(TEMPLATE_FOLDER, f"{rarity.lower()}.png")
        if os.path.exists(path):
            templates[rarity] = cv2.imread(path)
        else:
            print(f"Template not found: {path}")
    return templates

def find_rarity_boxes(shop_img, templates, threshold=0.85):
    found = []
    shop_gray = cv2.cvtColor(shop_img, cv2.COLOR_BGR2GRAY)
    
    for rarity, template in templates.items():
        if template is None:
            continue
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(shop_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= threshold)
        w, h = template_gray.shape[::-1]
        for pt in zip(*loc[::-1]):
            center_x = pt[0] + w // 2
            center_y = pt[1] + h // 2
            # Adjust the center_y to be in the original screen coordinates
            screen_center_y = center_y + FULL_SHOP_REGION[1]
            # Only add if within the valid Y range
            if MIN_Y <= screen_center_y <= MAX_Y:
                found.append({'rarity': rarity, 'center': (center_x, center_y), 'size': (w, h)})
    found = non_max_suppression(found, overlapThresh=0.5)
    return found

def non_max_suppression(boxes, overlapThresh=0.5):
    if len(boxes) == 0:
        return []
    boxes = sorted(boxes, key=lambda x: x['center'][1])
    pick = []
    for box in boxes:
        if not pick or (abs(box['center'][0] - pick[-1]['center'][0]) > 10 or abs(box['center'][1] - pick[-1]['center'][1]) > 10):
            pick.append(box)
    return pick

def get_stock(shop_img, rarity_center, stock_offset):
    dx, dy, w, h = stock_offset
    x, y = rarity_center
    shop_x = x - FULL_SHOP_REGION[0]
    shop_y = y - FULL_SHOP_REGION[1]
    stock_x = int(shop_x + dx)
    stock_y = int(shop_y + dy)
    stock_region = safe_crop(shop_img, stock_x, stock_y, w, h)
    if stock_region is None:
        print(f"Stock region out of bounds at ({stock_x},{stock_y},{w},{h})")
        return None
    save_debug_image(stock_region, f"stock_{x}_{y}")
    pil_img = Image.fromarray(stock_region)
    text = pytesseract.image_to_string(pil_img, config='--psm 7 digits')
    try:
        return int(''.join(filter(str.isdigit, text)))
    except:
        return None

def get_name(shop_img, rarity_center, name_offset):
    dx, dy, w, h = name_offset
    x, y = rarity_center
    shop_x = x - FULL_SHOP_REGION[0]
    shop_y = y - FULL_SHOP_REGION[1]
    name_x = int(shop_x + dx)
    name_y = int(shop_y + dy)
    name_region = safe_crop(shop_img, name_x, name_y, w, h)
    if name_region is None:
        print(f"Name region out of bounds at ({name_x},{name_y},{w},{h})")
        return ""
    save_debug_image(name_region, f"name_{x}_{y}")
    pil_img = Image.fromarray(name_region)
    text = pytesseract.image_to_string(pil_img, config='--psm 7')
    return text.strip()

def get_restock_time():
    """Get the restock time directly from the UI using OCR"""
    try:
        # Take a screenshot of the restock time region
        restock_img = take_screenshot(RESTOCK_TIME_REGION, label="restock_time")
        save_debug_image(restock_img, "restock_time")
        
        # Convert to high contrast image to improve OCR
        restock_np = np.array(restock_img)
        restock_gray = cv2.cvtColor(restock_np, cv2.COLOR_RGB2GRAY)
        _, restock_thresh = cv2.threshold(restock_gray, 150, 255, cv2.THRESH_BINARY)
        save_debug_image(restock_thresh, "restock_time_thresh")
        
        # Convert back to PIL for OCR
        restock_pil = Image.fromarray(restock_thresh)
        
        # Extract text with OCR
        text = pytesseract.image_to_string(restock_pil, config='--psm 7 -c tessedit_char_whitelist=0123456789:')
        text = text.strip()
        
        print(f"Detected restock time: '{text}'")
        
        # Extract minutes and seconds
        time_pattern = r'(\d+):(\d+)'
        match = re.search(time_pattern, text)
        
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            total_seconds = (minutes * 60) + seconds
            print(f"Parsed restock time: {minutes}m {seconds}s = {total_seconds} seconds")
            return total_seconds
        else:
            # As a fallback, try to extract only the numbers
            digits = ''.join(filter(str.isdigit, text))
            if len(digits) >= 3:  # At least 3 digits (m:ss format)
                if len(digits) == 3:  # Format is m:ss (e.g., 2:30 -> 230)
                    minutes = int(digits[0])
                    seconds = int(digits[1:3])
                else:  # Format is mm:ss (e.g., 12:30 -> 1230)
                    minutes = int(digits[0:2])
                    seconds = int(digits[2:4])
                total_seconds = (minutes * 60) + seconds
                print(f"Fallback parsing restock time: {minutes}m {seconds}s = {total_seconds} seconds")
                return total_seconds
            
            print("Could not parse restock time.")
            return None
    except Exception as e:
        print(f"Error getting restock time: {e}")
        return None

def buy_seed(rarity_center, name, rarity, stock):
    """
    Buy all available seeds of the given rarity.
    
    Args:
        rarity_center: (x, y) coordinates of the rarity icon
        name: Name of the seed
        rarity: Rarity of the seed
        stock: Number of seeds in stock
    """
    global seeds_purchased
    
    if not rarity_center or stock <= 0:
        return
    
    # Add an offset to click the buy button from the rarity icon position
    buy_x = rarity_center[0] + BUY_BUTTON_OFFSET[0]
    buy_y = rarity_center[1] + BUY_BUTTON_OFFSET[1]
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Buy all seeds in stock (up to a reasonable limit for safety)
    max_attempts = min(stock, 50)
    purchases_made = 0
    
    print(f"Attempting to buy {max_attempts} {name} seeds (Rarity: {rarity})")
    
    for i in range(max_attempts):
        # Click the buy button
        reliable_click(buy_x, buy_y)
        time.sleep(0.5)
    
    print(f"Successfully purchased {purchases_made} {name} seeds")


def process_seed(templates, return_all=False):
    # Take a screenshot of the full shop region
    shop_img_pil = take_screenshot(FULL_SHOP_REGION, label="shop_window")
    shop_img = cv2.cvtColor(np.array(shop_img_pil), cv2.COLOR_RGB2BGR)

    found = find_rarity_boxes(shop_img, templates)
    if not found:
        print("No rarity box found!")
        if return_all:
            return "", "", None, None, []
        else:
            return "", "", None, None
    for box in found:
        box['center'] = (box['center'][0] + FULL_SHOP_REGION[0], box['center'][1] + FULL_SHOP_REGION[1])
    rarity_box = found[0]
    rarity_center = rarity_box['center']
    rarity = rarity_box['rarity']

    name = get_name(shop_img, rarity_center, NAME_OFFSET)
    stock = get_stock(shop_img, rarity_center, STOCK_OFFSET)
    print(f"Seed: '{name}' | Rarity: {rarity} | Stock: {stock}")

    shop_x = rarity_center[0] - FULL_SHOP_REGION[0]
    shop_y = rarity_center[1] - FULL_SHOP_REGION[1]
    sx = int(shop_x + SEED_ENTRY_OFFSET[0])
    sy = int(shop_y + SEED_ENTRY_OFFSET[1])
    sw, sh = SEED_ENTRY_SIZE
    seed_entry_img = safe_crop(shop_img, sx, sy, sw, sh)
    save_debug_image(seed_entry_img, f"seed_entry_{rarity_center[0]}_{rarity_center[1]}")

    if return_all:
        return name, rarity, stock, rarity_center, found
    else:
        return name, rarity, stock, rarity_center

def aggregate_seeds(seed_list):
    """
    Aggregates a list of seed data by name and rarity.
    
    For seeds_in_stock: [timestamp, name, rarity, stock]
    For seeds_purchased: [timestamp, name, rarity]
    
    Returns list of [name, rarity, count]
    """
    aggregated = defaultdict(int)
    
    # For seeds_in_stock
    if len(seed_list) > 0 and len(seed_list[0]) == 4:
        for timestamp, name, rarity, stock in seed_list:
            key = f"{name}|{rarity}"
            # For in_stock, use the stock value if available
            stock_value = stock if stock is not None else 0
            aggregated[key] += stock_value
    # For seeds_purchased
    else:
        for timestamp, name, rarity in seed_list:
            key = f"{name}|{rarity}"
            # For purchased, count occurrences
            aggregated[key] += 1
    
    # Convert to list format
    result = []
    for key, count in aggregated.items():
        name, rarity = key.split('|', 1)
        result.append([name, rarity, count])
    
    # Sort by rarity and name
    result.sort(key=lambda x: (x[1], x[0]))
    return result

def print_tracking_tables():
    """Print tables with tracking information"""
    print("\n--- SEEDS IN STOCK (AGGREGATED) ---")
    if seeds_in_stock:
        agg_in_stock = aggregate_seeds(seeds_in_stock)
        print(tabulate(agg_in_stock, 
                      headers=["Name", "Rarity", "Stock"],
                      tablefmt="grid"))
    else:
        print("No seeds were detected in stock.")
        
    print("\n--- SEEDS PURCHASED (AGGREGATED) ---")
    if seeds_purchased:
        agg_purchased = aggregate_seeds(seeds_purchased)
        print(tabulate(agg_purchased, 
                      headers=["Name", "Rarity", "Count"],
                      tablefmt="grid"))
    else:
        print("No seeds were purchased.")
    
    # Save all tables to CSV
    save_tracking_data_to_csv()

def save_tracking_data_to_csv():
    """Save all tracking data to CSV files"""
    # Save raw data
    if seeds_in_stock:
        with open("seeds_in_stock_raw.csv", "w") as f:
            f.write("Timestamp,Name,Rarity,Stock\n")
            for seed in seeds_in_stock:
                f.write(f"{seed[0]},\"{seed[1]}\",{seed[2]},{seed[3]}\n")
    
    if seeds_purchased:
        with open("seeds_purchased_raw.csv", "w") as f:
            f.write("Timestamp,Name,Rarity\n")
            for seed in seeds_purchased:
                f.write(f"{seed[0]},\"{seed[1]}\",{seed[2]}\n")
    
    # Save aggregated data
    if seeds_in_stock:
        agg_in_stock = aggregate_seeds(seeds_in_stock)
        with open("seeds_in_stock_aggregated.csv", "w") as f:
            f.write("Name,Rarity,Stock\n")
            for seed in agg_in_stock:
                f.write(f"\"{seed[0]}\",{seed[1]},{seed[2]}\n")
    
    if seeds_purchased:
        agg_purchased = aggregate_seeds(seeds_purchased)
        with open("seeds_purchased_aggregated.csv", "w") as f:
            f.write("Name,Rarity,Count\n")
            for seed in agg_purchased:
                f.write(f"\"{seed[0]}\",{seed[1]},{seed[2]}\n")
    
    # Save combined data (all raw data in one file)
    with open("all_seed_data.csv", "w") as f:
        f.write("Type,Timestamp,Name,Rarity,Stock/Count\n")
        for seed in seeds_in_stock:
            stock = seed[3] if seed[3] is not None else 0
            f.write(f"In_Stock,{seed[0]},\"{seed[1]}\",{seed[2]},{stock}\n")
        for seed in seeds_purchased:
            f.write(f"Purchased,{seed[0]},\"{seed[1]}\",{seed[2]},1\n")

def scan_all_seeds(templates):
    global seeds_in_stock, seeds_purchased
    processed_seeds = set()  # Track which seeds we've already processed by name+rarity
    
    # Click the first seed to start
    click_seed(FIRST_SEED_SLOT)
    time.sleep(0.7)
    name, rarity, stock, rarity_center, _ = process_seed(templates, return_all=True)
    
    # Track this first seed
    if name and rarity:
        seed_identifier = f"{name.strip().lower()}|{rarity}"
        processed_seeds.add(seed_identifier)
        
        # Track seed in stock
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seeds_in_stock.append([timestamp, name, rarity, stock])
    
    # Buy first seed if appropriate
    if rarity in BUY_RARITIES and stock and stock > 0:
        buy_seed(rarity_center, name, rarity, stock)
        time.sleep(0.7)
    
    # CHANGED: Only AFTER buying, close the menu
    time.sleep(0.7)
    click_stock_box(rarity_center)
    time.sleep(1.0)
    
    # Check if the first seed is Cacao (last seed)
    if name and "cacao" in name.lower():
        # Scroll back to top
        click_multiple(SCROLL_UP_POINT[0], SCROLL_UP_POINT[1], SCROLL_UP_CLICKS)
        # ADDED: Click first seed again to reset
        time.sleep(0.5)
        click_seed(FIRST_SEED_SLOT)
        return
    
    # Stop if no valid seed detected
    if not name or name.lower() == "none":
        # Scroll back to top
        click_multiple(SCROLL_UP_POINT[0], SCROLL_UP_POINT[1], SCROLL_UP_CLICKS)
        # ADDED: Click first seed again to reset
        time.sleep(0.5)
        click_seed(FIRST_SEED_SLOT)
        return
    
    # Keep track of consecutive iterations with no new seeds
    no_new_seeds_count = 0
    max_no_new_seeds = 3  # Stop after this many consecutive iterations without new seeds
    
    # Start with the first seed's position
    last_seed_x, last_seed_y = FIRST_SEED_SLOT
    
    for i in range(2, MAX_SEEDS + 1):
        # Calculate position for next seed (below the previous one)
        next_seed_x = last_seed_x
        next_seed_y = last_seed_y + NEXT_SEED_OFFSET_Y
        
        # ADDED: Check before clicking next seed
        # If we've already found Cacao seed as the previous seed, don't continue
        if name and "cacao" in name.lower():
            break
        
        # Click at the calculated position to select next seed
        reliable_click(next_seed_x, next_seed_y)
        time.sleep(0.7)
        
        # Get seed information
        name, detected_rarity, stock, rarity_center, _ = process_seed(templates, return_all=True)
        
        # Check if we've found Cacao Seed (last seed)
        if name and "cacao" in name.lower():
            # Process this last seed
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            seeds_in_stock.append([timestamp, name, detected_rarity, stock])
            
            # Buy this seed if appropriate
            if detected_rarity in BUY_RARITIES and stock and stock > 0:
                buy_seed(rarity_center, name, detected_rarity, stock)
                time.sleep(0.7)
            
            # CHANGED: Only close menu after buying
            time.sleep(0.7)
            click_stock_box(rarity_center)
            time.sleep(1.0)
            
            # Scroll back to top
            click_multiple(SCROLL_UP_POINT[0], SCROLL_UP_POINT[1], SCROLL_UP_CLICKS)
            # ADDED: Click first seed again to reset
            time.sleep(0.5)
            click_seed(FIRST_SEED_SLOT)
            return
        
        # Check if we got a valid seed
        if not name or name.lower() == "none" or "none" in name.lower():
            no_new_seeds_count += 1
            if no_new_seeds_count >= max_no_new_seeds:
                break
            continue
        
        # Create a unique identifier for this seed
        seed_identifier = f"{name.strip().lower()}|{detected_rarity}"
        
        # Check if we've already processed this seed
        if seed_identifier in processed_seeds:
            no_new_seeds_count += 1
            continue
        
        # This is a new seed
        no_new_seeds_count = 0  # Reset counter when we find a new seed
        processed_seeds.add(seed_identifier)
        
        # Track seed in stock
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seeds_in_stock.append([timestamp, name, detected_rarity, stock])
        
        # Update the last seed position for the next iteration
        if rarity_center:
            last_seed_x, last_seed_y = rarity_center
        else:
            last_seed_x, last_seed_y = next_seed_x, next_seed_y
        
        # Buy if appropriate
        if detected_rarity in BUY_RARITIES and stock and stock > 0:
            buy_seed(rarity_center, name, detected_rarity, stock)
            time.sleep(0.7)
        
        # CHANGED: Only close menu after buying
        time.sleep(0.7)
        click_stock_box(rarity_center)
        time.sleep(1.0)
        
        # If we've processed a large number of seeds, we might want to stop
        if i >= MAX_SEEDS:
            break
    
    # Scroll back to top after finishing
    click_multiple(SCROLL_UP_POINT[0], SCROLL_UP_POINT[1], SCROLL_UP_CLICKS)
    # ADDED: Click first seed again to reset
    time.sleep(0.5)
    click_seed(FIRST_SEED_SLOT)


def main():
    while True:
        # Clear debug folder at the start of each run
        clear_debug_folder()
        
        print("\n===== STARTING NEW SCAN =====")
        print("Starting in 5 seconds... Switch to Roblox window!")
        for i in range(5, 0, -1):
            print(f"{i}...")
            time.sleep(1)
            
        templates = load_templates()
        scan_all_seeds(templates)
        
        # Print tracking information
        print_tracking_tables()
        
        # Get the restock time AFTER scanning all seeds
        print("\nChecking restock timer...")
        restock_seconds = get_restock_time()
        
        # Check if we should wait for restock
        if restock_seconds:
            buffer_time = 5  # Add a few seconds buffer
            wait_time = restock_seconds + buffer_time
            
            print(f"\nRestock timer says {restock_seconds} seconds until next restock.")
            print(f"Waiting {wait_time} seconds before next scan...")
            
            # Wait until restock
            for remaining in range(wait_time, 0, -1):
                if remaining % 30 == 0 or remaining <= 10:  # Show countdown every 30 sec and final 10 sec
                    print(f"Restock in {remaining} seconds...")
                time.sleep(1)
        else:
            # If restock time couldn't be read, wait a default time
            default_wait = 60
            print(f"\nCouldn't read restock time. Waiting {default_wait} seconds before next scan...")
            time.sleep(default_wait)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript stopped by user.")
        print_tracking_tables()
        # Ensure we save data on exit
        save_tracking_data_to_csv()
