"""Complexity-scaling benchmark generator (Experiment C1).

Programmatic, seeded, architecture-blind: emits a fake web app AND its
ground-truth manifest mechanically, so scoring is independent of any
architecture. Vuln vocabulary matches vuln_app_hard's 15 classes so
results are comparable across experiments.

Complexity axes (per the falsification contract):
  n_files     total modules (standalone + chain members + noise)
  n_vulns     graded vulnerabilities (~25% density)
  chain_depth cross-file hops from entry point to vuln sink
"""
import json
import random
from pathlib import Path

# (class, scoring terms, sink template). {fn}, {arg}, {name} are filled.
SINKS = {
    "sqli": (
        ["injection"],
        "def {fn}(conn, {arg}):\n"
        "    return conn.execute(f\"SELECT * FROM items WHERE name LIKE '%{{{arg}}}%'\").fetchall()\n",
    ),
    "jwt_sig": (
        ["signature"],
        "def {fn}(token):\n"
        "    import base64, json\n"
        "    payload = token.split('.')[1]\n"
        "    payload += '=' * (-len(payload) % 4)\n"
        "    return json.loads(base64.urlsafe_b64decode(payload))  # never verifies signature\n",
    ),
    "no_expiry": (
        ["expir"],
        "def {fn}(user_id):\n"
        "    import time\n"
        "    return {{'sub': user_id, 'iat': int(time.time())}}  # no exp claim: tokens never expire\n",
    ),
    "session_timeout": (
        ["timeout"],
        "def {fn}(session_id):\n"
        "    return _SESSIONS.get(session_id)  # returned as-is: no timeout, no idle check\n",
    ),
    "pickle": (
        ["pickle"],
        "def {fn}(blob):\n"
        "    import pickle\n"
        "    return pickle.loads(blob)  # deserializes client-supplied data\n",
    ),
    "eval": (
        ["eval"],
        "def {fn}(expr, ctx):\n"
        "    return str(eval(expr, {{'__builtins__': {{}}}}, ctx))  # evaluates user template\n",
    ),
    "traversal": (
        ["traversal"],
        "def {fn}(name):\n"
        "    import os\n"
        "    return open(os.path.join('uploads', name), 'rb').read()  # no path sanitization\n",
    ),
    "ssrf": (
        ["ssrf"],
        "def {fn}(url):\n"
        "    import urllib.request\n"
        "    return urllib.request.urlopen(url).status  # fetches arbitrary URL (SSRF)\n",
    ),
    "cmdi": (
        ["command injection", "os.system"],
        "def {fn}(archive):\n"
        "    import os\n"
        "    os.system(f'tar czf /backups/{{archive}} /data')  # shell interpolation\n",
    ),
    "md5": (
        ["md5"],
        "def {fn}(password):\n"
        "    import hashlib\n"
        "    return hashlib.md5(password.encode()).hexdigest()  # weak password hashing\n",
    ),
    "no_authz": (
        ["bypass", "unprotected", "missing auth", "authorization"],
        "def {fn}(conn, {arg}):\n"
        "    conn.execute(f'DELETE FROM users WHERE id = {{{arg}}}')  # no authorization check\n"
        "    conn.commit()\n",
    ),
    "yaml": (
        ["yaml"],
        "def {fn}(text):\n"
        "    import yaml\n"
        "    return yaml.load(text, Loader=yaml.Loader)  # unsafe loader\n",
    ),
    "xss": (
        ["xss"],
        "def {fn}(request):\n"
        "    q = request.args.get('q', '')\n"
        "    return f'<html><body><h1>Results for {{q}}</h1></body></html>'  # unescaped reflection\n",
    ),
    "debug": (
        ["debug"],
        "def {fn}():\n"
        "    return {{'debug': True, 'secret_key': 'debug-secret'}}  # debug mode in production\n",
    ),
    "hardcoded": (
        ["hardcoded"],
        "{arg}_KEY = 'AKIAIOSFODNN7EXAMPLE'\n"
        "{arg}_SECRET = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'  # hardcoded cloud credentials\n",
    ),
}
SINK_CLASSES = list(SINKS)

NOISE_TEMPLATE = '''"""{doc}."""
from dataclasses import dataclass, field


@dataclass
class {cls}:
    name: str
    tags: list = field(default_factory=list)

    def describe(self):
        return f"{{self.name}} ({{len(self.tags)}} tags)"


def make_{fn}(name):
    return {cls}(name=name)
'''

PASSTHROUGH_TEMPLATE = '''"""Chain segment {i}: request routing."""
from {next_mod} import handle as _next_handle


def handle(request):
    payload = request.args.get("payload", "")
    return _next_handle(request)
'''

SINK_MODULE_TEMPLATE = '''"""Business logic module."""
{body}

def handle(request):
    payload = request.args.get("payload", "")
    return {fn}(payload)
'''

LEVELS = {
    # level: (n_files, n_vulns, chain_depth)
    "L1": (8, 4, 1),
    "L2": (16, 8, 2),
    "L3": (32, 16, 3),
    "L4": (64, 32, 4),
    "L5": (128, 48, 6),
}


def generate(out_dir: Path, n_files: int, n_vulns: int, chain_depth: int, seed: int) -> dict:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_chained = max(1, n_vulns // 4) if chain_depth > 1 else 0
    n_chained = min(n_chained, (n_files - n_vulns // 2) // max(chain_depth, 1))
    n_standalone = n_vulns - n_chained

    classes = [SINK_CLASSES[i % len(SINK_CLASSES)] for i in
           rng.sample(range(1000), n_vulns)]  # deterministic rotation w/ seed offset
    vulns, files = [], {}

    # Standalone vulns: one module each
    for i in range(n_standalone):
        cls = classes.pop()
        terms, body_t = SINKS[cls]
        mod = f"mod_{cls}_{i}"
        body = body_t.format(fn=f"op_{cls}_{i}", arg=f"v{i}", name=mod)
        files[f"{mod}.py"] = f'"""Module {mod}."""\n{body}'
        vulns.append({"id": f"{cls}-{mod}", "terms": terms})

    # Chained vulns: chain_depth-1 pass-throughs feeding one sink
    for c in range(n_chained):
        cls = classes.pop()
        terms, body_t = SINKS[cls]
        sink_mod = f"chain{c}_sink_{cls}"
        fn = f"sink_{cls}_{c}"
        body = body_t.format(fn=fn, arg="payload", name=sink_mod)
        files[f"{sink_mod}.py"] = SINK_MODULE_TEMPLATE.format(body=body, fn=fn)
        vulns.append({"id": f"{cls}-{sink_mod}", "terms": terms})
        prev = sink_mod
        for seg in range(chain_depth - 1, 0, -1):
            mod = f"chain{c}_seg{seg}"
            files[f"{mod}.py"] = PASSTHROUGH_TEMPLATE.format(i=seg, next_mod=prev)
            prev = mod

    # Noise modules to reach n_files
    noise_idx = 0
    while len(files) < n_files:
        mod = f"util_noise_{noise_idx}"
        files[f"{mod}.py"] = NOISE_TEMPLATE.format(
            doc=f"Utility module {noise_idx}", cls=f"Noise{noise_idx}", fn=f"noise_{noise_idx}")
        noise_idx += 1

    for name, content in files.items():
        (out_dir / name).write_text(content)

    manifest = {"vulns": vulns,
                "meta": {"n_files": len(files), "n_vulns": len(vulns),
                         "chain_depth": chain_depth, "seed": seed}}
    (out_dir / "ground_truth.json").write_text(json.dumps(manifest, indent=1))
    return manifest
