import argparse

## MAIN code begins

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--bfserver", type=str, help="BigFix REST Server name/IP address")
parser.add_argument("-p", "--bfport", type=int, help="BigFix Port number (default 52311)", default=52311)
parser.add_argument("-U", "--bfuser", type=str, help="BigFix Console/REST User name")
parser.add_argument("-P", "--bfpass", type=str, help="BigFix Console/REST Password")
parser.add_argument("-o", "--older", type=int, help="Archive non-open actions older than N days")
parser.add_argument("-d", "--delete", action="store_true", help="Delete archived actions")
conf = parser.parse_args()

print(conf)
