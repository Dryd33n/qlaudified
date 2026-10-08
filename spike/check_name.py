"""Check whether a name is free on PyPI and GitHub. Python 3.7+. Read-only, unauthenticated.

    py -3 spike/check_name.py [name]
"""

import json
import sys
import urllib.error
import urllib.request


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "qlaudified-name-check"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, None


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "qlaudified"
    status, _ = get("https://pypi.org/pypi/%s/json" % name)
    print("PyPI project %-20s %s" % (name, "FREE" if status == 404 else "TAKEN (%s)" % status))

    status, _ = get("https://api.github.com/users/%s" % name)
    print("GitHub user/org %-16s %s" % (name, "FREE" if status == 404 else "TAKEN (%s)" % status))

    status, data = get("https://api.github.com/search/repositories?q=%s+in:name" % name)
    if data is not None:
        repos = [r["full_name"] for r in data.get("items", [])]
        print("GitHub repos named like it: %d %s" % (data.get("total_count", 0), repos[:10]))
    else:
        print("GitHub repo search failed (%s); likely rate-limited" % status)


if __name__ == "__main__":
    main()
