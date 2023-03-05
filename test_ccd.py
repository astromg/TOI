#!/usr/bin/env python3



import requests

base_url = "http://zb08-tcu.oca.lan:11111/api/v1/camera/0/"
headers = {"Content-Type": "application/json",}
method='percentcompleted'



url = f"{base_url}{method}"
response = requests.get(url, headers=headers, params=None)
try:
     j = response.json()
     tex = j['Value']
except:
    tex = f"Error {response.status_code}:  {response.text}"
print(f"{tex}")


#method='readoutmodes'
method='camerastate'
url = f"{base_url}{method}"
response = requests.get(url, headers=headers, params=None)
try:
     j = response.json()
     tex = j['Value']
except:
    tex = f"Error {response.status_code}:  {response.text}"
print(f"{tex}")



method='imageready'
url = f"{base_url}{method}"
response = requests.get(url, headers=headers, params=None)
try:
     j = response.json()
     tex = j['Value']
except:
    tex = f"Error {response.status_code}:  {response.text}"
print(f"{tex}")


method='imagearray'
url = f"{base_url}{method}"
response = requests.get(url, headers=headers, params=None)
try:
     j = response.json()
     tex = j['Value']
except: pass
print(len(tex))
