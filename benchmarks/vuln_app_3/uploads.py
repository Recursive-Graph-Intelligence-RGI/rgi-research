"""Report upload handling."""
from storage import save_file


def upload_report(request):
    filename = request.args.get("filename")
    content = request.files["report"].read()
    return save_file(filename, content)
