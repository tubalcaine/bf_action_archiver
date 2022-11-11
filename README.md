# bf_action_archiver
A tool to export text archives of BigFix actions and results for audit purposes, with optional delete.

This tool queries for all stopped and/or expired actions whose action issued time is more than
a certain number of days old (30 days by default) and writes the whole history of those actions to
a directory structure where:  
- The top level directory contains
    - A file named __execution_config_data.json__ which contains the command line argument values used in the run, with passwords removed
    - A file named __action_data.json__ which contains the results of the session relevance query used to select the actions to archive
    - One folder per user who issued an action being archived. Each folder contains:
        - Three files per action:
            - {action_id}_META.txt which contains the same data as the top-level action data file, but just for this action.
            - {action_id}_action.xml which contains the XML for the action itself (relevance, actionscript, action settings, etc.)
            - {action_id}_result.xml which contains the results of the action on each endpoint that ran the action and returned some result.

This is a complete "audit history" of the actions.

If you specify the -d/--delete option, each action will be deleted from the server after its archive data is written to disk.



## BigFix Action Archiver v1.0
### Command line arguments

    usage: actionarchive [-h] [-b BFSERVER] [-p BFPORT] -u BFUSER [-P BFPASS]
                        [-o OLDER] [-f FOLDER] [-d] [-v]

    optional arguments:
    -h, --help            show this help message and exit
    -b BFSERVER, --bfserver BFSERVER
                            BigFix REST Server name/IP address
    -p BFPORT, --bfport BFPORT
                            BigFix Port number (default 52311)
    -u BFUSER, --bfuser BFUSER
                            BigFix Console/REST User name
    -P BFPASS, --bfpass BFPASS
                            BigFix Console/REST Password
    -o OLDER, --older OLDER
                            Archive non-open actions older than N days (default
                            30)
    -f FOLDER, --folder FOLDER
                            Folder to write to. Default ./aarchive
    -d, --delete          Delete archived actions
    -v, --verbose         Verbose output (show details)
