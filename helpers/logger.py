import sys
from loguru import logger

logger.remove() # remove default logger
logger.add(sys.stderr, format='<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>') # add output to terminal
logger.add("./treyescan.log", rotation="500 MB", level=0) 