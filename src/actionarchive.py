"""
actionarchiver.py - A script that backs up all actions issued more  than --days
ago that are stopped or expired int a directory structure by issuing operator.
It can optionally delete the actions also. This can provide useful audit
information while also cleaning up actions that bog down the console."""
from getpass import getpass
import argparse
import os
import sys
import json

import keyring
import keyring.backends
import bigfixREST


def main():
    """main routine"""
    ## MAIN code begins:
    print("BigFix Action Archiver v1.0")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-b",
        "--bfserver",
        type=str,
        help="BigFix REST Server name/IP address",
    )
    parser.add_argument(
        "-p",
        "--bfport",
        type=int,
        help="BigFix Port number (default 52311)",
        default=52311,
    )
    parser.add_argument(
        "-u", "--bfuser", type=str, help="BigFix Console/REST User name", required=True
    )
    parser.add_argument("-P", "--bfpass", type=str, help="BigFix Console/REST Password")
    parser.add_argument(
        "-o",
        "--older",
        type=int,
        help="Archive non-open actions older than N days (default 30)",
        default=30,
    )
    parser.add_argument(
        "-f",
        "--folder",
        type=str,
        help="Folder to write to. Default ./aarchive",
        default="./aarchive",
    )
    parser.add_argument(
        "-d", "--delete", action="store_true", help="Delete archived actions"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output (show details)"
    )
    parser.add_argument(
        "-w",
        "--whose",
        type=str,
        default="true",
        help='Additional session relevance for "bes actions" whose clause, default: true',
    )
    parser.add_argument(
        "-k", "--keycreds", type=str, help="Use stored creds from key. Ex: -k mykey"
    )
    parser.add_argument(
        "-s",
        "--setcreds",
        help="Set credentials store by key name: Ex -s mykey",
        type=str,
    )
    conf = parser.parse_args()

    # setcreds is a "single" operation, do it and terminate.
    if conf.setcreds is not None:
        set_secure_credentials(conf.setcreds, conf.bfuser)
        sys.exit(0)

    if conf.keycreds is not None:
        bfpass = keyring.get_password(conf.keycreds, conf.bfuser)
    else:
        bfpass = conf.bfpass

    # Create the dest folder if it does not exist
    os.makedirs(conf.folder, exist_ok=True)

    big_fix = bigfixREST.BigfixRESTConnection(
        conf.bfserver, conf.bfport, conf.bfuser, bfpass
    )

    actquery = f"""(id of it, state of it, name of it, time issued of it,
    name of issuer of it | "_DeletedOperator", multiple flag of it) 
    of bes actions 
    whose ({conf.whose} and ((now - time issued of it) > {conf.older}*day) and
    top level flag of it and
    (state of it = "Expired" or state of it = "Stopped"))""".strip()

    ares = big_fix.relevance_query_json(actquery)

    if ares is None:
        print(
            "Query result is None: "
            + "This usually means BigFix connection failed or did not authenticate"
        )
        sys.exit(1)

    if conf.verbose:
        print(f"Action query returned {len(ares['result'])} results.")

    with open(conf.folder + "/action_data.json", "w", encoding="utf-8") as f_handle:
        f_handle.write(json.dumps(ares, sort_keys=True, indent=4))

    with open(
        conf.folder + "/execution_config_data.json", "w", encoding="utf-8"
    ) as f_handle:
        v_conf = vars(conf)
        v_conf["bfpass"] = "Removed_for_Security"
        f_handle.write(json.dumps(v_conf, sort_keys=True, indent=4))

    for actid in ares["result"]:
        acturl = f"/api/action/{str(actid[0])}"
        if conf.verbose:
            print(f"Processing action url [{acturl}]")

        action = str(big_fix.api_get(acturl))

        if action is None:
            print("REST API Call failed.")
            sys.exit(1)

        action_status = str(big_fix.api_get(acturl + "/status"))

        if action_status is None:
            print("REST API Call failed.")
            sys.exit(1)

        actpath = f"{conf.folder}/{actid[4]}"
        os.makedirs(actpath, exist_ok=True)

        with open(
            f"{actpath}/{str(actid[0])}_action.xml", "w", encoding="utf-8"
        ) as act_file:
            act_file.write(action)

        with open(
            f"{actpath}/{str(actid[0])}_result.xml", "w", encoding="utf-8"
        ) as act_file:
            act_file.write(action_status)

        with open(
            f"{actpath}/{str(actid[0])}_META.txt", "w", encoding="utf-8"
        ) as act_file:
            act_file.write(json.dumps(actid, sort_keys=True, indent=4))

        ## If we are a multiple action group, we need to make a MAG
        ## directory and populate it with component actions
        if actid[5]:
            mag_query = f"""
            (id of it, state of it, name of it) of member actions of bes action
              whose (id of it = {actid[0]})
            """
            mag_components = big_fix.relevance_query_json(mag_query)
            if mag_components is None:
                print(f"Could not get member actions of MAG id {actid[0]}")
                sys.exit(1)

            mag_path = f"{actpath}/{actid[0]}_MAG"
            os.makedirs(mag_path, exist_ok=True)

            for mag_id in mag_components["result"]:
                magurl = f"/api/action/{str(mag_id[0])}"
                if conf.verbose:
                    print(f"Processing MAG action url [{magurl}]")

                mag_action = str(big_fix.api_get(magurl))

                if mag_action is None:
                    print("REST API Call failed.")
                    sys.exit(1)

                mag_action_status = str(big_fix.api_get(magurl + "/status"))

                if mag_action_status is None:
                    print("REST API Call failed.")
                    sys.exit(1)

                with open(
                    f"{mag_path}/{str(mag_id[0])}_action.xml", "w", encoding="utf-8"
                ) as act_file:
                    act_file.write(action)

                with open(
                    f"{mag_path}/{str(mag_id[0])}_result.xml", "w", encoding="utf-8"
                ) as act_file:
                    act_file.write(action_status)

        # Back the main flow...
        if conf.verbose:
            print(f"Action {acturl} written to {actpath}")

        if conf.delete:
            if action is not None and action_status is not None:
                durl = f"/api/action/{str(actid[0])}"
                if conf.verbose:
                    print(f"Running REST API [DELETE {durl}]")
                delres = big_fix.api_delete(durl)
                if delres != b"ok":
                    print(
                        f"[DELETE https://{conf.bfserver}:{conf.bfport}{durl}] returned {delres}."
                    )
    sys.exit(0)


def set_secure_credentials(service_name, user_name):
    """set_secure_credentials() Use python keyring to store REST API password
    in a secure manner for later use"""
    ## We need to prompt for and save encrypted credentials
    onepass = "not"  # Set to ensure mismatch and avoid fail msg 1st time
    twopass = ""

    print(f"Enter the password for the user {user_name}")
    print("The password will not display. You must enter the same")
    print("password twice in a row. It will be stored encrypted")
    print(f"under the key name {service_name} in your system's")
    print("secure credential store. Use the command switches: ")
    print(f"-k {service_name} -U {user_name}    --OR--")
    print(f"--keycreds {service_name} --bfuser {user_name}")
    print("to run the program without having to provide the password")

    while onepass != twopass:
        if onepass != "not":
            print("\nPasswords did not match. Try again.\n")

        onepass = getpass(f"BigFix password for {user_name}: ")
        twopass = getpass("Enter the password again: ")

        keyring.set_password(service_name, user_name, onepass)
    sys.exit(0)


if __name__ == "__main__":
    # stuff only to run when not called via 'import' here
    main()
