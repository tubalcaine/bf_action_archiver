# bf_action_archiver
A tool to export compressed text archives of BigFix actions and results for audit purposes, with delete option

## BigFix Action Archiver v1.0
### Command line arguments

`usage: actionarchive [-h] [-b BFSERVER] [-p BFPORT] -u BFUSER [-P BFPASS]
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
`