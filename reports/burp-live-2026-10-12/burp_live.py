"""Verify an already running Burp extension against an owned loopback fixture."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import select
import socket
import sys
import threading
import time
import uuid


API = ("127.0.0.1", 9876)
PROXY = ("127.0.0.1", 8080)
FIXTURE = ("127.0.0.1", 18089)
SOURCE_HEAD = "d19105f6f7843f7dd28becdcfcdcdc0167d2b86c"


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def counts(result, requests, errors, hits):
    for key, expected in zip(("total_requests", "errors", "hits"), (requests, errors, hits)):
        expect(result.get(key) == expected, f"{key}: expected {expected}, observed {result.get(key)!r}")
    expect(len(result.get("hit_details", [])) == hits, "hit_details count differs from hits")


class Run:
    def __init__(self, directory, cases_file, events_file):
        self.directory = directory
        self.cases_file, self.events_file = cases_file, events_file
        self.start = time.monotonic()
        self.tag = "burp19-" + uuid.uuid4().hex[:12]
        self.base = f"http://{FIXTURE[0]}:{FIXTURE[1]}/{self.tag}"
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.cases, self.events = [], []
        self.active = 0

    def event(self, event, **fields):
        with self.lock:
            if event == "accepted":
                self.active += 1
            elif event == "finished":
                self.active -= 1
            row = {"t": time.monotonic() - self.start, "event": event, "active": self.active, **fields}
            self.events.append(row)
            self.events_file.write(json.dumps(row) + "\n")
            self.events_file.flush()

    def arrivals(self, suffix=None):
        with self.lock:
            return [dict(e) for e in self.events if e["event"] == "accepted"
                    and (suffix is None or e["path"].startswith(f"/{self.tag}/{suffix}"))]

    def record(self, row):
        with self.lock:
            self.cases.append(row)
            self.cases_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.cases_file.flush()
        print(f"{'FAIL' if row['failures'] else 'PASS'} {row['name']}: {row['failures'] or 'expected fields observed'}", flush=True)

    def case(self, name, tool, params, check, timeout=30):
        envelope = {"tool": tool, "params": params}
        row = {"name": name, "kind": "tool", "input": envelope,
               "started_s": time.monotonic() - self.start, "failures": []}
        connection = http.client.HTTPConnection(*API, timeout=timeout)
        result = None
        print(f"START {name}", flush=True)
        try:
            connection.request("POST", "/", json.dumps(envelope).encode(), {"Content-Type": "application/json"})
            response = connection.getresponse()
            row["http_status"] = response.status
            row["response_headers"] = response.getheaders()
            row["raw_response"] = response.read().decode("utf-8", errors="replace")
            result = json.loads(row["raw_response"])
            row["response"] = result
            expect(response.status == 200, f"HTTP status {response.status}, expected 200")
            expect(isinstance(result, dict), "Tool response is not a JSON object")
            check(result)
        except Exception as error:
            row["failures"].append(f"{type(error).__name__}: {error}")
        finally:
            connection.close()
            row["elapsed_s"] = time.monotonic() - self.start - row["started_s"]
            self.record(row)
        return result, row

    def seed(self, label, method, expected_status):
        url = self.base + "/hist/" + label
        row = {"name": "capture-" + label, "kind": "proxy_seed", "method": method,
               "url": url, "started_s": time.monotonic() - self.start, "failures": []}
        connection = http.client.HTTPConnection(*PROXY, timeout=15)
        try:
            # Absolute-form requests force proxy use even for localhost targets.
            connection.request(method, url, body=b"" if method == "POST" else None,
                               headers={"Host": f"{FIXTURE[0]}:{FIXTURE[1]}"})
            response = connection.getresponse()
            row.update(http_status=response.status, response_headers=response.getheaders(),
                       raw_response=response.read().decode("utf-8", errors="replace"))
            expect(response.status == expected_status, f"Expected {expected_status}, observed {response.status}")
        except Exception as error:
            row["failures"].append(f"{type(error).__name__}: {error}")
        finally:
            connection.close()
            row["elapsed_s"] = time.monotonic() - self.start - row["started_s"]
            self.record(row)


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_POST(self):
        self.do_GET()

    def do_GET(self):
        run = self.server.run
        path = self.path
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        run.event("accepted", method=self.command, path=path)
        try:
            parts = path.strip("/").split("/")
            expect(len(parts) >= 3 and parts[0] == run.tag, "Request is outside the owned fixture prefix")
            route, payload = parts[1], parts[2]
            if route == "disconnect":
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                run.event("fixture_closed_socket", path=path)
                return
            if route.startswith("slow-"):
                deadline, peer_closed = time.monotonic() + 125, False
                while time.monotonic() < deadline:
                    if run.stop.wait(min(0.25, max(0, deadline - time.monotonic()))):
                        return
                    if not peer_closed and select.select([self.connection], [], [], 0)[0]:
                        try:
                            if self.connection.recv(1, socket.MSG_PEEK) == b"":
                                peer_closed = True
                                run.event("peer_eof", path=path)
                        except OSError as error:
                            peer_closed = True
                            run.event("peer_read_error", path=path, error=str(error))
            status, body = 200, b"Token:abc"
            if route == "hist":
                status = {"old": 200, "post": 201, "missing": 404, "new": 200}[payload]
                body = b"MISSING" if payload == "missing" else b"Token:abc Token:DEF"
            elif route == "httpfail":
                status, body = 500, b"FAIL"
            elif route == "empty":
                status, body = 204, b""
            run.event("response_attempt", path=path, status=status, body_bytes=len(body))
            self.send_response_only(status)
            for name, value in (("SeRvEr", "owned-fixture"), ("X-POWERED-BY", "owned-runtime"),
                                ("x-AspNet-Version", "fixture-version"), ("Servers", "exclude-this"),
                                ("server-extra", "exclude-this-too"), ("X-Fixture-Run", run.tag),
                                ("Content-Length", str(len(body))), ("Connection", "close")):
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            self.close_connection = True
            run.event("write_success", path=path)
        except Exception as error:
            self.close_connection = True
            run.event("handler_error", path=path, error=f"{type(error).__name__}: {error}")
        finally:
            run.event("finished", path=path)


def normal_cases(run):
    run.case("encode-runtime", "encode", {"input": "probe", "type": "base64"},
             lambda r: expect(r.get("output") == "cHJvYmU=", "Base64 operation returned the wrong output"))
    run.case("burp-version", "burp_version", {},
             lambda r: expect(all(k in r for k in ("name", "major", "minor", "build")), "Missing actual Burp version fields"))
    for label, method, status in (("old", "GET", 200), ("post", "POST", 201), ("missing", "GET", 404), ("new", "GET", 200)):
        run.seed(label, method, status)

    def page(result):
        expect(result.get("total") == 4, "Expected exactly four captured fixture history rows")
        expect([(r["url"].rsplit("/", 1)[-1], r["index"]) for r in result["items"]]
               == [("missing", 1), ("post", 2)], "Newest-first page or filtered indices differ")

    run.case("history-page", "proxy_history", {"url_filter": f"/{run.tag}/hist/", "offset": 1, "limit": 2}, page)
    run.case("history-filter", "proxy_history", {"url_filter": f"/{run.tag}/hist/", "method_filter": "get", "status_filter": 200, "offset": 1, "limit": 1},
             lambda r: expect(r.get("total") == 2 and [(e["url"].rsplit("/", 1)[-1], e["index"]) for e in r["items"]] == [("old", 1)], "Method/status filtering differs"))
    run.case("history-end", "proxy_history", {"url_filter": f"/{run.tag}/hist/", "offset": 4, "limit": 2},
             lambda r: expect(r.get("total") == 4 and r.get("items") == [], "End page must retain total and contain no rows"))

    def sitemap_rows(result):
        actual = {(item["method"], item["url"], item["status"]) for item in result.get("items", [])}
        expected = {(method, run.base + "/hist/" + label, status)
                    for label, method, status in (("old", "GET", 200), ("post", "POST", 201), ("missing", "GET", 404), ("new", "GET", 200))}
        expect(expected <= actual, "SiteMap omitted a real captured fixture response")
        expect(result.get("total") == len(result.get("items", [])), "SiteMap total differs from enumerated entries")

    sitemap, _ = run.case("sitemap-fixture-rows", "sitemap", {"url_prefix": run.base + "/hist/"}, sitemap_rows)

    def technologies(result):
        expect(set(result.get("hosts", [])) == {"127.0.0.1"}, "Wrong fixture host set")
        # SiteMap includes inferred requests, such as a GET alongside a captured POST.
        expect(isinstance(sitemap, dict) and result.get("requests_sampled") == sitemap.get("total"),
               "Technology sampling differs from the actual SiteMap snapshot")
        expect({name.lower(): value for name, value in (h.split(": ", 1) for h in result.get("technologies", []))}
               == {"server": "owned-fixture", "x-powered-by": "owned-runtime", "x-aspnet-version": "fixture-version"},
               "Supported/near-match technology header names or values differ")

    run.case("technology-headers", "target_info", {"url": run.base + "/hist/"}, technologies)
    result, _ = run.case("search-original-index", "search_history", {"regex": f"/{run.tag}/hist/new$", "search_in": "url", "limit": 10},
                         lambda r: expect(r.get("matches") == 1 and len(r.get("items", [])) == 1, "Expected one matching fixture URL"))
    index = result["items"][0]["index"] if isinstance(result, dict) and result.get("items") else None
    run.case("search-response-insensitive", "search_history", {"regex": f"(?s)X-Fixture-Run: {run.tag}.*token:[a-z]+", "search_in": "response", "limit": 10},
             lambda r: expect(r.get("matches") == 3, "Expected three case-insensitive fixture response matches"))
    if index is not None:
        run.case("extract-full-match", "extract_from_response", {"index": index, "regex": "Token:([a-z]+)"},
                 lambda r: expect(r.get("total_matches") == 1 and r.get("matches") == ["Token:abc"], "Extraction must return the full case-sensitive match"))
    params = {"url_template": run.base + "/ok/@@", "from": 0, "to": 0, "success_length_not": 99, "grep_extract": "Token:([a-z]+)", "record_time": True}

    def grep(result):
        counts(result, 1, 0, 1)
        hit = result["hit_details"][0]
        expect(hit.get("extracted") == "Token:abc" and hit.get("time_ms", -1) >= 0, "Grep/timing fields differ")

    run.case("grep-full-match", "intruder_with_options", params, grep)
    for tool, arguments in (("search_history", {"regex": "(?=Token)"}),
                            ("extract_from_response", {"index": index, "regex": "(?=Token)"}) if index is not None else (None, {}),
                            ("intruder_with_options", {"url_template": run.base + "/ok/@@", "from": 1, "to": 0, "grep_extract": "(?=Token)"})):
        if tool is not None:
            before = len(run.arrivals())
            run.case("unsupported-" + tool, tool, arguments,
                     lambda r: expect(set(r) == {"error"} and r["error"].startswith("Invalid or unsupported RE2J regex:") and len(run.arrivals()) == before,
                                      "Unsupported regex must return a clear error without target traffic"))

    for tool in ("intruder_attack", "intruder_attack_async"):
        # shortcut: error checks do not assert fixture origin; inspect close events when adding failure routes.
        for route, hit_length, hits in (("ok", 99 if tool == "intruder_attack" else 9, 3 if tool == "intruder_attack" else 0), ("httpfail", 4, 0)):
            arguments = {"url_template": run.base + f"/{route}/@@", "from": 0, "to": 2, "threads": 2, "pad_digits": 3, "success_length_not": hit_length}
            run.case(route + "-" + tool, tool, arguments, lambda r, h=hits: counts(r, 3, 0, h))

        def disconnected(result):
            expect(result.get("total_requests") in (0, 1), "One failed send must have a completed count of zero or one")
            expect(isinstance(result.get("errors"), int) and result["errors"] >= 1, "Socket-close must record an error")
            expect(result.get("hits") == 0 and result.get("hit_details") == [], "Socket-close unexpectedly became a hit")

        run.case("socket-close-" + tool, tool, {"url_template": run.base + "/disconnect/@@", "from": 0, "to": 0, "threads": 2, "success_length_not": 99}, disconnected)
    run.case("async-single-hit", "intruder_attack_async", {"url_template": run.base + "/ok/@@", "from": 0, "to": 0, "threads": 2, "success_length_not": 99},
             lambda r: counts(r, 1, 0, 1))

    for tool in ("intruder_attack", "intruder_attack_async", "intruder_with_options"):
        run.case("empty-204-" + tool, tool,
                 {"url_template": run.base + "/empty/@@", "from": 0, "to": 0, "threads": 2, "success_length_not": 99},
                 lambda r: counts(r, 1, 0, 1))
    for tool, extra in (("intruder_with_options", {"from": 0, "to": 0}),
                        ("intruder_attack_wordlist", {"wordlist": ["0"]}),
                        ("intruder_pitchfork", {"placeholders": {"@@": ["0"]}}),
                        ("intruder_cluster_bomb", {"placeholders": {"@@": ["0"]}, "max_requests": 1}),
                        ("intruder_battering_ram", {"wordlist": ["0"], "placeholder": "@@"})):
        run.case("socket-close-" + tool, tool,
                 {"url_template": run.base + "/disconnect/@@", "success_length_not": 99, **extra},
                 lambda r, attempts=1 if tool == "intruder_cluster_bomb" else 0: counts(r, attempts, 1, 0))

    for tool in ("send_request", "repeater_send", "repeater_modify_send"):
        for route, status in (("disconnect", None), ("empty", 204), ("httpfail", 500)):
            url = run.base + f"/{route}/0"
            arguments = {"url": url, "method": "GET"} if tool == "send_request" else {
                "request": f"GET /{run.tag}/{route}/0 HTTP/1.1\r\nHost: {FIXTURE[0]}:{FIXTURE[1]}\r\n\r\n",
                "host": FIXTURE[0], "port": FIXTURE[1], "https": False,
            }

            def direct_response(result, expected=status):
                if expected is None:
                    expect("error" in result and "response" in result["error"].lower(),
                           "A missing HTTP response must return an operation error")
                else:
                    expect("error" not in result and result.get("status") == expected,
                           "A valid empty/error HTTP response must retain its status")
                    expect(result.get("length") == (0 if expected == 204 else 4), "Direct response body length changed")

            run.case(route + "-" + tool, tool, arguments, direct_response)

    for tool in ("intruder_attack", "intruder_attack_async", "intruder_with_options"):
        arguments = {"url_template": run.base + "/ok/@@", "from": 7, "to": 7, "threads": 2, "success_length_not": 99, "pad_digits": 1025}
        before = len(run.arrivals())
        cap_error = {"error": "pad_digits must be no greater than 1024"}
        result, _ = run.case("padding-1025-" + tool, tool, arguments,
                             lambda r: expect(r == cap_error and len(run.arrivals()) == before, "Width 1025 must reject before target traffic"))
        if result == cap_error:
            for width in (2147483647, 4294967297):
                run.case(f"padding-{width}-" + tool, tool, {**arguments, "from": 1, "to": 0, "pad_digits": width},
                         lambda r: expect(r == cap_error and len(run.arrivals()) == before, "Oversized empty-range padding must reject before target traffic"))
        for width, payload in ((0, "7"), (-4294967293, "7"), (3, "007"), (1024, "0" * 1023 + "7")):
            def padded(result, expected=payload):
                counts(result, 1, 0, 1)
                expect(result["hit_details"][0].get("payload") == expected and result["hit_details"][0].get("length") == 9, "Accepted padding changed payload/response fields")
            run.case(f"padding-{width}-" + tool, tool, {**arguments, "pad_digits": width}, padded)


def slow_cases(run):
    phase_start = time.monotonic()

    def deadline_result(result, offered):
        expect(result.get("timed_out") is True, "Slow attack did not report coordinator timeout")
        expect(result.get("hits") == 0 and result.get("hit_details") == [], "Slow attack unexpectedly reported a hit")
        # Montoya may return null; the server still increments total_requests before validation.
        for field in ("total_requests", "errors"):
            expect(type(result.get(field)) is int and 0 <= result[field] <= offered,
                   f"{field} must be an integer within the offered {offered}-candidate range")

    specs = (("intruder_attack", "slow-seq", 2), ("intruder_attack_async", "slow-async", 5))
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(run.case, "deadline-" + route, tool,
                                  {"url_template": run.base + f"/{route}/@@", "from": 0, "to": end, "threads": 2},
                                  lambda result, offered=end + 1: deadline_result(result, offered), 150)
                   for tool, route, end in specs]
        for elapsed in (20, 40, 60, 80, 100, 120, 130):
            time.sleep(max(0, phase_start + elapsed - time.monotonic()))
            print(f"PROGRESS slow observation {elapsed}/130s; completed API calls {sum(f.done() for f in futures)}/2; slow arrivals {len(run.arrivals('slow-'))}", flush=True)
        for future, (_, route, end) in zip(futures, specs):
            _, case = future.result()
            with run.lock:
                events = [dict(e) for e in run.events if f"/{route}/" in e.get("path", "")]
            arrivals = [e for e in events if e["event"] == "accepted"]
            returned = case["started_s"] + case["elapsed_s"]
            nominal_deadline = case["started_s"] + 120
            response_attempts = [e for e in events if e["event"] == "response_attempt"]
            allowed_paths = {f"/{run.tag}/{route}/{candidate}" for candidate in range(end + 1)}
            failures = []
            if not 110 <= case["elapsed_s"] <= 135:
                failures.append(f"Coordinator elapsed {case['elapsed_s']:.3f}s outside expected 110..135s observation window")
            if not arrivals or any(e["path"] not in allowed_paths for e in arrivals):
                failures.append("Slow fixture traffic was absent or outside the owned prefix/candidate range")
            if any(e["t"] <= nominal_deadline for e in response_attempts):
                failures.append("The 125-second fixture attempted a response within the nominal coordinator window")
            run.record({"name": "observation-" + route, "kind": "fixture_observation",
                        "arrivals": [{**e, "since_api_start_s": e["t"] - case["started_s"],
                                      "relative_to_nominal_deadline_s": e["t"] - nominal_deadline,
                                      "relative_to_api_return_s": e["t"] - returned} for e in arrivals],
                        "late_network_arrivals": [e for e in arrivals if e["t"] > nominal_deadline],
                        "response_attempts_before_api_return": [e for e in response_attempts if e["t"] <= returned],
                        "fixture_writes_before_api_return": [e for e in events if e["event"] == "write_success" and e["t"] <= returned],
                        "peer_events": [e for e in events if e["event"] in ("peer_eof", "peer_read_error")],
                        "write_events": [e for e in events if e["event"] in ("response_attempt", "write_success", "handler_error")],
                        "observation_limit": "API receive time and fixture arrivals do not expose Java submission or response-consumption times.",
                        "observed_for_s": time.monotonic() - phase_start, "failures": failures})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Skip the two concurrent 120-second coordinator tests")
    parser.add_argument("--output", type=Path, help="New artifact directory; existing paths are refused")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = args.output or Path(__file__).resolve().parent / ("run-" + stamp + "-" + uuid.uuid4().hex[:6])
    directory.mkdir(parents=True, exist_ok=False)
    print(f"ARTIFACTS {directory.resolve()}", flush=True)
    with (directory / "cases.jsonl").open("w", encoding="utf-8") as cases_file, (directory / "fixture-events.jsonl").open("w", encoding="utf-8") as events_file:
        run = Run(directory, cases_file, events_file)
        server = None
        try:
            server = ThreadingHTTPServer(FIXTURE, FixtureHandler)
            server.daemon_threads = False  # Join owned request handlers before closing the event log.
            server.run = run
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            normal_cases(run)
            if not args.quick:
                slow_cases(run)
        except Exception as error:
            run.record({"name": "runner-error", "kind": "runner", "failures": [f"{type(error).__name__}: {error}"]})
        finally:
            run.stop.set()
            if server is not None:
                server.shutdown()
                server.server_close()
        summary = {"started_utc": stamp, "requested_source_head": SOURCE_HEAD, "python": sys.version,
                   "api": API, "proxy": PROXY, "fixture": FIXTURE, "fixture_tag": run.tag, "quick": args.quick,
                   "elapsed_s": time.monotonic() - run.start, "passed": all(not c["failures"] for c in run.cases),
                   "cases": run.cases, "fixture_events": run.events,
                   "unknowns": ["The actual RequestOptions response-timeout argument is not exposed by the HTTP API.",
                                "Coordinator return does not establish that in-flight transport terminated.",
                                "Fixture arrivals observe network activity, not exact Java task-submission timestamps.",
                                "A successful late fixture write does not prove that Burp consumed the response."]}
        (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT {'PASS' if summary['passed'] else 'FAIL'}; cases {len(run.cases)}; artifacts {directory.resolve()}", flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
