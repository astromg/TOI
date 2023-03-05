#!/usr/bin/env python3



import requests

quest = "http://zb08-tcu.oca.lan:11111/api/v1/camera/0/startexposure"
method='ccdtemperature'


data={"Duration":20,"Light":True}
response = requests.put(quest,data=data)

try:
     j = response.json()
     tex = j['Value']
except:
    tex = f"Error {response.status_code}:  {response.text}"
print(f"{tex}")



