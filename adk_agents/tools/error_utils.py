import logging

def log_and_raise_connection_error(message, exception):
    logging.error(f"{message}: {exception}")
    raise ConnectionError(f"{message}: {exception}")

def log_and_raise_import_error(message, exception):
    logging.error(f"{message}: {exception}")
    raise ImportError(f"{message}: {exception}")
