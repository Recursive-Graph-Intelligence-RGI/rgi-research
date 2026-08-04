"""Report download handling."""
from middleware import require_auth
from storage import load_file


@require_auth
def download_report(request):
    filename = request.args.get("filename")
    return load_file(filename)
