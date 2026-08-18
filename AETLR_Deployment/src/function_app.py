## Receives the HTTP request through Azure Functions.
## Passes the request to the correct HTTP handler

import azure.functions as func

from functions.bdx_tracker_http import main as bdx_tracker_http_main
from functions.bikmo_http import main as bikmo_http_main
from functions.floodre_http import main as floodre_http_main
from functions.unposted_reports_http import main as unposted_reports_http_main


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="bikmo", methods=["POST"])
def bikmo(req: func.HttpRequest) -> func.HttpResponse:
    return bikmo_http_main(req)


@app.route(route="bdx-tracker", methods=["POST"])
def bdx_tracker(req: func.HttpRequest) -> func.HttpResponse:
    return bdx_tracker_http_main(req)


@app.route(route="unposted-reports", methods=["POST"])
def unposted_reports(req: func.HttpRequest) -> func.HttpResponse:
    return unposted_reports_http_main(req)


@app.route(route="floodre", methods=["POST"])
def floodre(req: func.HttpRequest) -> func.HttpResponse:
    return floodre_http_main(req)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse("ok", status_code=200)
