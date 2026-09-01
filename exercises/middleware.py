"""Response policies for authenticated application traffic."""


class PrivateResponseCacheMiddleware:
    """Prevent browsers and intermediary caches from storing user data.

    The service worker has the same policy for offline fetches, but HTTP
    cache headers are still required for normal browser/proxy requests.
    AuthenticationMiddleware runs before this middleware in settings so the
    decision is made from the actual authenticated user.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            response['Cache-Control'] = 'private, no-store, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
