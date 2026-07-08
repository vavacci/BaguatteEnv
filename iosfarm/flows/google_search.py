"""google_search — example business flow.

Demonstrates how a concrete process plugs into the framework: it only uses the
Session's control (open/scroll/screenshot) and capture (mark/wait_idle/flows_since)
methods — no knowledge of baguette, iwdp, proxy, or file formats.

Steps:
  1. open Google, let it settle, screenshot
  2. issue the search (via the search URL — robust and needs no on-screen keyboard)
  3. wait for network idle, scroll to trigger more requests, wait again
  4. return the captured request/response flows for this flow's window

params: {"query": "<search terms>", "scrolls": <int, default 2>}
Make sure the target hosts (google.com / www.google.com) are in config.capture.hosts.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .base import Flow, FlowResult, register


@register
class GoogleSearchFlow(Flow):
    name = "google_search"

    def run(self, session, params: dict) -> FlowResult:
        query = params.get("query", "claude ai")
        scrolls = int(params.get("scrolls", 2))
        shots: list[str] = []

        marker = session.mark()

        # 1) browse Google home
        session.open("https://www.google.com/")
        session.wait_idle()
        shots.append(str(session.screenshot("google_home")))

        # 2) search (search URL avoids fragile keyboard interaction)
        session.open(f"https://www.google.com/search?q={quote_plus(query)}")
        session.wait_idle()
        shots.append(str(session.screenshot("google_results_top")))

        # 3) scroll to pull more results / lazy requests
        for i in range(scrolls):
            session.scroll("up", distance=session.control.height * 0.8)
            session.wait_idle()
        shots.append(str(session.screenshot("google_results_scrolled")))

        # 4) collect this flow's captured req/resp
        flows = session.flows_since(marker)
        return FlowResult(
            name=self.name,
            params={"query": query, "scrolls": scrolls},
            captured=len(flows),
            data={
                "query": query,
                "urls": [f["url"] for f in flows],
                "statuses": {f["url"]: f["status_code"] for f in flows},
            },
            screenshots=shots,
        )
