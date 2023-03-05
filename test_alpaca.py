#!/usr/bin/env python3



import requests


base_url = "http://zb08-tcu.oca.lan:11111/api/v1"    # zb08 Telescope

def send_request(endpoint, method, params=None):
    headers = {
        # "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    url = f"{base_url}/{endpoint}{method}"
    response = requests.get(url, headers=headers, params=params)
    try:
        j = response.json()
        tex = j['Value']
    except:
        tex = f"Error {response.status_code}:  {response.text}"
    print(f"{endpoint}{method:16}: {tex}")


endpoint = 'telescope/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'alignmentmode')
send_request(endpoint, 'aperturearea')
send_request(endpoint, 'aperturediameter')
send_request(endpoint, 'atpark')
send_request(endpoint, 'altitude')
send_request(endpoint, 'azimuth')
send_request(endpoint, 'canfindhome')
send_request(endpoint, 'canpark')
send_request(endpoint, 'canpulseguide')
send_request(endpoint, 'cansetpark')
send_request(endpoint, 'cansetpierside')
send_request(endpoint, 'cansettracking')
send_request(endpoint, 'canslew')
send_request(endpoint, 'canslewaltaz')
send_request(endpoint, 'canslewaltazasync')
send_request(endpoint, 'canslewasync')
send_request(endpoint, 'cansync')
send_request(endpoint, 'cansyncaltaz')
send_request(endpoint, 'cansetguiderates')
send_request(endpoint, 'cansetpark')



endpoint = 'dome/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'altitude')
send_request(endpoint, 'azimuth')
send_request(endpoint, 'atpark')
send_request(endpoint, 'canfindhome')
send_request(endpoint, 'canpark')
send_request(endpoint, 'cansetaltitude')
send_request(endpoint, 'cansetazimuth')
send_request(endpoint, 'cansetpark')
send_request(endpoint, 'cansetshutter')
send_request(endpoint, 'canslave')
send_request(endpoint, 'cansyncazimuth')


endpoint = 'filterwheel/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'canmove')
send_request(endpoint, 'names')
send_request(endpoint, 'position')
send_request(endpoint, 'focusoffsets')



endpoint = 'focuser/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'absolute')
send_request(endpoint, 'ismoving')
send_request(endpoint, 'maxincrement')
send_request(endpoint, 'maxstep')
send_request(endpoint, 'position')
send_request(endpoint, 'stepsize')
send_request(endpoint, 'tempcomp')
send_request(endpoint, 'tempcompavailable')
send_request(endpoint, 'temperature')


endpoint = 'rotator/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'canreverse')
send_request(endpoint, 'position')
send_request(endpoint, 'reverse')
send_request(endpoint, 'stepsize')
send_request(endpoint, 'targetposition')
send_request(endpoint, 'temperature')



endpoint = 'camera/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'binx')
send_request(endpoint, 'biny')
send_request(endpoint, 'camerastate')
send_request(endpoint, 'canabortexposure')
send_request(endpoint, 'canpulseguide')
send_request(endpoint, 'cansetccdtemperature')
send_request(endpoint, 'cameraxsize')
send_request(endpoint, 'cameraysize')
send_request(endpoint, 'ccdtemperature')
send_request(endpoint, 'setccdtemperature')
send_request(endpoint, 'electronsperadu')
send_request(endpoint, 'fullwellcapacity')
send_request(endpoint, 'gain')
send_request(endpoint, 'hasshutter')
send_request(endpoint, 'cangetcoolerpower')
send_request(endpoint, 'canstopexposure')
send_request(endpoint, 'cooleron')
send_request(endpoint, 'coolerpower')
send_request(endpoint, 'exposuremax')
send_request(endpoint, 'exposuremin')
send_request(endpoint, 'exposureresolution')
send_request(endpoint, 'canfastreadout')
send_request(endpoint, 'fastreadout')
send_request(endpoint, 'imageready')
send_request(endpoint, 'lastexposureduration')
send_request(endpoint, 'lastexposurestarttime')
send_request(endpoint, 'maxadu')
send_request(endpoint, 'numx')
send_request(endpoint, 'numy')
send_request(endpoint, 'readoutmode')
send_request(endpoint, 'readoutmodes')
send_request(endpoint, 'sensorname')
send_request(endpoint, 'sensortype')
send_request(endpoint, 'heatsinktemperature')
send_request(endpoint, 'imagearray')
send_request(endpoint, 'offset')
send_request(endpoint, 'offsets')
send_request(endpoint, 'offsetmax')
send_request(endpoint, 'offsetmin')
send_request(endpoint, 'percentcompleted')
send_request(endpoint, 'subexposureduration')


endpoint = 'covercalibrator/0/'
send_request(endpoint, 'connected')
send_request(endpoint, 'description')
send_request(endpoint, 'driverinfo')
send_request(endpoint, 'driverversion')
send_request(endpoint, 'interfaceversion')
send_request(endpoint, 'name')
send_request(endpoint, 'supportedactions')
send_request(endpoint, 'calibratorstate')
send_request(endpoint, 'brightness')
send_request(endpoint, 'coverstate')
send_request(endpoint, 'maxbrightness')
