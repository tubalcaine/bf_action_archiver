"""
bigfixREST.py -- an abortive attempt to make a generic class libary to
access the BigFix core REST API. Consider using jgstew's besapi module
(which is actually in pip) instead:

https://github.com/jgstew/besapi
"""

import json
import threading
import xml.etree.ElementTree as ET
import requests

# This is here ONLY to suppress self-signed certoficate warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# End of warning supression


class BigfixRESTError(Exception):
    """Base exception for BigFix REST API errors"""
    def __init__(self, message, url=None, status_code=None, reason=None):
        self.message = message
        self.url = url
        self.status_code = status_code
        self.reason = reason
        super().__init__(self.message)

    def __str__(self):
        parts = [self.message]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.status_code:
            parts.append(f"HTTP {self.status_code}")
        if self.reason:
            parts.append(f"Reason: {self.reason}")
        return " | ".join(parts)


class BigfixConnectionError(BigfixRESTError):
    """Raised when connection to BigFix server fails"""
    pass


class BigfixAuthenticationError(BigfixRESTError):
    """Raised when authentication fails"""
    pass


class BigfixAPIError(BigfixRESTError):
    """Raised when API call returns an error"""
    pass


## bigFixActionResult class
class BigfixActionResult:
    """A class that represents an API Action Result"""

    def __init__(self, resxml):
        self.xml = resxml
        self.root = ET.fromstring(resxml)

    def get_action_id(self):
        """get the action id"""
        thing = self.root.findall("Action/ID")
        act_id = thing[0].text
        return act_id

    def get_action_url(self):
        """get the action URL"""
        thing = self.root.findall("Action")
        attrs = thing[0].attrib
        return attrs["Resource"]

    def get_action_result_xml(self):
        """return the action result XML"""
        return self.xml


