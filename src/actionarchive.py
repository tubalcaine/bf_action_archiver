import argparse
import os
import sys
import json
import bigfixREST

## MAIN code begins

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--bfserver", type=str, help="BigFix REST Server name/IP address")
parser.add_argument("-p", "--bfport", type=int, help="BigFix Port number (default 52311)", default=52311)
parser.add_argument("-U", "--bfuser", type=str, help="BigFix Console/REST User name")
parser.add_argument("-P", "--bfpass", type=str, help="BigFix Console/REST Password")
parser.add_argument("-o", "--older", type=int, help="Archive non-open actions older than N days")
parser.add_argument("-f", "--folder", type=str, help="Folder to write to", default="./aarchive")
parser.add_argument("-d", "--delete", action="store_true", help="Delete archived actions")
conf = parser.parse_args()

print(conf)

# Create the dest folder if it does not exist
os.makedirs(conf.folder, exist_ok=True)

bf = bigfixREST.bigfixRESTConnection(conf.bfserver, conf.bfport, conf.bfuser, conf.bfpass)

actquery = f'''(id of it, state of it, name of it, time issued of it, name of issuer of it) 
of bes actions 
whose (((now - time issued of it) > {conf.older}*day) and 
(state of it = "Expired" or state of it = "Stopped"))'''.strip()

ares = bf.srQueryJson(actquery)

with open(conf.folder + "/action_data.json", "w") as f:
    f.write(json.dumps(ares, sort_keys=True, indent=4))

with open(conf.folder + "/execution_config_data.json", "w") as f:
    v = vars(conf)
    v["bfpass"] = "Removed_for_Security"

    f.write(json.dumps(v, sort_keys=True, indent=4))

for actid in ares["result"]:
    action = str(bf._get("/api/action/" + str(actid[0])))
    status = str(bf._get("/api/action/" + str(actid[0]) + "/status"))

    actpath = conf.folder + "/" + actid[4]
    os.makedirs(actpath, exist_ok=True)


    with open(actpath + "/" + str(actid[0]) + "_action.xml", "w") as a:
        a.write(action)
    
    
    with open(actpath + "/" + str(actid[0]) + "_result.xml", "w") as a:
        a.write(status)
        
    with open(actpath + "/" + str(actid[0]) + "_META.txt", "w") as a:
        a.write(json.dumps(actid, sort_keys=True, indent=4))
    
    if conf.delete:
        if (action != None and status != None):
            delres = bf._delete("/api/action/" + str(actid[0]))


sys.exit(0)
