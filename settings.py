import logging

OBSERVATORY_COORD = ("0", "0", "0")  # deg,deg,m

ALPACA_BASE_ADDRESS = ""

OCA_ADDRESS_DICT = {

}

#  import all custom settings
try:
    from configuration.settings import *
except ImportError:
    logging.warning('configuration/settings.py not found. Create this file customise TOI app settings')
