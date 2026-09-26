  @echo off
  cd /d C:\project\game_deals_tracker
  call venv\Scripts\activate.bat
  flask --app app sync-all-prices
  flask --app app check-price-alerts