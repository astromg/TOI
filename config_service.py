import settings as st


class Config:

    @staticmethod
    def get(property_name, default=None):
        return getattr(st, property_name, default)

