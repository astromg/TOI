import pathlib

OBSERVATORY_COORD = ("48.3", "14.28", "1000")  # deg,deg,m

PATH_TO_CONFIG_DIR = pathlib.Path().resolve()


ALPACA_BASE_ADDRESS = "sim"

OCA_ADDRESS_DICT = {
    "get_current_user_control": f"{ALPACA_BASE_ADDRESS}.access_grantor.current_user",
    "get_dome_azimuth": f"{ALPACA_BASE_ADDRESS}.dome.azimuth",
    "get_dome_status": f"{ALPACA_BASE_ADDRESS}.dome.shutterstatus",  # todo potwierdzic
    "get_dome_shutterstatus": f"{ALPACA_BASE_ADDRESS}.dome.shutterstatus",  # todo potwierdzic i może przetłumaczyć na polski bo zwraca 1,2,3,4
    "get_telescope_rightascension": f"{ALPACA_BASE_ADDRESS}.mount.rightascension",
    "get_telescope_declination": f"{ALPACA_BASE_ADDRESS}.mount.declination",
    "get_telescope_altitude": f"{ALPACA_BASE_ADDRESS}.mount.altitude",
    "get_telescope_azimuth": f"{ALPACA_BASE_ADDRESS}.mount.azimuth",
    "get_telescope_connected": f"{ALPACA_BASE_ADDRESS}.mount.connected",
    "get_telescope_utcdate": f"{ALPACA_BASE_ADDRESS}.mount.utcdate",
    "get_covercalibrator_coverstate": f"{ALPACA_BASE_ADDRESS}.covercalibrator.coverstate",
    "get_filterwheel_position": f"{ALPACA_BASE_ADDRESS}.filterwheel.position",
    "get_filterwheel_names": f"{ALPACA_BASE_ADDRESS}.filterwheel.names",
    "get_focuser_position": f"{ALPACA_BASE_ADDRESS}.focuser.position",

    "put_take_control": f"{ALPACA_BASE_ADDRESS}.access_grantor.take_control",
    "put_dome_azimuth": f"{ALPACA_BASE_ADDRESS}.dome.slewtoazimuth",
    "put_dome_shutter_open": f"{ALPACA_BASE_ADDRESS}.dome.openshutter",
    "put_dome_shutter_close": f"{ALPACA_BASE_ADDRESS}.dome.closeshutter",
    "put_telescope_slewtocoordinates": f"{ALPACA_BASE_ADDRESS}.mount.slewtocoordinates",
    "put_telescope_slewtoaltaz": f"{ALPACA_BASE_ADDRESS}.mount.slewtoaltaz",
    "put_telescope_tracking": f"{ALPACA_BASE_ADDRESS}.mount.tracking",
    "put_telescope_abortslew": f"{ALPACA_BASE_ADDRESS}.mount.abortslew",
    "put_telescope_park": f"{ALPACA_BASE_ADDRESS}.mount.park",
    "put_telescope_unpark": f"{ALPACA_BASE_ADDRESS}.mount.unpark",
    "put_covercalibrator_close": f"{ALPACA_BASE_ADDRESS}.covercalibrator.closecover",
    "put_covercalibrator_open": f"{ALPACA_BASE_ADDRESS}.covercalibrator.opencover",
    "put_filterwheel_position": f"{ALPACA_BASE_ADDRESS}.filterwheel.position",
    "put_focuser_move": f"{ALPACA_BASE_ADDRESS}.focuser.move",

}
