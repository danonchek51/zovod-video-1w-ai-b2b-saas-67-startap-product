"""Runs inside Resolve (via resolve_bridge.py script mode) and reports project state.

Prints one flat key=value line so the caller can parse it without worrying
about JSON escaping in the MCP transport.
"""
try:
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    project = proj.GetName() if proj else "none"
    timeline = "none"
    rendering = "false"
    jobs = "-1"
    if proj:
        tl = proj.GetCurrentTimeline()
        timeline = tl.GetName() if tl else "none"
        rendering = "true" if proj.IsRenderingInProgress() else "false"
        try:
            jobs = str(len(proj.GetRenderJobList() or []))
        except Exception:
            jobs = "-1"
    print("DOCTORSTATE project=%s | timeline=%s | rendering=%s | jobs=%s"
          % (project, timeline, rendering, jobs))
except Exception as e:
    print("DOCTORSTATE error=%s" % e)
