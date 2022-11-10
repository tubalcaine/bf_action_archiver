"""
actionarchiver.py - A script that backs up all actions issued more  than --days
ago that are stopped or expired int a directory structure by issuing operator.
It can optionally delete the actions also. This can provide useful audit
information while also cleaning up actions that bog down the console."""
import argparse
import os
import sys
import json
import bigfixREST


def main():
    """main routine"""
    ## MAIN code begins:
    print("BigFix Action Archiver v1.0")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s", "--bfserver", type=str, help="BigFix REST Server name/IP address"
    )
    parser.add_argument(
        "-p",
        "--bfport",
        type=int,
        help="BigFix Port number (default 52311)",
        default=52311,
    )
    parser.add_argument(
        "-U", "--bfuser", type=str, help="BigFix Console/REST User name"
    )
    parser.add_argument("-P", "--bfpass", type=str, help="BigFix Console/REST Password")
    parser.add_argument(
        "-o", "--older", type=int, help="Archive non-open actions older than N days"
    )
    parser.add_argument(
        "-f", "--folder", type=str, help="Folder to write to", default="./aarchive"
    )
    parser.add_argument(
        "-d", "--delete", action="store_true", help="Delete archived actions"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output (show details)"
    )
    conf = parser.parse_args()

    # Create the dest folder if it does not exist
    os.makedirs(conf.folder, exist_ok=True)

    big_fix = bigfixREST.BigfixRESTConnection(
        conf.bfserver, conf.bfport, conf.bfuser, conf.bfpass
    )

    actquery = f"""(id of it, state of it, name of it, time issued of it,
    name of issuer of it | "_DeletedOperator") 
    of bes actions 
    whose (((now - time issued of it) > {conf.older}*day) and 
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

        action = str(big_fix.api_get("/api/action/" + str(actid[0])))
        action_status = str(big_fix.api_get("/api/action/" + str(actid[0]) + "/status"))

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


if __name__ == "__main__":
    # stuff only to run when not called via 'import' here
    main()