## bigfixRESTConnection class
class BigfixRESTConnection:
    """A class that represents one connection to a BigFix REST API

    Thread Safety:
    This class is thread-safe for concurrent requests. Multiple threads can safely
    call api_get(), api_delete(), and relevance_query_json() on the same instance.
    Each thread gets its own requests.Session via threading.local() to avoid
    conflicts with cookies, redirects, and connection pooling. Authentication
    credentials and configuration are shared across threads.
    """

    def __init__(self, bfserver, bfport, bfuser, bfpass):
        self.bfserver = bfserver
        self.bfport = bfport
        self.bfuser = bfuser
        self.bfpass = bfpass
        self._thread_local = threading.local()  # Each thread gets its own Session
        self.url = "https://" + self.bfserver + ":" + str(self.bfport)
        self.initialized = 0

        # Verify authentication works (using a temporary session)
        test_sess = requests.Session()
        test_sess.auth = (self.bfuser, self.bfpass)
        try:
            resp = test_sess.get(self.url + "/api/login", verify=False, timeout=30)
            if resp.ok:
                self.initialized = 1
            else:
                if resp.status_code == 401:
                    raise BigfixAuthenticationError(
                        "Authentication failed - invalid username or password",
                        url=self.url + "/api/login",
                        status_code=resp.status_code,
                        reason=resp.reason
                    )
                else:
                    raise BigfixConnectionError(
                        "Failed to connect to BigFix server",
                        url=self.url + "/api/login",
                        status_code=resp.status_code,
                        reason=resp.reason
                    )
        except requests.exceptions.RequestException as e:
            raise BigfixConnectionError(
                f"Network error connecting to BigFix server: {str(e)}",
                url=self.url + "/api/login"
            )

    def _get_session(self):
        """Get or create a requests.Session for the current thread"""
        if not hasattr(self._thread_local, 'session'):
            # Create a new session for this thread
            self._thread_local.session = requests.Session()
            self._thread_local.session.auth = (self.bfuser, self.bfpass)
        return self._thread_local.session

    def _check_initialized(self):
        """Check if connection is initialized before making API calls"""
        if not self.initialized:
            raise BigfixConnectionError(
                "BigFix connection not initialized - authentication may have failed"
            )

    def _is_success(self, http_return_value):
        rv_diff = http_return_value - 200
        if rv_diff >= 0 and rv_diff < 100:
            return True

        return False

    def relevance_query_json(self, srquery):
        """Takes a session relevance query and returns a JSON dict
        Raises BigfixAPIError on failure"""
        self._check_initialized()

        qheader = {"Content-Type": "application/x-www-form-urlencoded"}
        qquery = {"relevance": srquery, "output": "json"}

        try:
            sess = self._get_session()
            req = requests.Request(
                "POST", self.url + "/api/query", headers=qheader, data=qquery
            )
            prepped = sess.prepare_request(req)
            result = sess.send(prepped, verify=False, timeout=120)

            if result.status_code == 200:
                retval = json.loads(result.text)
                retval["query"] = srquery
                return retval
            else:
                raise BigfixAPIError(
                    "Session relevance query failed",
                    url=self.url + "/api/query",
                    status_code=result.status_code,
                    reason=result.reason
                )
        except requests.exceptions.RequestException as e:
            raise BigfixAPIError(
                f"Network error during relevance query: {str(e)}",
                url=self.url + "/api/query"
            )

    ## Rawest possible GET
    def api_get(self, url):
        """Does an http GET on a URL and returns the decoded result
        Raises BigfixAPIError on failure"""
        self._check_initialized()

        try:
            sess = self._get_session()
            req = requests.Request("GET", self.url + url)
            res = sess.send(sess.prepare_request(req), verify=False, timeout=60)

            if not self._is_success(res.status_code):
                raise BigfixAPIError(
                    "API GET request failed",
                    url=self.url + url,
                    status_code=res.status_code,
                    reason=res.reason
                )

            return res.text
        except requests.exceptions.RequestException as e:
            raise BigfixAPIError(
                f"Network error during GET request: {str(e)}",
                url=self.url + url
            )

    ## Rawest possible DELETE
    def api_delete(self, url):
        """Calls an http DELETE on a URL and returns the decoded content
        Raises BigfixAPIError on failure"""
        self._check_initialized()

        try:
            sess = self._get_session()
            req = requests.Request("DELETE", self.url + url)
            res = sess.send(sess.prepare_request(req), verify=False, timeout=60)

            if self._is_success(res.status_code):
                return res.content
            else:
                raise BigfixAPIError(
                    "API DELETE request failed",
                    url=self.url + url,
                    status_code=res.status_code,
                    reason=res.reason
                )
        except requests.exceptions.RequestException as e:
            raise BigfixAPIError(
                f"Network error during DELETE request: {str(e)}",
                url=self.url + url
            )

    # The idea of this stub method is that we can parse up the return tuple, mangling the
    # relevance property names to single tokens, and then returning an array of dictionaries,
    # each row of which contains a "row" entry with a flat array and a "dict" entry with
    # the mangled names and values. Usually when you write a relevance query, you know what the
    # positions are in absolute terms. I haven't decided if this is a good idea...
    #    def flattenQueryResult(self, qres):
    #        return None

    def take_sourcedfixletaction(
        self,
        target_list,
        site_id,
        fixlet_id,
        action_id="Action1",
        title="Programmatic Action from Python Script",
    ):
        """Takes a SourcedFixletAction on the given target list using the given
        site id, fixlet id, and action"""
        templ = """\
<?xml version="1.0" encoding="UTF-8" ?>
<BES xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" >
<SourcedFixletAction>
	<SourceFixlet>
		<SiteID>__SiteID__</SiteID>
		<FixletID>__FixletID__</FixletID>
		<Action>__ActionID__</Action>
	</SourceFixlet>
	<Target>
        __TargetList__
	</Target>
	<Settings>
	</Settings>
	<Title>__Title__</Title>
</SourcedFixletAction>
</BES>
""".strip()

        templ = templ.replace("__SiteID__", str(site_id))
        templ = templ.replace("__FixletID__", str(fixlet_id))
        templ = templ.replace("__ActionID__", action_id)
        templ = templ.replace("__Title__", title)

        targets = ""
        for tgt in target_list:
            targets += "<ComputerName>" + tgt + "</ComputerName>\n"

        templ = templ.replace("__TargetList__", targets)

        qheader = {"Content-Type": "application/x-www-form-urlencoded"}

        sess = self._get_session()
        req = requests.Request(
            "POST", self.url + "/api/actions", headers=qheader, data=templ
        )

        prepped = sess.prepare_request(req)

        result = sess.send(prepped, verify=False)

        if self._is_success(result.status_code):
            print(result)
            return BigfixActionResult(result.content)
        else:
            return None
