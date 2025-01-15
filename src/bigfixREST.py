"""
bigfixREST.py -- an abortive attempt to make a generic class libary to
access the BigFix core REST API. Consider using jgstew's besapi module
(which is actually in pip) instead:

https://github.com/jgstew/besapi
"""

import json
import xml.etree.ElementTree as ET
import requests

# This is here ONLY to suppress self-signed certoficate warnings
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# End of warning supression


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
    """A class that represents one connection to a BigFix REST API"""

    def __init__(self, bfserver, bfport, bfuser, bfpass):
        self.bfserver = bfserver
        self.bfport = bfport
        self.bfuser = bfuser
        self.bfpass = bfpass
        self.sess = requests.Session()
        self.url = "https://" + self.bfserver + ":" + str(self.bfport)
        self.initialized = 0

        self.sess.auth = (self.bfuser, self.bfpass)
        resp = self.sess.get(self.url + "/api/login", verify=False)
        if resp.ok:
            self.initialized = 1

    def _is_success(self, http_return_value):
        rv_diff = http_return_value - 200
        if rv_diff >= 0 and rv_diff < 100:
            return True

        return False

    def relevance_query_json(self, srquery):
        """Takes a session relevance query and returns a JSON string
        on success and None on error"""
        qheader = {"Content-Type": "application/x-www-form-urlencoded"}

        qquery = {"relevance": srquery, "output": "json"}

        req = requests.Request(
            "POST", self.url + "/api/query", headers=qheader, data=qquery
        )

        prepped = self.sess.prepare_request(req)
        result = self.sess.send(prepped, verify=False)

        if result.status_code == 200:
            retval = json.loads(result.text)
            retval["query"] = srquery
            return retval

        return None

    ## Rawest possible GET
    def api_get(self, url):
        """Does an http GET on a URL and returns the decoded result
        or None on error"""
        req = requests.Request("GET", self.url + url)
        res = self.sess.send(self.sess.prepare_request(req), verify=False)

        if not self._is_success(res.status_code):
            print(f"Error: {res.status_code} Reason: {res.reason}")
            return None

        return res.text

    ## Rawest possible DELETE
    def api_delete(self, url):
        """Calls an http DELETE on a URL and returns the decoded content
        or None on error"""
        req = requests.Request("DELETE", self.url + url)
        res = self.sess.send(self.sess.prepare_request(req))

        if self._is_success(res.status_code):
            return res.content

        return None

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

        req = requests.Request(
            "POST", self.url + "/api/actions", headers=qheader, data=templ
        )

        prepped = self.sess.prepare_request(req)

        result = self.sess.send(prepped, verify=False)

        if self._is_success(result.status_code):
            print(result)
            return BigfixActionResult(result.content)
        else:
            return None
