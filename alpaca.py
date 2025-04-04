#!/usr/bin/env python3


import json
import requests


# Tertiary mirror

# data = {"Action":"selectnasmythport","Parameters":"1"}
# quest = "http://192.168.7.110:11111/api/v1/telescope/0/action"
# r = requests.put(quest, data=data).json()
# r = r['Value']
# print(f"ALPACA: {quest}\n {r}\n")

# data = {"Action":"nasmythport","Parameters":""}
# quest = "http://192.168.7.110:11111/api/v1/telescope/0/action"
# r = requests.put(quest, data=data).json()
# r = r['Value']
# print(f"ALPACA: {quest}\n {r}\n")



# ERROR


# data ={"Action" :"telescope:errorstring" ,"Parameters" :""}
# quest ="http://192.168.7.110:11111/api/v1/telescope/0/action"
# r = requests.put(quest ,data=data).json()
# r= r['Value']
# print(f"ALPACA: {quest}\n {r}\n")

# data = {"Action":"clearerror","Parameters":"1"}
# quest = "http://192.168.7.110:11111/api/v1/telescope/0/action"
# r = requests.put(quest, data=data).json()
# r = r['Value']
# print(f"ALPACA: {quest}\n {r}\n")



# Rotator

#  72.86856842041016

# quest = "http://192.168.7.110:11111/api/v1/rotator/0/moveabsolute"
# data={"Position":"190"}
# r = requests.put(quest, data=data).json()
# print(f"ALPACA: {quest}\n {r}\n")

# quest = "http://192.168.7.110:11111/api/v1/rotator/0/move"
# data={"Position":"10"}
# r = requests.put(quest, data=data).json()
# print(f"ALPACA: {quest}\n {r}\n")

# quest = "http://192.168.7.110:11111/api/v1/rotator/0/movemechanical"
# data={"Position":"150"}
# r = requests.put(quest, data=data).json()
# print(f"ALPACA: {quest}\n {r}\n")

quest = "http://192.168.7.110:11111/api/v1/rotator/0/position"
r = requests.get(quest)
r = r.json()
r = r["Value"]
print(f"ALPACA: {quest}\n {r}\n")
#
quest = "http://192.168.7.110:11111/api/v1/rotator/0/mechanicalposition"
r = requests.get(quest)
r = r.json()
r = r["Value"]
print(f"ALPACA: {quest}\n {r}\n")

# CCD


# quest="http://192.168.7.120:11111/api/v1/camera/0/gain"
#quest="http://192.168.7.120:11111/api/v1/camera/0/camerastate"
# quest="http://192.168.7.120:11111/api/v1/camera/0/setccdtemperature"
#quest="http://192.168.7.120:11111/api/v1/camera/0/description"
#quest="http://192.168.7.120:11111/api/v1/camera/0/numx"
#quest="http://192.168.7.120:11111/api/v1/camera/0/electronsperadu"
#quest="http://192.168.7.120:11111/api/v1/camera/0/exposuremax"
#quest="http://192.168.7.120:11111/api/v1/camera/0/fullwellcapacity"
#quest="http://192.168.7.120:11111/api/v1/camera/0/pixelsizey"
#quest="http://192.168.7.120:11111/api/v1/camera/0/readoutmodes"
#quest="http://192.168.7.120:11111/api/v1/camera/0/readoutmode"

#r = requests.get(quest)
#r = r.json()
#r = r["Value"]
#print(f"ALPACA: {quest}\n {r}\n")


# awaryjny
# txt =""
# dat a ={"Action" :"telescope:errorstring" ,"Parameters" :""}
# ques t ="http://192.168.7.110:11111/api/v1/telescope/0/action"
# r = requests.put(quest ,data=data).json() r= r['Value']
# txt = txt + f"ERROR:  {r}"
#
#data = {"Action": "DomeFansTurnOn", "Parameters": ""}
#quest = "http://192.168.7.110:11111/api/v1/dome/0/action"
#r = requests.put(quest, data=data).json()
#r = r['Value']
#print(r)

# data = {"Command": "DomeFansRunning", "Raw": "false"}
# quest = "http://192.168.7.110:11111/api/v1/dome/0/commandbool"
# r = requests.put(quest, data=data).json()
# r = r['Value']
# print(r)
#
# data = {"Command": "DomeFansTurnOff", "Raw": "false"}
# quest = "http://192.168.7.110:11111/api/v1/dome/0/commandblind"
# r = requests.put(quest, data=data)


# print(txt)

# data={"Action":"MotStat","Parameters":""}
# data={"Action":"telescope:startfans","Parameters":"5"}    # Dome Flat lamps
# data={"Action":"telescope:stopfans","Parameters":""}
# data={"Action":"fansturnon","Parameters":""}
# data={"Action":"fansturnoff","Parameters":""}
# data={"Action":"fansstatus","Parameters":""}
# data={"Action":"telescope:reportmindec","Parameters":""}
# data={"Action":"coverstatus","Parameters":""}
# data={"Action":"telescope:motoron","Parameters":""}
# data={"Action":"telescope:motoroff","Parameters":""}
# data={"Action":"telescope:stopfans","Parameters":""}

# quest="http://192.168.7.110:11111/api/v1/telescope/0/action"
# quest="http://192.168.7.110:11111/api/v1/focuser/0/position"

# data={"Brightness":0}
# quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/opencover"
# quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/closecover"
# quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/coverstate"
# quest="http://192.168.7.110:11111/api/v1/covercalibrator/0/action"

# quest="http://zb08-tcu.oca.lan:11111/api/v1/dome/0/shutterstatus"

# quest="http://192.168.7.110:11111/api/v1/camera/0/gain"
# quest="http://192.168.7.110:11111/api/v1/rotator/0/position"
# quest="http://192.168.7.110:11111/api/v1/telescope/0/utcdate"
# quest="http://192.168.7.110:11111/api/v1/dome/0/abortslew"
# quest="http://192.168.7.110:11111/api/v1/camera/0/camerastate"
# quest="http://192.168.7.110:11111/api/v1/camera/0/setccdtemperature"

#quest="http://192.168.7.110:11111/api/v1/camera/1/description"
#quest="http://192.168.7.110:11111/api/v1/camera/0/numx"
#quest="http://192.168.7.110:11111/api/v1/camera/1/electronsperadu"
#quest="http://192.168.7.110:11111/api/v1/camera/1/exposuremax"
#quest="http://192.168.7.110:11111/api/v1/camera/1/fullwellcapacity"
#quest="http://192.168.7.110:11111/api/v1/camera/1/pixelsizey"
#quest="http://192.168.7.110:11111/api/v1/camera/1/readoutmodes"

#quest="http://192.168.7.110:11111/api/v1/telescope/0/pulseguide"
#data={"Direction":"0","Duration":"1000"}


#r=requests.get(quest)

# data={"Command":"MotStat","Raw":"True"}
# quest="http://192.168.7.110:11111/api/v1/telescope/0/commandstring"

#r=requests.put(quest,data=data)

#r=r.json()
#print(f"ALPACA: {quest}\n {r}\n")
