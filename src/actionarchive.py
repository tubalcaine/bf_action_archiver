"""
actionarchiver.py - A script that backs up all actions issued more than --days
ago that are stopped or expired into a directory structure by issuing operator.
It can optionally delete the actions also. This can provide useful audit
information while also cleaning up actions that bog down the console."""
from getpass import getpass
import argparse
import io
import os
import sys
import json
import zipfile
import tarfile
import threading
import concurrent.futures
import time
from collections import namedtuple
from datetime import datetime

import keyring
import keyring.backends
import bigfixREST
from bigfixREST import BigfixConnectionError, BigfixAuthenticationError, BigfixAPIError

VERSION = "1.2.0"

ActionRecord = namedtuple("ActionRecord", ["id", "state", "name", "time_issued", "issuer", "is_mag"])
MagComponent = namedtuple("MagComponent", ["id", "state", "name"])


class ArchiveWriter:
    """Abstraction for writing files to either a directory or archive format"""

    def __init__(self, path, verbose=False):
        self.path = path
        self.verbose = verbose
        self.archive_type = self._detect_archive_type()
        self.archive_handle = None
        self.lock = threading.Lock()  # Thread-safe access to archive handles

        if self.archive_type == "zip":
            self.archive_handle = zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED)
            if self.verbose:
                print(f"Creating ZIP archive: {path}")
        elif self.archive_type == "tar":
            self.archive_handle = tarfile.open(path, "w")
            if self.verbose:
                print(f"Creating TAR archive: {path}")
        elif self.archive_type == "tar.gz":
            self.archive_handle = tarfile.open(path, "w:gz")
            if self.verbose:
                print(f"Creating TAR.GZ archive: {path}")
        else:
            # Directory mode
            os.makedirs(path, exist_ok=True)
            if self.verbose:
                print(f"Creating directory structure: {path}")

    def _detect_archive_type(self):
        """Detect archive type based on file extension"""
        lower_path = self.path.lower()
        if lower_path.endswith(".zip"):
            return "zip"
        elif lower_path.endswith(".tar.gz") or lower_path.endswith(".tgz"):
            return "tar.gz"
        elif lower_path.endswith(".tar"):
            return "tar"
        else:
            return "directory"

    def makedirs(self, dir_path, exist_ok=True):
        """Create directory - no-op for archives, actual mkdir for directories (thread-safe)"""
        with self.lock:
            if self.archive_type == "directory":
                os.makedirs(dir_path, exist_ok=exist_ok)

    def write_file(self, file_path, content):
        """Write a file to either directory or archive (thread-safe)"""
        with self.lock:
            if self.archive_type == "zip":
                if isinstance(content, str):
                    content = content.encode("utf-8")
                self.archive_handle.writestr(file_path, content)
            elif self.archive_type in ("tar", "tar.gz"):
                if isinstance(content, str):
                    content = content.encode("utf-8")
                tarinfo = tarfile.TarInfo(name=file_path)
                tarinfo.size = len(content)
                tarinfo.mtime = datetime.now().timestamp()
                self.archive_handle.addfile(tarinfo, io.BytesIO(content))
            else:
                # Directory mode - write actual file
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

    def get_path(self, *parts):
        """Get a path suitable for this writer (forward slashes for archives)"""
        if self.archive_type == "directory":
            return os.path.join(self.path, *parts)
        else:
            return "/".join(parts)

    def close(self):
        """Finalize the archive if needed"""
        if self.archive_handle:
            self.archive_handle.close()
            if self.verbose:
                print(f"Archive finalized: {self.path}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def process_action(actid, big_fix, writer, conf, progress_lock, actions_processed, total_actions):
    """Process a single action in a worker thread

    Args:
        actid: ActionRecord namedtuple
        big_fix: BigfixRESTConnection instance
        writer: ArchiveWriter instance (thread-safe)
        conf: Configuration namespace
        progress_lock: Lock for progress reporting and counter
        actions_processed: Shared counter (list with single int for mutability)
        total_actions: Total number of actions to process

    Returns:
        tuple: (success: bool, actid: ActionRecord, error: Exception or None)
    """
    try:
        acturl = f"/api/action/{actid.id}"

        if not conf.quiet:
            with progress_lock:
                print(f"Archiving action {actid.id}: {actid.name} (by {actid.issuer})")

        if conf.verbose:
            with progress_lock:
                print(f"  Fetching from API: {acturl}")

        action = str(big_fix.api_get(acturl))
        action_status = str(big_fix.api_get(acturl + "/status"))

        actpath = writer.get_path(actid.issuer)
        writer.makedirs(actpath, exist_ok=True)

        writer.write_file(
            writer.get_path(actid.issuer, f"{actid.id}_action.xml"),
            action
        )
        writer.write_file(
            writer.get_path(actid.issuer, f"{actid.id}_result.xml"),
            action_status
        )
        writer.write_file(
            writer.get_path(actid.issuer, f"{actid.id}_META.txt"),
            json.dumps(actid._asdict(), sort_keys=True, indent=4)
        )

        if actid.is_mag:
            mag_query = f"""
            (id of it, state of it, name of it) of member actions of bes action
              whose (id of it = {actid.id})
            """
            mag_result = big_fix.relevance_query_json(mag_query)
            mag_components = [MagComponent(*row) for row in mag_result["result"]]

            mag_path = writer.get_path(actid.issuer, f"{actid.id}_MAG")
            writer.makedirs(mag_path, exist_ok=True)

            for mag in mag_components:
                magurl = f"/api/action/{mag.id}"

                if not conf.quiet:
                    with progress_lock:
                        print(f"  - MAG sub-action {mag.id}: {mag.name}")

                if conf.verbose:
                    with progress_lock:
                        print(f"    Fetching from API: {magurl}")

                mag_action = str(big_fix.api_get(magurl))
                mag_action_status = str(big_fix.api_get(magurl + "/status"))

                writer.write_file(
                    writer.get_path(actid.issuer, f"{actid.id}_MAG", f"{mag.id}_action.xml"),
                    mag_action
                )
                writer.write_file(
                    writer.get_path(actid.issuer, f"{actid.id}_MAG", f"{mag.id}_result.xml"),
                    mag_action_status
                )

        with progress_lock:
            actions_processed[0] += 1
            if (not conf.quiet and
                conf.progress > 0 and
                actions_processed[0] % conf.progress == 0 and
                actions_processed[0] < total_actions):
                remaining = total_actions - actions_processed[0]
                percentage = (actions_processed[0] / total_actions) * 100
                print(f"Progress: {actions_processed[0]}/{total_actions} actions archived ({percentage:.1f}% complete, {remaining} remaining)")

        return (True, actid, None)

    except Exception as e:
        return (False, actid, e)


def _delete_action(actid, big_fix, conf):
    """Delete a single action from the server.

    Returns the exception on error, None on success.
    """
    durl = f"/api/action/{actid.id}"
    if conf.verbose:
        print(f"  Running REST API: DELETE {durl}")
    try:
        delres = big_fix.api_delete(durl)
        if delres != b"ok":
            print(f"WARNING: [DELETE https://{conf.bfserver}:{conf.bfport}{durl}] returned {delres}.")
        elif not conf.quiet:
            print(f"  Deleted action {actid.id}: {actid.name}")
        return None
    except BigfixAPIError as e:
        print(f"ERROR deleting action {actid.id}: {e}")
        print("Archive is complete but some actions may not have been deleted.")
        return e


def format_elapsed_time(seconds):
    """Format elapsed time in human readable format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def print_performance_summary(start_time, start_datetime, total_actions, quiet=False):
    """Print performance metrics summary"""
    if quiet:
        return

    end_time = time.time()
    end_datetime = datetime.now()
    elapsed_seconds = end_time - start_time

    if elapsed_seconds > 0:
        actions_per_minute = (total_actions / elapsed_seconds) * 60
    else:
        actions_per_minute = 0

    print(f"\n{'='*60}")
    print(f"Performance Summary:")
    print(f"  Start time:          {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  End time:            {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Elapsed time:        {format_elapsed_time(elapsed_seconds)}")
    print(f"  Actions processed:   {total_actions}")
    print(f"  Processing rate:     {actions_per_minute:.1f} actions/minute")
    print(f"{'='*60}")


def main():
    """main routine"""
    print(f"BigFix Action Archiver v{VERSION}")

    if "--version" in sys.argv or "-V" in sys.argv:
        sys.exit(0)

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
        help="Output path: directory or archive file (.zip, .tar, .tar.gz, .tgz). Default: ./aarchive",
        default="./aarchive",
    )
    parser.add_argument(
        "-d", "--delete", action="store_true", help="Delete archived actions"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output (show extra details)"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Quiet mode (suppress progress messages)"
    )
    parser.add_argument(
        "-n",
        "--progress",
        type=int,
        default=10,
        help="Report progress every N actions (default: 10, 0 to disable)",
    )
    parser.add_argument(
        "-t",
        "--threads",
        type=int,
        default=1,
        help="Number of worker threads for parallel processing (default: 1)",
    )
    parser.add_argument(
        "-B",
        "--batch-size",
        type=int,
        default=0,
        help="Process actions in batches of N (directory output only, 0 to disable, default: 0)",
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
    parser.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Display version information and exit",
    )
    conf = parser.parse_args()

    if conf.progress < 0:
        print("ERROR: Progress interval must be 0 or greater")
        sys.exit(1)

    if conf.threads < 1:
        print("ERROR: Number of threads must be 1 or greater")
        sys.exit(1)
    if conf.threads > 10:
        print(f"WARNING: Using {conf.threads} threads may overload the BigFix server. Recommended maximum is 10.")

    if conf.batch_size < 0:
        print("ERROR: Batch size must be 0 or greater")
        sys.exit(1)
    if conf.batch_size > 0:
        lower_folder = conf.folder.lower()
        if (lower_folder.endswith(".zip") or
            lower_folder.endswith(".tar") or
            lower_folder.endswith(".tar.gz") or
            lower_folder.endswith(".tgz")):
            print("ERROR: Batch processing is only supported with directory output (not ZIP/TAR archives)")
            print("Remove the -B/--batch-size flag or change output to a directory path")
            sys.exit(1)

    if conf.setcreds is not None:
        set_secure_credentials(conf.setcreds, conf.bfuser)
        sys.exit(0)

    if conf.keycreds is not None:
        bfpass = keyring.get_password(conf.keycreds, conf.bfuser)
    else:
        bfpass = conf.bfpass

    if bfpass is None:
        onepass = "not"  # Set to ensure mismatch and avoid fail msg 1st time
        twopass = ""
        print(f"Enter the password for the user {conf.bfuser}")
        print("The password will not display. You must enter the same")
        print("password twice in a row for verification.")

        while onepass != twopass:
            if onepass != "not":
                print("\nPasswords did not match. Try again.\n")

            onepass = getpass(f"BigFix password for {conf.bfuser}: ")
            twopass = getpass("Enter the password again: ")

        bfpass = onepass

    writer = ArchiveWriter(conf.folder, verbose=conf.verbose)

    try:
        big_fix = bigfixREST.BigfixRESTConnection(
            conf.bfserver, conf.bfport, conf.bfuser, bfpass
        )
    except BigfixAuthenticationError as e:
        print(f"AUTHENTICATION ERROR: {e}")
        sys.exit(1)
    except BigfixConnectionError as e:
        print(f"CONNECTION ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"UNEXPECTED ERROR connecting to BigFix: {e}")
        sys.exit(1)

    actquery = f"""(id of it, state of it, name of it, time issued of it,
    name of issuer of it | "_DeletedOperator", multiple flag of it)
    of bes actions
    whose ({conf.whose} and ((now - time issued of it) > {conf.older}*day) and
    top level flag of it and
    (state of it = "Expired" or state of it = "Stopped"))""".strip()

    try:
        ares = big_fix.relevance_query_json(actquery)
    except BigfixAPIError as e:
        print(f"QUERY ERROR: {e}")
        if conf.verbose:
            print(f"Query was: {actquery}")
        sys.exit(1)

    actions = [ActionRecord(*row) for row in ares["result"]]
    total_actions = len(actions)

    if not conf.quiet:
        print(f"Found {total_actions} action(s) to archive.")

    start_time = time.time()
    start_datetime = datetime.now()

    writer.write_file(
        writer.get_path("action_data.json"),
        json.dumps(ares, sort_keys=True, indent=4)
    )

    v_conf = dict(vars(conf))
    v_conf["bfpass"] = "Removed_for_Security"
    writer.write_file(
        writer.get_path("execution_config_data.json"),
        json.dumps(v_conf, sort_keys=True, indent=4)
    )

    progress_lock = threading.Lock()
    actions_processed = [0]  # Use list for mutability across threads
    all_actions_to_delete = []
    all_errors = []

    if not conf.quiet and conf.threads > 1:
        print(f"Using {conf.threads} worker threads for parallel processing.")

    if not conf.quiet and conf.batch_size > 0:
        num_batches = (total_actions + conf.batch_size - 1) // conf.batch_size
        print(f"Processing {total_actions} actions in {num_batches} batch(es) of {conf.batch_size}.")

    if conf.batch_size > 0:
        batches = [actions[i:i+conf.batch_size] for i in range(0, len(actions), conf.batch_size)]
    else:
        batches = [actions]

    for batch_num, batch in enumerate(batches, 1):
        batch_actions_to_delete = []
        batch_errors = []

        if not conf.quiet and conf.batch_size > 0:
            print(f"\nBatch {batch_num}/{len(batches)}: Processing {len(batch)} action(s)...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=conf.threads) as executor:
            futures = {
                executor.submit(
                    process_action,
                    actid,
                    big_fix,
                    writer,
                    conf,
                    progress_lock,
                    actions_processed,
                    total_actions
                ): actid
                for actid in batch
            }

            for future in concurrent.futures.as_completed(futures):
                actid = futures[future]
                try:
                    success, returned_actid, error = future.result()

                    if not success:
                        batch_errors.append((returned_actid, error))
                    elif conf.delete:
                        with progress_lock:
                            batch_actions_to_delete.append(returned_actid)

                except Exception as e:
                    batch_errors.append((actid, e))

        if batch_errors:
            print(f"\nERROR in batch {batch_num}: {len(batch_errors)} action(s) failed to archive:")
            for actid, error in batch_errors:
                print(f"  Action {actid.id} ({actid.name}): {error}")
            all_errors.extend(batch_errors)

        if conf.batch_size > 0 and conf.delete and batch_actions_to_delete and not batch_errors:
            if not conf.quiet:
                print(f"\nBatch {batch_num} complete. Deleting {len(batch_actions_to_delete)} action(s) from server...")

            for actid in batch_actions_to_delete:
                err = _delete_action(actid, big_fix, conf)
                if err:
                    all_errors.append((actid, err))
        else:
            all_actions_to_delete.extend(batch_actions_to_delete)

    if all_errors:
        print(f"\nERROR: {len(all_errors)} total action(s) failed during processing:")
        if not conf.quiet:
            for actid, error in all_errors:
                print(f"  Action {actid.id} ({actid.name}): {error}")
        if conf.batch_size == 0:
            print(f"\nArchiving incomplete due to errors. No actions will be deleted.")
            print_performance_summary(start_time, start_datetime, total_actions, conf.quiet)
            sys.exit(1)

    writer.close()

    if conf.batch_size == 0 and conf.delete and all_actions_to_delete:
        if not conf.quiet:
            print(f"\nArchive complete. Deleting {len(all_actions_to_delete)} action(s) from server...")

        for actid in all_actions_to_delete:
            err = _delete_action(actid, big_fix, conf)
            if err:
                print_performance_summary(start_time, start_datetime, total_actions, conf.quiet)
                sys.exit(1)

    if not conf.quiet:
        if not conf.delete:
            print(f"\nComplete: {total_actions} action(s) archived.")
        else:
            print(f"\nComplete: {total_actions} action(s) archived and deleted.")

    print_performance_summary(start_time, start_datetime, total_actions, conf.quiet)

    sys.exit(0)


def set_secure_credentials(service_name, user_name):
    """Use python keyring to store REST API password in a secure manner for later use"""
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


if __name__ == "__main__":
    main()
