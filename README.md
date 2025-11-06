# bf_action_archiver
A tool to export text archives of BigFix actions and results for audit purposes, with optional delete.

This tool queries for all stopped and/or expired actions whose action issued time is more than
a certain number of days old (30 days by default) and writes the whole history of those actions to
either a directory structure or an archive file (ZIP, TAR, or TAR.GZ format).

## Output Formats

The tool automatically detects the desired output format based on the file extension:
- **Directory structure** (default): Use any path without archive extensions
- **ZIP archive**: Use `.zip` extension (e.g., `archive.zip`)
- **TAR archive**: Use `.tar` extension (e.g., `archive.tar`)
- **Compressed TAR archive**: Use `.tar.gz` or `.tgz` extension (e.g., `archive.tar.gz`)

## Archive Structure

When archiving to a directory or archive file, the output structure is:  
- The top level directory contains
    - A file named __execution_config_data.json__ which contains the command line argument values used in the run, with passwords removed
    - A file named __action_data.json__ which contains the results of the session relevance query used to select the actions to archive
    - One folder per user who issued an action being archived. Each folder contains:
        - Three files per action:
            - {action_id}_META.txt which contains the same data as the top-level action data file, but just for this action.
            - {action_id}_action.xml which contains the XML for the action itself (relevance, actionscript, action settings, etc.)
            - {action_id}_result.xml which contains the results of the action on each endpoint that ran the action and returned some result.
        - Multiple Action Groups (baseline actions) also have
            - {action_id}_MAG directory that contains two files per subaction:
                - {subaction_id}_action.xml which contains the XML for the action itself (relevance, actionscript, action settings, etc.)
                - {subaction_id}_result.xml which contains the results of the action on each endpoint that ran the action and returned some result.
            

This is a complete "audit history" of the actions.

If you specify the -d/--delete option, each action will be deleted from the server after its archive data is written to disk.



## BigFix Action Archiver v1.0
### Command line arguments

    usage: actionarchive [-h] [-b BFSERVER] [-p BFPORT] -u BFUSER [-P BFPASS]
                        [-o OLDER] [-f FOLDER] [-d] [-v] [-w WHOSE]

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
                            Output path: directory or archive file (.zip, .tar,
                            .tar.gz, .tgz). Default: ./aarchive
    -d, --delete          Delete archived actions
    -v, --verbose         Verbose output (show details)
    -w WHOSE, --whose WHOSE
                            Additional session relevance for "bes actions" whose
                            clause, default: true

## Examples

### Archive to a directory (default behavior):
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f ./my_archive
```

### Archive to a ZIP file:
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.zip
```

### Archive to a compressed TAR file and delete actions:
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.tar.gz -d -v
```

### Archive using stored credentials:
```bash
# First, store credentials securely
python src/actionarchive.py -u admin -s mykey

# Then use stored credentials with ZIP output
python src/actionarchive.py -b myserver.com -u admin -k mykey -f archive.zip -v
```

### Archive actions older than 90 days to TAR format:
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -o 90 -f archive.tar -v
```
