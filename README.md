# bf_action_archiver

A Python tool to export complete audit archives of BigFix actions and results, with optional delete capability.

## Overview

This tool queries for all stopped and/or expired actions whose action issued time is more than
a certain number of days old (30 days by default) and writes the complete history of those actions to
either a directory structure or an archive file (ZIP, TAR, or TAR.GZ format).

## Features

- **Multiple output formats**: Directory, ZIP, TAR, or compressed TAR.GZ
- **Secure credential storage**: Uses system keyring to store passwords securely
- **Password prompting**: Double-entry password verification if not provided
- **Progress reporting**: Shows each action being archived (suppressible with `-q`)
- **Error handling**: Clear, detailed error messages with HTTP status codes
- **Multiple Action Group (MAG) support**: Automatically archives baseline sub-actions
- **Optional deletion**: Can delete archived actions from server after archiving
- **Customizable queries**: Filter actions with custom session relevance

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



## Command Line Arguments

```
usage: actionarchive [-h] [-b BFSERVER] [-p BFPORT] -u BFUSER [-P BFPASS]
                     [-o OLDER] [-f FOLDER] [-d] [-v] [-q] [-w WHOSE]
                     [-k KEYCREDS] [-s SETCREDS] [-V]

BigFix Action Archiver v1.0.1

optional arguments:
  -h, --help            Show this help message and exit
  -V, --version         Display version information and exit

Connection options:
  -b BFSERVER, --bfserver BFSERVER
                        BigFix REST Server name/IP address
  -p BFPORT, --bfport BFPORT
                        BigFix Port number (default: 52311)
  -u BFUSER, --bfuser BFUSER
                        BigFix Console/REST User name (required)
  -P BFPASS, --bfpass BFPASS
                        BigFix Console/REST Password (will prompt if not provided)

Credential storage:
  -k KEYCREDS, --keycreds KEYCREDS
                        Use stored credentials from keyring. Example: -k mykey
  -s SETCREDS, --setcreds SETCREDS
                        Store credentials in keyring by key name. Example: -s mykey

Archive options:
  -o OLDER, --older OLDER
                        Archive non-open actions older than N days (default: 30)
  -f FOLDER, --folder FOLDER
                        Output path: directory or archive file (.zip, .tar,
                        .tar.gz, .tgz). Default: ./aarchive
  -d, --delete          Delete archived actions from server after archiving
  -w WHOSE, --whose WHOSE
                        Additional session relevance for "bes actions" whose
                        clause (default: true)

Output options:
  -v, --verbose         Verbose output (show API URLs and extra details)
  -q, --quiet           Quiet mode (suppress progress messages, only show errors)
```

### Password Handling

If you don't provide a password via `-P` or `-k`, the tool will prompt you to enter it securely:
- Password input is hidden (not echoed to screen)
- You must enter the password twice for verification
- If the passwords don't match, you'll be prompted again

## Usage Examples

### Basic Usage

**Display version:**
```bash
python src/actionarchive.py --version
```

**Archive to a directory (will prompt for password):**
```bash
python src/actionarchive.py -b myserver.com -u admin -f ./my_archive
```

**Archive with password on command line:**
```bash
python src/actionarchive.py -b myserver.com -u admin -P mypassword -f ./my_archive
```

### Archive Format Examples

**Archive to a ZIP file:**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.zip
```

**Archive to an uncompressed TAR file:**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.tar
```

**Archive to a compressed TAR.GZ file:**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.tar.gz
```

**Using .tgz extension (equivalent to .tar.gz):**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.tgz
```

### Credential Storage

**Store credentials securely in system keyring:**
```bash
python src/actionarchive.py -u admin -s mykey
# Prompts for password and stores it encrypted
```

**Use stored credentials:**
```bash
python src/actionarchive.py -b myserver.com -u admin -k mykey -f archive.zip
```

### Advanced Options

