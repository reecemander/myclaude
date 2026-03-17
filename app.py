"""Flask web interface for the Research Podcast Pipeline.

Streams live console output to the browser via Server-Sent Events while
also pushing structured data (ranked papers, script) as JSON events.

Usage:
    python app.py          # starts on http://localhost:5000
    PORT=8080 python app.py
"""

import os
import sys
import json
import time
import queue
import threading
import io
from flask import Flask, render_template, Response, request, jsonify
from dotenv import load_dotenv

load_dotenv()

# ─── Thread-local stdout capture ─────────────────────────────────────────────
# Replaces sys.stdout globally. Pipeline threads set _thread_local.log_queue
# so their print() calls route to the SSE queue; all other threads (Flask,
# werkzeug) fall through to the original stdout.

_thread_local = threading.local()
_original_stdout = sys.stdout


class _PipelineWriter(io.RawIOBase):
    def write(self, text):
        q = getattr(_thread_local, "log_queue", None)
        if q is not None:
            stripped = text.rstrip("\n")
            if stripped:
                q.put({"type": "log", "text": stripped})
        else:
            _original_stdout.write(text)
        return len(text)

    def flush(self):
        if getattr(_thread_local, "log_queue", None) is None:
            _original_stdout.flush()

    def isatty(self):
        return False


sys.stdout = _PipelineWriter()

# ─── Import pipeline functions after stdout is replaced ──────────────────────
from research_podcast import fetch_papers, rank_papers, write_script, CLAUDE_MODEL  # noqa: E402

app = Flask(__name__)

# ─── Job state (one concurrent run) ─────────────────────────────────────────
_job_lock = threading.Lock()
_is_running = False
_current_queue: "queue.Queue | None" = None


def _pipeline_thread(search_term: str, out_q: queue.Queue) -> None:
    """Run Steps 1-3, pushing log lines and structured data events to out_q."""
    global _is_running
    _thread_local.log_queue = out_q
    try:
        papers = fetch_papers(search_term)
        out_q.put({"type": "papers", "data": papers})

        top_papers = rank_papers(papers, search_term)
        out_q.put({"type": "ranked", "data": top_papers})

        script = write_script(top_papers, search_term)
        out_q.put({"type": "script", "data": script})

        out_q.put({"type": "done"})

    except SystemExit:
        out_q.put({"type": "error", "text": "Not enough papers found — try a broader search term or longer date range."})
    except Exception as exc:
        out_q.put({"type": "error", "text": str(exc)})
    finally:
        _thread_local.log_queue = None
        with _job_lock:
            _is_running = False
        out_q.put(None)  # sentinel — closes the SSE stream


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    default_term = os.getenv("SEARCH_TERM", "microbiota gut brain axis").strip('"')
    return render_template("index.html", default_search_term=default_term, model=CLAUDE_MODEL)


@app.route("/run", methods=["POST"])
def run():
    global _is_running, _current_queue
    with _job_lock:
        if _is_running:
            return jsonify({"error": "Pipeline already running"}), 409
        body = request.get_json(silent=True) or {}
        search_term = body.get("search_term", "").strip()
        if not search_term:
            search_term = os.getenv("SEARCH_TERM", "microbiota gut brain axis").strip('"')
        _current_queue = queue.Queue()
        _is_running = True

    t = threading.Thread(target=_pipeline_thread, args=(search_term, _current_queue), daemon=True)
    t.start()
    return jsonify({"status": "started", "search_term": search_term})


@app.route("/stream")
def stream():
    def generate():
        global _current_queue
        # Brief wait in case /stream is hit a few ms before /run sets the queue
        for _ in range(50):
            with _job_lock:
                q = _current_queue
            if q is not None:
                break
            time.sleep(0.1)
        else:
            yield f"data: {json.dumps({'type': 'error', 'text': 'No pipeline running'})}\n\n"
            return

        while True:
            try:
                event = q.get(timeout=30)
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                continue
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    _original_stdout.write(f"Starting Research Podcast Generator → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
