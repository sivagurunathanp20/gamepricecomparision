@echo off
REM ===================================================================
REM sync_prices.bat
REM Runs the price/image sync for every game with a Steam App ID.
REM Task Scheduler runs this file on a timer (see README instructions).
REM ===================================================================

REM --- EDIT THIS PATH to match where you extracted the project ---
cd /d "C:\Users\sivag\Downloads\game_deals_tracker"

REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Run the sync — refreshes Steam prices/images + CheapShark/ITAD prices
REM for every game that has a Steam App ID set.
flask --app app sync-all-prices

REM Log the run with a timestamp so you can confirm it's actually firing
echo %date% %time% - sync-all-prices finished >> sync_log.txt

deactivate