**Archive actions older than 90 days:**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -o 90 -f archive.tar
```

**Archive and delete actions from server:**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.zip -d
```

**Custom session relevance filter:**
```bash
# Only archive actions by specific user
python src/actionarchive.py -b myserver.com -u admin -P password \
  -w 'name of issuer of it = "jsmith"' -f archive.zip
```

### Output Control

**Quiet mode (only show errors):**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.zip -q
```

**Verbose mode (show API URLs and extra details):**
```bash
python src/actionarchive.py -b myserver.com -u admin -P password -f archive.zip -v
```

**Schedule with cron (quiet mode for log files):**
```bash
# Run daily at 2 AM, log only errors
0 2 * * * /usr/bin/python3 /path/to/src/actionarchive.py \
  -b bigfix.example.com -u archiver -k production \
  -f /backups/bigfix-actions-$(date +\%Y\%m\%d).tar.gz -d -q >> /var/log/bigfix-archive.log 2>&1
```

## Output Modes

The tool provides three levels of output verbosity:

### Default Mode (no flags)

Reports progress for each action being processed:

```
BigFix Action Archiver v1.0.1
Found 5 action(s) to archive.
Archiving action 123: Install Security Patch (by admin)
Archiving action 124: Update Software (by jsmith)
  - MAG sub-action 125: Component A
  - MAG sub-action 126: Component B
  Deleted action 124 from server
Archiving action 125: Windows Updates (by admin)
...

Archiving complete: 5 action(s) processed.
Actions deleted from server.
```

### Quiet Mode (`-q`)

Suppresses all progress messages, only shows errors:

```
BigFix Action Archiver v1.0.1
[Only errors would appear here]
```

Ideal for:
- Cron jobs
- Automated scripts
- Log file management

### Verbose Mode (`-v`)

Shows detailed information including API URLs and operations:

```
BigFix Action Archiver v1.0.1
Creating ZIP archive: archive.zip
Found 5 action(s) to archive.
Archiving action 123: Install Security Patch (by admin)
  Fetching from API: /api/action/123
Archiving action 124: Update Software (by jsmith)
  Fetching from API: /api/action/124
  - MAG sub-action 125: Component A
    Fetching from API: /api/action/125
  Running REST API: DELETE /api/action/124
  Deleted action 124 from server
...

Archiving complete: 5 action(s) processed.
Actions deleted from server.
Archive finalized: archive.zip
```

## Error Handling

The tool provides clear, actionable error messages with context:

### Authentication Errors
```
AUTHENTICATION ERROR: Authentication failed - invalid username or password |
URL: https://server:52311/api/login | HTTP 401 | Reason: Unauthorized
```

### Connection Errors
```
CONNECTION ERROR: Network error connecting to BigFix server: Connection refused |
URL: https://server:52311/api/login
```

### API Errors
```
ERROR fetching action 123: API GET request failed |
URL: https://server:52311/api/action/123 | HTTP 404 | Reason: Not Found
```

All errors include:
- Error type (AUTHENTICATION, CONNECTION, API, etc.)
- Detailed error message
- URL that failed
- HTTP status code and reason (when applicable)

## Installation

### Requirements

- Python 3.x
- Required packages: `argparse`, `keyring`, `requests`

### Install Dependencies

Using pipenv:
```bash
pipenv install
```

Or using pip:
```bash
pip install argparse keyring requests
```

## Notes

- **SSL Verification**: The tool disables SSL certificate verification to work with BigFix's self-signed certificates. This is normal for BigFix environments.
- **Timeouts**: Connection timeout is 30 seconds, queries timeout at 120 seconds, API calls timeout at 60 seconds.
- **MAG Support**: Multiple Action Groups (baselines) are automatically detected and their sub-actions are archived in `{action_id}_MAG/` subdirectories.
- **Secure Storage**: When using `-s` to store credentials, passwords are stored encrypted in your system's secure credential store (Keychain on macOS, Credential Manager on Windows, Secret Service on Linux).
