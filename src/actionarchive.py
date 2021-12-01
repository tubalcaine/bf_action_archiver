import argparse

## MAIN code begins

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", required=True, type=str, help="Path to JSON configuration file")
conf = parser.parse_args()

print(conf)
