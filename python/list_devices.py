import sounddevice as sd

print(sd.query_hostapis())
print("Default hostapi index:", sd.default.hostapi)
print("Host API used:", sd.query_hostapis()[sd.default.hostapi]["name"])
