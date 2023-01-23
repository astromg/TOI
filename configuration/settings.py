OBSERVATORY_COORD = ("48.3", "14.28", "1000")  # deg,deg,m

ALPACA_BASE_ADDRESS = "800"

OCA_ADDRESS_DICT = {
    "get_dome_azimuth": f"{ALPACA_BASE_ADDRESS}.dome.azimuth",
    "get_dome_status": f"{ALPACA_BASE_ADDRESS}.dome.shutterstatus",  # todo potwierdzic
    "get_dome_shutterstatus": f"{ALPACA_BASE_ADDRESS}.dome.shutterstatus",  # todo potwierdzic i może przetłumaczyć na polski bo zwraca 1,2,3,4
}
