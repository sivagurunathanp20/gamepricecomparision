@echo off
echo === Checking running processes for known Steam emulator tools ===
tasklist | findstr /I "steamemu creamapi steamtools goldberg onlinefix ali213 greenluma smartsteamemu"
echo (if nothing printed above, none found running)
echo.

echo === Checking installed programs ===
wmic product get name 2^>nul | findstr /I "steamemu creamapi steamtools goldberg onlinefix ali213 greenluma smartsteamemu unlocker"
echo (if nothing printed above, none found installed via this method - some tools don't register here)
echo.

echo === Checking for unusual trusted root certificates ===
certutil -store Root | findstr /I "CN="
echo (look through the list above for anything that is NOT a well-known name like Microsoft, DigiCert, GlobalSign, Sectigo, GoDaddy, Entrust, Verisign)
echo.

echo Done. If the process/program checks found something, close it and re-run raw_check.py.
pause
