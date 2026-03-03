import hmac

DEFAULT_WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def extract_request_token(request):
    token = str(request.headers.get('X-API-Token', '') or '').strip()
    if token:
        return token
    token = str(request.args.get('token', '') or '').strip()
    if token:
        return token
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        token = str(payload.get('token', '') or '').strip()
        if token:
            return token
    return ''


def request_needs_auth(request, path_prefix='/api/', write_methods=None):
    methods = write_methods or DEFAULT_WRITE_METHODS
    if not str(request.path or '').startswith(path_prefix):
        return False
    return str(request.method or '').upper() in methods


def verify_request_token(request, secret, path_prefix='/api/', write_methods=None):
    if not secret:
        return True
    if not request_needs_auth(request, path_prefix=path_prefix, write_methods=write_methods):
        return True
    token = extract_request_token(request)
    if not token:
        return False
    return hmac.compare_digest(token, str(secret))

