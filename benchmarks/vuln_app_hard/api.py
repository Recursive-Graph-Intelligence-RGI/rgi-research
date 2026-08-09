"""HTTP API surface."""
from admin import run_backup, purge_user
from cache import import_blob
from reports import sales_report
from sessions import create_session, get_session
from storage import read_invoice, save_upload
from users import login, register
from webhooks import test_webhook
from tokens import issue_token


def route(request):
    action = request.args.get("action")
    if action == "register":
        register(request.form["email"], request.form["password"])
        return {"ok": True}
    if action == "login":
        if login(request.form["email"], request.form["password"]):
            token = issue_token(request.form["email"])
            return {"token": token, "session": create_session(request.form["email"])}
        return {"error": "bad credentials"}
    if action == "invoice":
        return read_invoice(request.args["name"])
    if action == "upload":
        return save_upload(request.args["filename"], request.body)
    if action == "report":
        return sales_report(request.args["expr"])
    if action == "webhook_test":
        return {"status": test_webhook(request.args["url"])}
    if action == "import_session":
        return import_blob(request.body)
    if action == "backup":
        return run_backup(request)
    if action == "purge":
        return purge_user(request)
    if action == "session":
        return get_session(request.args["id"])
    return {"error": "unknown action"}
