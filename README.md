# Seed Shop Bot - README

This script automates the process of scanning and purchasing seeds in a seed shop interface. It uses image recognition and OCR to detect seed rarities, names, and stock levels, and can automatically purchase seeds of specified rarities.

## Features

- **Automated Seed Scanning**: Systematically scans through all available seeds in the shop
- **Intelligent Purchasing**: Automatically buys seeds of specified rarities
- **Stock Tracking**: Keeps detailed records of which seeds are in stock and which have been purchased
- **Restock Timer**: Monitors the shop's restock timer and automatically rescans after restocks
- **Data Export**: Saves detailed seed data to CSV files for analysis

## Requirements

- Python 3.7 or higher
- Tesseract OCR (installed separately)
- Several Python packages (listed in requirements.txt)
- A folder named "templates" containing reference images for each rarity type

## Installation

1. **Install Python 3.7+** from [python.org](https://www.python.org/downloads/)

2. **Install Tesseract OCR**:
   - Windows: Download from [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
   - Mac: `brew install tesseract`
   - Linux: `sudo apt install tesseract-ocr`

3. **Install Python dependencies**:
4. **Create a "templates" folder** with reference images for each rarity:
- divine.png
- mythical.png
- legendary.png
- rare.png
- uncommon.png
- common.png

5. **Configure the script**:
- Update the path to Tesseract in the script: `pytesseract.pytesseract.tesseract_cmd = r'PATH_TO_TESSERACT'`
- Adjust screen coordinates if needed for your display resolution

## Configuration

The main configuration options are at the top of the script:

- `BUY_RARITIES`: List of seed rarities to automatically purchase (default: ["Divine", "Mythical"])
- `DEBUG_MODE`: Set to True to save debug images (helpful for troubleshooting)
- Various screen coordinates: Adjust these if the bot isn't clicking in the right places for your screen resolution

## Usage

1. Open the game and navigate to the seed shop
2. Run the script:
3. Quickly switch to the game window (you have 5 seconds)
4. The bot will scan all available seeds, purchase designated rarities, and wait for the next restock

## Output Files

The script generates several CSV files:

- `seeds_in_stock_raw.csv`: Raw data of all seeds found in stock
- `seeds_purchased_raw.csv`: Raw data of all seeds purchased
- `seeds_in_stock_aggregated.csv`: Aggregated summary of seeds in stock
- `seeds_purchased_aggregated.csv`: Aggregated summary of seeds purchased
- `all_seed_data.csv`: Combined data of all seed tracking

## Troubleshooting

- **Bot not clicking correctly**: Adjust the screen coordinates in the configuration section
- **OCR not reading text**: Ensure Tesseract is installed and the path is correct
- **Rarity detection failing**: Check that your template images are clear and match what appears in the game
- **Emergency stop**: Press Ctrl+E to force-stop the script at any time

## Safety Notes

- This script uses mouse automation which takes control of your mouse
- Keep Ctrl+E handy to stop the script in case of emergencies
- Only run this script when you don't need to use your computer for other tasks
